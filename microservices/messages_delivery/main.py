import pika
import json
import redis
from dotenv import load_dotenv
import os
import copy
from enum import Enum
import time
import paho.mqtt.client as mqtt

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

workflow_configuration = {"detection_timer": 10}
sensor_limit_list = []

redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_db = os.getenv('REDIS_DB')

mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
mqtt_port = int(os.getenv("MQTT_PORT", 1883))
mqtt_topic = os.getenv("MQTT_TOPIC", "/alert")

device_id = ''
message_count = 0


def getWorkflowConfiguration(redis_client: redis.Redis):

    global workflow_configuration, sensor_limit_dict

    try:
        workflow_configuration["detection_timer"] = float(
            redis_client.get('detection_timer').decode('utf-8'))

    except Exception as e:
        print(f"[EX]: When read data from redis db: {e}")

    try:
        sensor_limit_str = str(redis_client.get(
            'sensor_limit').decode('utf-8'))
        sensor_limit_dict = json.loads(sensor_limit_str)

    except Exception as e:
        print(f"[EX]: When read data from redis db: {e}")


def getDataRedis():

    global redis_host, redis_port, redis_db
    global device_id

    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
    try:
        device_id = str(redis_client.get('DEVICE_ID').decode('utf-8'))
    except Exception as e:
        print(f"[EX]: When read data from redis db: {e}")

    getWorkflowConfiguration(redis_client=redis_client)


getDataRedis()


class AlertPublisher:

    global mqtt_broker, mqtt_port, mqtt_topic

    def __init__(self):
        self._client = mqtt.Client()
        self._client.on_connect = self.on_connect
        self.connectMQTT()

    def connectMQTT(self):
        """
        Connects to the MQTT broker.
        """
        print(f"Connecting to MQTT broker at {mqtt_broker}:{mqtt_port}")
        self._client.connect(mqtt_broker, mqtt_port, 60)

    def on_connect(self, client, userdata, flags, rc):
        """
        Callback function when MQTT client connects to broker.
        """
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print(f"Failed to connect to MQTT Broker, return code {rc}")

    def publishAlert(self):
        """
        Publish a message with payload "1" to the configured MQTT topic.
        """
        result = self._client.publish(mqtt_topic, "1")
        # Optionally, you could check the result here:
        status = result[0]
        if status == 0:
            print(f"Message sent to topic `{mqtt_topic}`")
        else:
            print(f"Failed to send message to topic `{mqtt_topic}`")


class SensorHandler:

    def __init__(self, sensor_limits: dict):

        self._sensor_limits_dict = {sensor['sensor_name']: (float(
            sensor['lower_limit']), float(sensor['upper_limit'])) for sensor in sensor_limits}
        self._invalid_sensor_list = []

        print(self._sensor_limits_dict)

    def processing(self, sensor_data_list: list):
        for sensor_data in sensor_data_list:
            sensor_name = str(sensor_data["name"])
            sensor_value = float(sensor_data["payload"])
            limit_tuple_of_this_sensor = self._sensor_limits_dict.get(
                sensor_name)
            if limit_tuple_of_this_sensor is None:
                continue
            elif sensor_value < limit_tuple_of_this_sensor[0] or sensor_value > limit_tuple_of_this_sensor[1]:
                self._invalid_sensor_list.append(sensor_name)

    def getInvalidSensorData(self, sensor_data_list: list) -> list:

        self.processing(sensor_data_list=sensor_data_list)
        return self._invalid_sensor_list


class TimerHandler:

    def __init__(self, duration: float):
        """Initialize with a fixed duration in seconds."""

        self.duration = duration  # Fixed amount of time (in seconds)
        self.start_time = None
        self.is_first_time = True  # First time, always True

    def setStartTime(self):
        """Set the current time as the start time."""

        self.start_time = time.time()

    def hasElapsed(self):
        """Check if the fixed duration has passed since start time.
        Resets start time after checking.
        """

        if (self.is_first_time):
            self.is_first_time = False
            self.setStartTime()
            return True

        if self.start_time is None:
            raise ValueError(
                "Start time is not set. Call setStartTime() first.")

        elapsed = time.time() - self.start_time

        if elapsed >= self.duration:
            # Reset the start time for the next use
            self.setStartTime()
            return True
        else:
            return False


class MessageHandler:

    global workflow_configuration, sensor_limit_list

    def __init__(self, message_dict: dict):
        self._message_dict = message_dict

        self._message_type = message_dict["message_type"]
        self._message_payload = message_dict["payload"]

        self._message_id = self._message_payload["message_id"]
        self._message_timestamp = self._message_payload["timestamp"]
        self._message_location = self._message_payload["location"]

        self._sensor_handler = SensorHandler(sensor_limits=sensor_limit_dict)
        self._is_object = False
        self._is_sensor = False

        self._cat = "CAT0"

    def objectMessageHandle(self) -> str:

        self._is_object = True

        model_specs = self._message_payload["specs"]
        model_description = model_specs["description"]

        return f"Detection meet the requirements (Model: {model_description})"

    def sensorMessageHandle(self) -> str:

        self._is_sensor = True
        out_of_range_sensor_data: list = self._sensor_handler.getInvalidSensorData(
            self._sensor_list)

        if len(out_of_range_sensor_data) == 0:
            return ""

        msg = "Sensor value exceeds pre-set threshold: " + \
            str(out_of_range_sensor_data)

        alert = AlertPublisher()
        alert.publishAlert()

        return msg

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

        if self._message_type == "sensor":
            self._sensor_list = self._message_payload["sensor_list"]
            msg_payload = self.sensorMessageHandle()
            if msg_payload == "":
                return ""
            payload_dict["payload"] = msg_payload
        elif self._message_type == "object":
            payload_dict["payload"] = self.objectMessageHandle()

        external_message_list = []
        if self._is_sensor:
            sensor_dict = {
                "type": MessageType.SENSOR.value,
                "message_id": self._message_id
            }
            external_message_list.append(sensor_dict)
        elif self._is_object:
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
            print(f"Published: {message}")
            return True
        except Exception as e:
            print(f"[EX] When publish a message to cloud AMQP server: {e}")
            return False

    def displayMessage(self, message: str) -> bool:
        if len(message) == 0:
            return False
        print(f"Publish this message:\n{message}")


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

        self._timer = TimerHandler(
            duration=workflow_configuration["detection_timer"])

    def start(self):
        def callback(ch, method, properties, body):
            try:
                raw_message = body.decode()

                message_dict = json.loads(raw_message)
                message_type = message_dict["message_type"]

                if message_type is not None:
                    getDataRedis()
                    print(f"Arrived message: {message_type}")

                if message_type == "object":
                    if not self._timer.hasElapsed():
                        return

                message_handler = MessageHandler(message_dict)
                self.cloud_amqp_client.messagePublish(
                    message=raw_message)
                self.cloud_amqp_client.messagePublish(
                    message=message_handler.getMessage())

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
