import pika
import json
from datetime import datetime
import redis
from dotenv import load_dotenv
import os
import copy
import sys
from enum import Enum
from lib import ftp, aws

DOTENV_FILE_PATH = '.env'
MAX_FILE_SIZE_IN_MB = 10
IMAGE_FILE_EXTENSION = '.png'

HUMAN_OBJECT_TEMPLATE_DICT = {
    "type": "Human",
    "age": int,
    "gender": str
}

VEHICLE_OBJECT_TEMPLATE_DICT = {
    "type": "Vehicle",
    "category": str,
    "brand": str,
    "color": str,
    "licence": str
}

OBJECT_TEMPLATE_DICT = {
    "id": str,
    "bbox": {
        "topleftx": int,
        "toplefty": int,
        "bottomrightx": int,
        "bottomrighty": int
    },
    "image_URL": str,
    "object": dict
}

EVENT_TEMPLATE_DICT = {
    "object_id": str,
    "action": str,
    "video_URL": str,
    "type": str
}

LOCATION_TEMPLATE_DICT = {
    "id": str,
    "lat": float,
    "lon": float,
    "alt": float,
    "description": str
}

MODEL_SPECS_TEMPLATE_DICT = {
    "description": str,
    "camera": {
        "id": str,
        "type": str
    }
}

OBJECT_MESSAGE_TEMPLATE_DICT = {
    "message_type": "object",
    "payload": {
        "message_id": str,
        "timestamp": str,
        "location": LOCATION_TEMPLATE_DICT,
        "specs": MODEL_SPECS_TEMPLATE_DICT,
        "number_of_objects": int,
        "object_list": list,
        "number_of_events": int,
        "event_list": list
    },
}


class ObjectType(Enum):
    HUMAN = 1
    VEHICLE = 2


load_dotenv(dotenv_path=DOTENV_FILE_PATH)

amqp_host = os.getenv('AMQP_HOST')
amqp_port = int(os.getenv('AMQP_PORT'))
amqp_vhost = os.getenv('AMQP_VIRTUAL_HOST')
amqp_username = os.getenv('AMQP_USERNAME')
amqp_password = os.getenv('AMQP_PASSWORD')
amqp_model_queue = os.getenv('AMQP_MODEL_QUEUE')
amqp_object_queue = os.getenv('AMQP_OBJECT_QUEUE')

redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_db = os.getenv('REDIS_DB')

s3_bucket = os.getenv('S3_BUCKET')
s3_file_destination_directory = os.getenv('S3_DESTINATION_DIR')
s3_start_url = os.getenv('S3_START_URL')

local_image_directory = os.getenv('LOCAL_IMAGE_DIRECTORY')

location_id = ""
location_description = ""
message_count = 0
model_description = ""
camera_id = ""
camera_type = ""


def getDataRedis():

    global redis_host, redis_port, redis_db
    global location_id, location_description
    global camera_id, camera_type, model_description
    redis_client = redis.Redis(
        host=redis_host, port=redis_port, db=redis_db)

    try:
        location_id = str(redis_client.get("LOCATION_ID")).zfill(4)
    except Exception as e:
        location_id = str(int(-1))

    try:
        location_description = str(redis_client.get("LOCATION_DESCRIPTION"))
    except Exception as e:
        location_description = "nil"

    try:
        camera_id = str(redis_client.get("CAMERA_ID")).zfill(4)
    except Exception as e:
        location_id = str(int(-1))

    try:
        camera_type = str(redis_client.get("CAMERA_TYPE"))
    except Exception as e:
        camera_type = 'RGB'

    try:
        model_description = str(redis_client.get("MODEL_DESCRIPTION"))
    except Exception as e:
        model_description = 'nil'


getDataRedis()  # Get LOCATION_ID, LOCATION_DESCRIPTION from redis db


