import pika
import json
from datetime import datetime
import redis
from dotenv import load_dotenv
import os
import copy
import sys
from enum import Enum

DOTENV_FILE_PATH = '.env'

OBJECT_MESSAGE_TEMPLATE = {}


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

location_id = ""
location_description = ""


def getDataRedis():
    '''
    Fetches location data from a Redis database and assigns it to global variables.

    This function connects to a Redis database using the global variables
    `redis_host`, `redis_port`, and `redis_db` to configure the connection.
    It retrieves the values for "LOCATION_ID" and "LOCATION_DESCRIPTION" keys
    from the Redis database and assigns them to the global variables
    `location_id` and `location_description`, respectively. If any retrieval
    fails, it assigns default values: "-1" for `location_id` and "nil" for
    `location_description`.
    '''
    global redis_host, redis_port, redis_db
    global location_id, location_description
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

    def close(self):
        """Closes the connection to the RabbitMQ broker."""
        if self.connection and not self.connection.is_closed:
            self.connection.close()


class Object:
    '''
    Base class of all object data.
    '''

    def __init__(self, timestamp: str, id: int, type: str, bbox: list):
        self.timestamp = timestamp
        self.object_id = id
        self.object_type = type
        self.bounding_box = bbox
        pass

    # def __str__(self):
    #     return f"Object:{self.data_dict}"

    def load(self, raw_str: str):
        try:
            data = json.loads(raw_str)

            self.timestamp = data['timestamp']
            self.object_id = data['object_id']
            self.object_type = data['object_type']
            self.bounding_box = data['bounding_box']

        except json.JSONDecodeError as e:
            print("Failed to decode model message: {e}", file=sys.stderr)

