import pika
import json
import redis
from dotenv import load_dotenv
import os
import copy
from enum import Enum

DOTENV_FILE_PATH = '.env'

NOTIFICATION_MESSAGE_TEMPLATE_DICT = {
    "message_type": "notification",
    "payload": {
        "message_id": str,
        "timestamp": str,
        "location": dict,
        "CAT": str,
        "payload": str,
        "external_messages": [
            {
                "type": str,
                "message_id": str
            },
            {
                "type": str,
                "message_id": str
            }
        ]
    }
}


class CAT(Enum):
    CAT0: 0
    CAT1: 1
    CAT2: 2
    CAT3: 3


class MessageType(Enum):
    OBJECT = "object"
    SENSOR = "sensor"
    NOTIFICATION = "notification"


load_dotenv(dotenv_path=DOTENV_FILE_PATH)

local_amqp_host = os.getenv('LOCAL_AMQP_HOST')
local_amqp_port = int(os.getenv('LOCAL_AMQP_PORT'))
local_amqp_vhost = os.getenv('LOCAL_AMQP_VHOST')
local_amqp_username = os.getenv('LOCAL_AMQP_USERNAME')
local_amqp_password = os.getenv('LOCAL_AMQP_PASSWORD')
local_amqp_object_queue = os.getenv('LOCAL_AMQP_OBJECT_QUEUE')
local_amqp_sensor_queue = os.getenv('LOCAL_AMQP_SENSOR_QUEUE')

cloud_amqp_url = os.getenv('CLOUD_AMQP_URL')

redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_db = os.getenv('REDIS_DB')

device_id = ''
message_count = 0


def getDataRedis():

    global redis_host, redis_port, redis_db
    global device_id

    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
    try:
        device_id = str(redis_client.get('DEVICE_ID').decode('utf-8'))
    except Exception as e:
        print(f"[EX]: When read data from redis db: {e}")


getDataRedis()


class MessageHandler:
    def __init__(self, message_dict: dict):
        self._message_dict = message_dict

        self._message_type = message_dict["message_type"]
        self._message_payload = message_dict["payload"]

        self._message_id = self._message_payload["message_id"]
        self._message_timestamp = self._message_payload["timestamp"]
        self._message_location = self._message_payload["location"]

        self._cat = "CAT0"
        self._payload = "Notification bypass: only detection"

    def objectMessageHandle(self):
        pass

    def sensorMessageHandle(self):
        pass

    def getMessage(self) -> str:
        message = copy.deepcopy(NOTIFICATION_MESSAGE_TEMPLATE_DICT)
        payload_dict = message["payload"]

        def createMessageID() -> str:
            global message_count
            msg_id = "not-" + \
                self._message_location["id"] + \
                '-' + str(message_count).zfill(8)
            message_count += 1
            return msg_id

        payload_dict["message_id"] = createMessageID()
        payload_dict["timestamp"] = self._message_timestamp
        payload_dict["location"] = self._message_location
        payload_dict["CAT"] = self._cat
        payload_dict["payload"] = self._payload

        external_message_list = []
        if self._message_type == MessageType.SENSOR.value:
            return ''
        elif self._message_type == MessageType.OBJECT.value:
            object_dict = {
                "type": MessageType.OBJECT.value,
                "message_id": self._message_id
            }
            external_message_list.append(object_dict)

        payload_dict["external_messages"] = external_message_list

        return json.dumps(message, indent=4)


class CloudAMQPCLient:
    def __init__(self, amqp_url: str, dev_queue: str):
        self.amqp_url = amqp_url
        self.device_queue = dev_queue

        connection_parameters = pika.URLParameters(self.amqp_url)
        connection = pika.BlockingConnection(connection_parameters)
        self.channel = connection.channel()

    def messagePublish(self, message: str) -> bool:
        if len(message) == 0:
            return False
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self.device_queue,
                body=message
            )
            return True
        except Exception as e:
            print(f"[EX] When publish a message to cloud AMQP server: {e}")
            return False


class LocalRabbitMQClient:
    def __init__(self, host: str, port: int, vhost: str,
                 usr: str, pwd: str,
                 obj_queue: str, sen_queue: str,
                 cloud_amqp_url: str, dev_queue: str):
        self.host = host
        self.port = port
        self.virtual_host = vhost
        self.username = usr
        self.password = pwd
        self.object_queue = obj_queue
        self.sensor_queue = sen_queue

        credentials = pika.PlainCredentials(self.username, self.password)
        parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host=self.virtual_host,
            credentials=credentials
        )
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.queue_declare(
            queue=self.object_queue, durable=True)
        self.channel.queue_declare(
            queue=self.sensor_queue, durable=True)

        self.cloud_amqp_client = CloudAMQPCLient(
            amqp_url=cloud_amqp_url, dev_queue=dev_queue)

    def start(self):
        def callback(ch, method, properties, body):
            try:
                raw_message = body.decode()
                object_message_dict = json.loads(raw_message)
                message_handler = MessageHandler(object_message_dict)
                self.cloud_amqp_client.messagePublish(
                    message=raw_message)
                self.cloud_amqp_client.messagePublish(
                    message=message_handler.getMessage())
                print(f"{message_handler.getMessage()}")

            except Exception as e:
                print(f"[Ex]: {e}")
            finally:
                ch.basic_ack(delivery_tag=method.delivery_tag)

        self.channel.basic_consume(
            queue=self.object_queue, on_message_callback=callback, auto_ack=False
        )
        self.channel.basic_consume(
            queue=self.sensor_queue, on_message_callback=callback, auto_ack=False
        )

        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            print("Exiting...")
            self.connection.close()


if __name__ == "__main__":
    local_rabbitmq_client = LocalRabbitMQClient(host=local_amqp_host, port=local_amqp_port, vhost=local_amqp_vhost,
                                                usr=local_amqp_username, pwd=local_amqp_password,
                                                obj_queue=local_amqp_object_queue, sen_queue=local_amqp_sensor_queue,
                                                cloud_amqp_url=cloud_amqp_url, dev_queue=device_id)
    local_rabbitmq_client.start()
