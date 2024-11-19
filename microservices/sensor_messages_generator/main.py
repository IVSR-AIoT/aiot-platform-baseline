import paho.mqtt.client as mqtt
import pika
import json
import time
import redis
from dotenv import load_dotenv
import os
from typing import Dict, Type

DOTENV_FILE_PATH = '.env'
MQTT_ALL_TOPICS_WILDCARD = '#'

load_dotenv(dotenv_path=DOTENV_FILE_PATH)

mqtt_host = os.getenv('MQTT_HOST')
mqtt_port = int(os.getenv('MQTT_PORT'))

amqp_host = os.getenv('AMQP_HOST')
amqp_port = int(os.getenv('AMQP_PORT'))
amqp_vhost = os.getenv('AMQP_VIRTUAL_HOST')
amqp_username = os.getenv('AMQP_USERNAME')
amqp_password = os.getenv('AMQP_PASSWORD')

redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_db = os.getenv('REDIS_DB')


class SensorData:
    '''
    Base class for all sensor data.
    '''

    def __init__(self, data: Dict):
        self.data = data

    def __str__(self):
        return f"SensorData: {self.data}"


class PMData(SensorData):
    '''
    Represents particulate matter sensor data.
    '''

    def __init__(self, data: Dict):
        super().__init__(data)
        self.pm1 = data.get("pm1", 0)
        self.pm10 = data.get("pm10", 0)
        self.pm25 = data.get("pm25", 0)

    def __str__(self):
        return f"PMData(pm1={self.pm1}, pm10={self.pm10}, pm25={self.pm25})"


class UVSensorData(SensorData):
    '''
    Represents UV sensor data.
    '''

    def __init__(self, data: Dict):
        super().__init__(data)
        self.raw_value = data.get("raw_value", 0)
        self.uv_intensity = data.get("uv_intensity", 0.0)
        self.voltage = data.get("voltage", 0.0)

    def __str__(self):
        return f"UVSensorData(raw_value={self.raw_value}, uv_intensity={self.uv_intensity}, voltage={self.voltage})"


class CO2SensorData(SensorData):
    '''
    Represents CO2 sensor data.
    '''

    def __init__(self, data: Dict):
        super().__init__(data)
        self.co2 = data.get("co2", 0)
        self.humidity = data.get("humidity", 0.0)
        self.temperature = data.get("temperature", 0.0)

    def __str__(self):
        return f"CO2SensorData(co2={self.co2}, humidity={self.humidity}, temperature={self.temperature})"


class SensorDataFactory:
    '''
    Factory class to create sensor data objects.
    '''
    SENSOR_CLASSES: Dict[str, Type[SensorData]] = {
        "pm": PMData,
        "uv": UVSensorData,
        "co2": CO2SensorData,
    }

    @staticmethod
    def from_dict(data: Dict) -> SensorData:
        '''
        Factory method to create a sensor data object based on the input dictionary.

        The dictionary must contain a 'type' key to indicate the sensor type
        and a 'payload' key with the actual sensor data.

        Parameters:
            data (Dict): Input dictionary with 'type' and 'payload'.

        Returns:
            SensorData: An instance of the appropriate child class.

        Raises:
            ValueError: If the 'type' is missing or not supported.
        '''
        sensor_type = data.get("type")
        payload = data.get("payload")

        if not sensor_type or not payload:
            raise ValueError(
                "Invalid input data. Must contain 'type' and 'payload'.")

        sensor_class = SensorDataFactory.SENSOR_CLASSES.get(sensor_type)
        if not sensor_class:
            raise ValueError(f"Unsupported sensor type: {sensor_type}")

        return sensor_class(payload)

###############################################################################


class MQTTClient:
    def __init__(self, host: str, port: int) -> None:
        '''
        Initializes an instance of the MQTTClient class.

        Sets up the MQTT client with the specified host and port, and assigns
        the on_connect and on_message callback methods.

        Parameters:
            host (str): The hostname or IP address of the MQTT broker.
            port (int): The port number to connect to the MQTT broker.
        '''

        self._host = host
        self._port = port
        self._connection_timeout = 60  # seconds
        self._client = mqtt.Client()
        self._client.on_connect = self.on_connect
        self._client.on_message = self.on_message

        try:
            self._client.connect(self._host, self._port,
                                 self._connection_timeout)
        except ConnectionError as e:
            raise ConnectionError(
                f"Failed to connect to {self._host}:{self._port}") from e

    def on_connect(self, client: mqtt.Client, userdata, flags, rc: int):
        '''
        Handles the event when the MQTT client connects to the broker.

        This function is called when the client receives a CONNACK response
        from the server. It prints the connection result code and subscribes
        the client to all topics.

        Parameters:
            client (paho.mqtt.client.Client): The MQTT client instance.
            userdata (any): The private user data as set in Client() or userdata_set().
            flags (dict): Response flags sent by the broker.
        '''

        print(f"Connected with result code {rc}")
        client.subscribe(MQTT_ALL_TOPICS_WILDCARD)

    def on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        # print(f"Received message: {msg.payload.decode()} on topic {msg.topic}")
        msg_payload = msg.payload.decode()
        self.messageProcessing(msg_str=msg_payload)

    def messageProcessing(self, msg_str: str):
        try:
            msg_dict = json.loads(msg_str)
        except json.JSONDecodeError as e:
            return

        sensor = SensorDataFactory.from_dict(msg_dict)
        print(f"\n{sensor.__class__.__name__}")
        print(sensor)

###############################################################################

###############################################################################


if __name__ == '__main__':
    mqtt_client = MQTTClient(host=mqtt_host, port=mqtt_port)
    mqtt_client._client.loop_forever()
