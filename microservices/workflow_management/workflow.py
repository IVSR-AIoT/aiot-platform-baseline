import pika
import json
import redis
from dotenv import load_dotenv
import os
from enum import Enum

DOTENV_FILE_PATH = '.env'
WORKFLOW_MESSAGE_TYPE = "workflow"

load_dotenv(dotenv_path=DOTENV_FILE_PATH)

cloud_amqp_url = os.getenv('CLOUD_AMQP_URL')
redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_db = os.getenv('REDIS_DB')

device_id = ''


class WorkflowType(Enum):
    DETECTION_RANGE = "detection_range"
    DETECTION_TIMER = "detection_timer"
    SENSOR_LIMIT = "sensor_limit"


def getDataRedis():
    global redis_host, redis_port, redis_db
    global device_id

    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
    try:
        device_id = str(redis_client.get('DEVICE_ID').decode('utf-8'))
    except Exception as e:
        print(f"[EX]: When read data from redis db: {e}")


getDataRedis()


class WorkflowHandler:

    def __init__(self, message_payload: dict, redis_client: redis.Redis):
        self._message_payload = message_payload
        self._workflow_type = self._message_payload["type"]
        self._redis_client = redis_client

    def processing(self):
        if self._workflow_type == WorkflowType.DETECTION_RANGE.value:
            self.detectionRangeHandle()
        elif self._workflow_type == WorkflowType.DETECTION_TIMER.value:
            self.detectionTimerHandle()
        elif self._workflow_type == WorkflowType.SENSOR_LIMIT.value:
            self.sensorLimitHandle()

        print(f"[INFO]: Set workflow parameters successfully")

    def detectionRangeHandle(self):
        points = self._message_payload["list_of_setpoint"]
        points_json = json.dumps(points)
        self._redis_client.set(
            name=WorkflowType.DETECTION_RANGE.value, value=points_json)
        print(f"[INFO]: Detection Polygon: {points_json}")

    def detectionTimerHandle(self):
        seconds = float(self._message_payload["seconds"])
        self._redis_client.set(
            name=WorkflowType.DETECTION_TIMER.value, value=seconds)
        print(f"[INFO]: Detection Timer (seconds): {seconds}")

    def sensorLimitHandle(self):
        sensor_limit_list = self._message_payload["sensor_list"]
        sensor_limit_list_str = json.dumps(sensor_limit_list)
        self._redis_client.set(
            name=WorkflowType.SENSOR_LIMIT.value, value=sensor_limit_list_str)
        print(f"[INFO]: Sensor Limits List: {sensor_limit_list}")


class CloudAMQPClient:

    def __init__(self, amqp_url: str, dev_queue: str,
                 redis_client: redis.Redis):

        self._amqp_url = amqp_url
        self._device_queue = dev_queue
        connection_parameters = pika.URLParameters(self._amqp_url)
        self._connection = pika.BlockingConnection(connection_parameters)
        self._channel = self._connection.channel()

        self._redis_client = redis_client

    def start(self):
        def callback(ch, method, properties, body):
            try:
                raw_message = body.decode()

                message_dict = json.loads(raw_message)
                message_type = message_dict["message_type"]

                if message_type != WORKFLOW_MESSAGE_TYPE:
                    ch.basic_nack(
                        delivery_tag=method.delivery_tag, requeue=True)
                    return

                message_payload = message_dict["payload"]
                workflow_handler = WorkflowHandler(
                    message_payload=message_payload, redis_client=self._redis_client)
                workflow_handler.processing()

                ch.basic_ack(delivery_tag=method.delivery_tag)

            except Exception as e:
                print(f"[Ex]: {e}")

        self._channel.basic_consume(
            queue=self._device_queue, on_message_callback=callback, auto_ack=False
        )

        try:
            self._channel.start_consuming()
        except KeyboardInterrupt:
            print("Exiting...")
            self._connection.close()


if __name__ == "__main__":

    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
    cloud_amqp_client = CloudAMQPClient(
        amqp_url=cloud_amqp_url, dev_queue=device_id, redis_client=redis_client)

    cloud_amqp_client.start()
