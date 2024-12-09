import pika
import json
from datetime import datetime
import redis
from dotenv import load_dotenv
import os
import copy
import sys
from enum import Enum
from lib import ftp

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
amqp_vhost = os.getenv('AMQP_VHOST')
amqp_username = os.getenv('AMQP_USERNAME')
amqp_password = os.getenv('AMQP_PASSWORD')
amqp_model_queue = os.getenv('AMQP_MODEL_QUEUE')
amqp_object_queue = os.getenv('AMQP_OBJECT_QUEUE')

redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_db = os.getenv('REDIS_DB')

minio_bucket = os.getenv('MINIO_BUCKET')
minio_file_destination_directory = os.getenv('MINIO_DESTINATION_DIR')
minio_start_url = os.getenv('MINIO_START_URL')
minio_credentials_file_path = os.getenv('MINIO_CREDENTIALS_FILE_PATH')

local_image_directory = os.getenv('LOCAL_IMAGE_DIR')

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
    global minio_bucket
    redis_client = redis.Redis(
        host=redis_host, port=redis_port, db=redis_db)

    try:
        location_id = str(redis_client.get(
            "LOCATION_ID").decode('utf-8')).zfill(4)
    except Exception as e:
        location_id = str(int(-1))

    try:
        location_description = str(redis_client.get(
            "LOCATION_DESCRIPTION").decode('utf-8'))
    except Exception as e:
        location_description = "nil"

    try:
        camera_id = str(redis_client.get("CAMERA_ID").decode('utf-8')).zfill(4)
    except Exception as e:
        location_id = str(int(-1))

    try:
        camera_type = str(redis_client.get("CAMERA_TYPE").decode('utf-8'))
    except Exception as e:
        camera_type = 'RGB'

    try:
        model_description = str(redis_client.get(
            "MODEL_DESCRIPTION").decode('utf-8'))
    except Exception as e:
        model_description = 'nil'

    try:
        minio_bucket = str(redis_client.get('DEVICE_ID')).decode('utf-8')
    except Exception as e:
        minio_bucket = 'nil'


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

    def objectPublish(self, message: str) -> bool:
        try:
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

            raw_object_msg = body.decode()
            print(f" {raw_object_msg}\n")

            raw_object_list = [raw_object_msg]
            object_data_message = ObjectDataMessage(
                raw_obj_msg_list=raw_object_list)
            message_str = object_data_message.createMessage()
            result = self.objectPublish(message=message_str)

            if result and object_data_message._upload_result:
                for obj in object_data_message._raw_object_list:
                    ts = obj.timestamp
                    path = local_image_directory + '/' + ts + IMAGE_FILE_EXTENSION
                    os.remove(path=path)
                    print(path)
                ch.basic_ack(delivery_tag=method.delivery_tag)

        self.model_channel.basic_consume(
            queue=self.model_queue, on_message_callback=callback, auto_ack=False)

        try:
            self.model_channel.start_consuming()
        except Exception as e:
            print(e)
            self.close()

    def close(self):
        """Closes the connection to the RabbitMQ broker."""
        if self.connection and not self.connection.is_closed:
            self.connection.close()


class RawObject:
    '''
    Base class of all object data.
    '''

    def __init__(self, timestamp: str = '', id: int = 0, type: str = '', bbox: list = []):
        self.timestamp = timestamp
        self.object_id = id
        self.object_type = type
        self.bounding_box = bbox
        self.version = 'ver.1'
        pass

    # def __str__(self):
    #     return f"Object:{self.data_dict}"

    def to_dict(self):
        return {
            'timestamp': self.timestamp,
            'id': self.object_id,
            'type': self.object_type,
            'bbox': self.bounding_box,
            'version': self.version,
        }

    def load(self, raw_str: str):
        try:
            data = json.loads(raw_str)

            self.timestamp = data.get('timestamp', 'default_timestamp')
            self.object_id = data.get('id', 'default_id')
            self.object_type = data.get('type', 'default_type')
            self.bounding_box = data.get('bbox', [0, 0, 0, 0])

        except json.JSONDecodeError as e:
            print(f"Failed to decode model message: {e}", file=sys.stderr)
            self.timestamp = 'default_timestamp'
            self.object_id = 'default_id'
            self.object_type = 'default_type'
            self.bounding_box = [0, 0, 0, 0]  # Set default bounding box

        return self  # Ensure that this always returns an object, even if the input is malformed


class ObjectDataMessage:
    global location_id, location_description
    global minio_bucket, minio_file_destination_directory, minio_start_url, minio_credentials_file_path
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
            bucket=minio_bucket, max_size_mb=MAX_FILE_SIZE_IN_MB, json_credentials_file=minio_credentials_file_path)

        self._upload_result = True

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
        # return True
        des = minio_file_destination_directory + '/' + image_path
        self._upload_result = self._file_transfer_handler.uploadFile(
            file_path=image_path, destination=des)

        return self._upload_result

    def createObjectList(self) -> list:

        def createObjectDetail(object_type: ObjectType) -> dict:
            if object_type == ObjectType.HUMAN:
                object_detail = HUMAN_OBJECT_TEMPLATE_DICT.copy()
                object_detail["age"] = -1
                object_detail["gender"] = "unspecified"
            elif object_type == ObjectType.VEHICLE:
                object_detail = VEHICLE_OBJECT_TEMPLATE_DICT.copy()

            return object_detail

        def createBboxDict(raw_object: RawObject) -> dict:
            return {
                "topleftx": raw_object.bounding_box[0],
                "toplefty": raw_object.bounding_box[1],
                "bottomrightx": raw_object.bounding_box[2],
                "bottomrighty": raw_object.bounding_box[3]
            }

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

            object["image_URL"] = minio_start_url + '/' + minio_bucket + '/' + \
                minio_file_destination_directory + '%2F' + \
                raw_object.timestamp + IMAGE_FILE_EXTENSION

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

    def createMessage(self) -> str:
        message = copy.deepcopy(OBJECT_MESSAGE_TEMPLATE_DICT)
        message["message_type"] = "object"

        payload_dict = message["payload"]
        payload_dict["message_id"] = self.createMessageID()
        payload_dict["timestamp"] = self.createTimestamp()

        lat, lon, alt = self.getCurretLocation()
        payload_dict["location"] = self.createLocationObjectDict(
            lat=lat, lon=lon, alt=alt)

        # Check for missing fields, provide default values where necessary
        payload_dict["specs"] = self.createModelSpecs(description=model_description or 'default_model',
                                                      cam_id=camera_id or 'default_cam',
                                                      cam_type=camera_type or 'default_type')

        payload_dict["number_of_objects"] = self._num_of_objects
        # This now contains dicts, not RawObject instances
        payload_dict["object_list"] = self.createObjectList()
        payload_dict["number_of_events"] = self._num_of_events
        payload_dict["event_list"] = self.createEventList()

        try:
            return json.dumps(obj=message, indent=4)
        except Exception as e:
            print(f"[ERROR] Exception during json.dumps: {e}", file=sys.stderr)
            raise


if __name__ == "__main__":
    client = RabbitMQClient(host=amqp_host, port=amqp_port, vhost=amqp_vhost, usr=amqp_username,
                            pwd=amqp_password, model_queue=amqp_model_queue, object_queue=amqp_object_queue)
    client.start()