class RabbitMQClient:
    def __init__(self, host: str, port: int, vhost: str,
                 usr: str, pwd: str,
                 model_queue: str, object_queue: str):
        self.host = host
        self.port = port
        self.virtual_host = vhost
        self.username = usr
        self.password = pwd
        self.model_queue = model_queue
        self.object_queue = object_queue

        credentials = pika.PlainCredentials(self.username, self.password)
        parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host=self.virtual_host,
            credentials=credentials
        )
        self.connection = pika.BlockingConnection(parameters)
        self.model_channel = self.connection.channel()
        self.model_channel.queue_declare(
            queue=self.model_queue, durable=True)
        self.object_channel = self.connection.channel()
        self.object_channel.queue_declare(
            queue=self.object_queue, durable=True)

    def objectPublish(self, message: str | dict) -> bool:
        try:
            if isinstance(message, dict):
                message_body = json.dumps(obj=message, indent=4)
            else:
                message_body = message
            self.object_channel.basic_publish(
                exchange='',
                routing_key=self.object_queue,
                body=message_body
            )
        except Exception as e:
            print(f'[ERR]: {e}', file=sys.stderr)
            return False
        return True

    def start(self):
        def callback(ch, method, properties, body):
            global local_image_directory

            raw_object = RawObject().load(body.decode())
            raw_object_list = [raw_object]
            object_data_message = ObjectDataMessage(
                raw_obj_msg_list=raw_object_list)
            message_str = object_data_message.createMessage()
            result = self.objectPublish(message=message_str)

            if result and object_data_message._upload_result:
                for obj in object_data_message._raw_object_list:
                    ts = obj.timestamp
                    path = local_image_directory + ts + IMAGE_FILE_EXTENSION
                    os.remove(path=path)

        self.model_channel.basic_consume(
            queue=self.model_queue, on_message_callback=callback, auto_ack=True)

        try:
            self.model_channel.start_consuming()
        except Exception as e:
            self.close()

    def close(self):
        """Closes the connection to the RabbitMQ broker."""
        if self.connection and not self.connection.is_closed:
            self.connection.close()


class RawObject:
    '''
    Base class of all object data.
    '''

    def __init__(self, timestamp: str, id: int, type: str, bbox: list):
        self.timestamp = timestamp
        self.object_id = id
        self.object_type = type
        self.bounding_box = bbox
        self.version = 'ver.1'
        pass

    # def __str__(self):
    #     return f"Object:{self.data_dict}"

    def load(self, raw_str: str):
        try:
            data = json.loads(raw_str)

            self.timestamp = data['timestamp']
            self.object_id = data['id']
            self.object_type = data['type']
            self.bounding_box = data['bbox']

        except json.JSONDecodeError as e:
            print("Failed to decode model message: {e}", file=sys.stderr)


class ObjectDataMessage:
    global location_id, location_description
    global s3_bucket, s3_file_destination_directory, s3_start_url
    global message_count, local_image_directory

    def __init__(self, raw_obj_msg_list: list = [], raw_evn_msg_list: list = []):
        self._num_of_objects = len(raw_obj_msg_list)
        self._num_of_events = len(raw_evn_msg_list)
        self._message_template_dict = copy.deepcopy(
            OBJECT_MESSAGE_TEMPLATE_DICT)

        self._raw_object_list: list[RawObject] = []
        for raw_object_message in raw_obj_msg_list:
            self._raw_object_list.append(
                RawObject().load(raw_str=raw_object_message))

        self._file_transfer_handler = ftp.FileTransferHandler(
            bucket=s3_bucket, max_size_mb=MAX_FILE_SIZE_IN_MB)

        _upload_result = True

    def getCurretLocation(self):
        return 0, 0, 0

    def createLocationObjectDict(self, lat: str, lon: str, alt: str):
        """
        Creates a dictionary representing a location object.

        This method initializes a location dictionary based on the 
        LOCATION_TEMPLATE_DICT, populates it with the provided latitude, 
        longitude, and altitude values, and includes global location 
        identifiers and description.

        Args:
            lat (str): The latitude of the location.
            lon (str): The longitude of the location.
            alt (str): The altitude of the location.

        Returns:
            dict: A dictionary containing the location data.
        """

        location = LOCATION_TEMPLATE_DICT.copy()

        location["id"] = str(location_id)
        location["lat"] = float(lat)
        location["lon"] = float(lon)
        location["alt"] = float(alt)
        location["description"] = str(location_description)

        return location

    def createModelSpecs(self, description: str, cam_id: str, cam_type: str):
        specs = MODEL_SPECS_TEMPLATE_DICT.copy()
        specs["description"] = description
        specs["camera"] = {
            "id": cam_id,
            "type": cam_type
        }

        return specs

    def uploadImage(self, image_path: str) -> bool:
        return True
        des = s3_file_destination_directory + '/' + image_path
        self._upload_result = self._file_transfer_handler.uploadFile(
            file_path=image_path, destination=des)

        return self._upload_result

    def createObjectList(self) -> list:

        def createObjectDetail(object_type: ObjectType) -> dict:
            if object_type == ObjectType.HUMAN:
                object_detail = HUMAN_OBJECT_TEMPLATE_DICT.copy()
            elif object_type == ObjectType.VEHICLE:
                object_detail == VEHICLE_OBJECT_TEMPLATE_DICT.copy()

            return object_detail

        def createBboxDict(self, raw_object: RawObject) -> dict:
            return {
                "topleftx": raw_object.bounding_box[0],
                "toplefty": raw_object.bounding_box[1],
                "bottomrightx": raw_object.bounding_box[2],
                "bottomrighty": raw_object.bounding_box[3]
            },

        object_list = []
        for raw_object in self._raw_object_list:
            object = copy.deepcopy(OBJECT_TEMPLATE_DICT)

            object["id"] = raw_object.object_id
            object["bbox"] = createBboxDict(raw_object=raw_object)

            image_path = local_image_directory + '/' + \
                raw_object.timestamp + IMAGE_FILE_EXTENSION

            if not self.uploadImage(image_path=image_path):
                self._upload_result = False
                continue

            object["image_URL"] = s3_start_url + '/' + s3_file_destination_directory + \
                '/' + raw_object.timestamp + IMAGE_FILE_EXTENSION

            if (raw_object.object_type == "Human"):
                object["object"] = createObjectDetail(
                    object_type=ObjectType.HUMAN)
            elif (raw_object.object_type == "Vehicle"):
                object["object"] = createObjectDetail(
                    object_type=ObjectType.VEHICLE)

            object_list.append(object)

        return object_list

    def createEventList(self) -> list:
        return []

    def createMessageID(self) -> str:
        global message_count
        msg_id = "obj-" + \
            camera_id.zfill(4) + '-' + str(message_count).zfill(8)
        message_count += 1
        return msg_id

    def createTimestamp(self) -> str:
        return self._raw_object_list[0].timestamp

    def createMessage(self) -> dict | str:
        message = copy.deepcopy(OBJECT_MESSAGE_TEMPLATE_DICT)
        message["message_type"] = "object"

        payload_dict = message["payload"]
        payload_dict["message_id"] = self.createMessageID()
        payload_dict["timestamp"] = self.createTimestamp()
        lat, lon, alt = self.getCurretLocation()
        payload_dict["location"] = self.createLocationObjectDict(
            lat=lat, lon=lon, alt=alt)
        payload_dict["specs"] = self.createModelSpecs(
            description=model_description, cam_id=camera_id, cam_type=camera_type)
        payload_dict["number_of_objects"] = self._num_of_objects
        payload_dict["object_list"] = self.createObjectList()
        payload_dict["number_of_events"] = self._num_of_events
        payload_dict["event_list"] = self.createEventList()

        return json.dumps(obj=message, indent=4)


if __file__ == "__main__":
    client = RabbitMQClient(host=amqp_host, port=amqp_port, vhost=amqp_vhost, usr=amqp_username,
                            pwd=amqp_password, model_queue=amqp_model_queue, object_queue=amqp_object_queue)
    client.start()
