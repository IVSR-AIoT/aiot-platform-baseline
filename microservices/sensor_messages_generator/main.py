import paho.mqtt.client as mqtt
import pika
import json
from datetime import datetime
import redis
from dotenv import load_dotenv
import os
from typing import Dict, Type
import copy
import sys

DOTENV_FILE_PATH = '.env'
MQTT_ALL_TOPICS_WILDCARD = '#'
SUB_ADD = ': '

SENSOR_OBJECT_TEMPLATE_DICT = {
    "id": str,
    "name": str,
    "description": str,
    "unit": str,
    "payload": int | float | list
}

LOCATION_TEMPLATE_DICT = {
    "id": str,
    "lat": float,
    "lon": float,
    "alt": float,
    "description": str
}

SENSOR_DATA_MESSAGE_TEMPLATE_DICT = {
    "message_type": "sensor",
    "payload": {
        "message_id": str,
        "timestamp": str,
        "location": LOCATION_TEMPLATE_DICT,
        "number_of_sensors": int,
        "sensor_list": list
    }
}

load_dotenv(dotenv_path=DOTENV_FILE_PATH)

mqtt_host = os.getenv('MQTT_HOST')
mqtt_port = int(os.getenv('MQTT_PORT'))

amqp_host = os.getenv('AMQP_HOST')
amqp_port = int(os.getenv('AMQP_PORT'))
amqp_vhost = os.getenv('AMQP_VIRTUAL_HOST')
amqp_username = os.getenv('AMQP_USERNAME')
amqp_password = os.getenv('AMQP_PASSWORD')
amqp_sensor_queue = os.getenv('AMQP_SENSOR_QUEUE')

redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_db = os.getenv('REDIS_DB')

number_of_sensors = int(os.getenv('NUMBER_OF_SENSORS'))

location_id = ""
location_description = ""
message_count = 0


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


class SensorData:
    '''
    Base class for all sensor data.
    '''

    def __init__(self, data=Dict):
        self.data = data
        self.num_values = 0

    def __str__(self):
        return f"SensorData: {self.data}"

    def complete(self):
        """
        Completes the object by setting the name and description
        attributes to predefined values specific to the sensor.
        """
        pass

    def getValuesList(self, start_id: int) -> list:
        """
        Generates a list of dictionaries representing sensor data.

        Each dictionary contains an ID, name, description, unit, and payload for a specific
        particulate matter sensor reading. The IDs are sequentially generated starting from
        the given start_id.

        Args:
            start_id (int): The starting ID for the sensor data entries.

        Returns:
            list: A list of dictionaries, each representing a sensor data entry.
        """
        pass


class PMSensorData(SensorData):
    '''
    Represents particulate matter sensor data.
    '''

    def __init__(self, data={}, name="name", description="description"):
        super().__init__(data)
        self.pm1 = data.get("pm1", 0)
        self.pm10 = data.get("pm10", 0)
        self.pm25 = data.get("pm25", 0)
        self.name = name
        self.description = description
        self.num_values = 3

    def __str__(self):
        return f"PMSensorData (pm1={self.pm1}, pm10={self.pm10}, pm25={self.pm25})"

    def complete(self):
        self.name = "PMS5004 sensor"
        self.description = "PMS5003 sensor: PM 1.0, PM 2.5 and PM 10"

    def getValuesList(self, start_id: int) -> list:

        pm1_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        pm1_dict["id"] = str(start_id).zfill(4)
        pm1_dict["name"] = str(self.name + SUB_ADD + "pm1")
        pm1_dict["description"] = str(self.description + SUB_ADD + "pm1")
        pm1_dict["unit"] = "ug/m3"
        pm1_dict["payload"] = self.pm1

        pm25_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        pm25_dict["id"] = str(start_id + 1).zfill(4)
        pm25_dict["name"] = str(self.name + SUB_ADD + "pm2.5")
        pm25_dict["description"] = str(self.description + SUB_ADD + "pm2.5")
        pm25_dict["unit"] = "ug/m3"
        pm25_dict["payload"] = self.pm25

        pm10_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        pm10_dict["id"] = str(start_id + 2).zfill(4)
        pm10_dict["name"] = str(self.name + SUB_ADD + "pm10")
        pm10_dict["description"] = str(self.description + SUB_ADD + "pm10")
        pm10_dict["unit"] = "ug/m3"
        pm10_dict["payload"] = self.pm10

        result = [pm1_dict, pm25_dict, pm10_dict]
        return result


class UVSensorData(SensorData):
    '''
    Represents UV sensor data.
    '''

    def __init__(self, data={}, name="name", description="description"):
        super().__init__(data)
        self.raw_value = data.get("raw_value", 0)
        self.uv_intensity = data.get("uv_intensity", 0.0)
        self.voltage = data.get("voltage", 0.0)
        self.name = name
        self.description = description
        self.num_values = 3

    def __str__(self):
        return f"UVSensorData(raw_value={self.raw_value}, uv_intensity={self.uv_intensity}, voltage={self.voltage})"

    def complete(self):
        self.name = "GUVA-S12SD sensor"
        self.description = "GUVA-S12SD sensor: UV intensity with voltage and raw digital value"

    def getValuesList(self, start_id: int) -> list:

        intensity_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        intensity_dict["id"] = str(start_id).zfill(4)
        intensity_dict["name"] = str(self.name + SUB_ADD + "uv intensity")
        intensity_dict["description"] = str(
            self.description + SUB_ADD + "uv intensity")
        intensity_dict["unit"] = "mW/cm2"
        intensity_dict["payload"] = self.uv_intensity

        raw_value_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        raw_value_dict["id"] = str(start_id + 1).zfill(4)
        raw_value_dict["name"] = str(self.name + SUB_ADD + "raw digital value")
        raw_value_dict["description"] = str(
            self.description + SUB_ADD + "digital raw value")
        raw_value_dict["unit"] = ""
        raw_value_dict["payload"] = self.raw_value

        voltage_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        voltage_dict["id"] = str(start_id + 2).zfill(4)
        voltage_dict["name"] = str(self.name + SUB_ADD + "voltage")
        voltage_dict["description"] = str(
            self.description + SUB_ADD + "voltage")
        voltage_dict["unit"] = "volt"
        voltage_dict["payload"] = self.voltage

        result = [intensity_dict, raw_value_dict, voltage_dict]
        return result


class CO2SensorData(SensorData):
    '''
    Represents CO2 sensor data.
    '''

    def __init__(self, data={}, name="name", description="description"):
        super().__init__(data)
        self.co2 = data.get("co2", 0)
        self.humidity = data.get("humidity", 0.0)
        self.temperature = data.get("temperature", 0.0)
        self.name = name
        self.description = description
        self.num_values = 3

    def __str__(self):
        return f"CO2SensorData(co2={self.co2}, humidity={self.humidity}, temperature={self.temperature})"

    def complete(self):
        self.name = "SCD41 sensor"
        self.description = "SCD41 sensor: CO2, temperature and humidity"

    def getValuesList(self, start_id: int) -> list:

        co2_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        co2_dict["id"] = str(start_id).zfill(4)
        co2_dict["name"] = str(self.name + SUB_ADD + "co2")
        co2_dict["description"] = str(self.description + SUB_ADD + "co2")
        co2_dict["unit"] = "ppm"
        co2_dict["payload"] = self.co2

        temp_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        temp_dict["id"] = str(start_id + 1).zfill(4)
        temp_dict["name"] = str(self.name + SUB_ADD + "temperature")
        temp_dict["description"] = str(
            self.description + SUB_ADD + "temperature")
        temp_dict["unit"] = "degree C"
        temp_dict["payload"] = self.temperature

        humi_dict = copy.deepcopy(SENSOR_OBJECT_TEMPLATE_DICT)
        humi_dict["id"] = str(start_id + 2).zfill(4)
        humi_dict["name"] = str(self.name + SUB_ADD + "humidity")
        humi_dict["description"] = str(self.description + SUB_ADD + "humidity")
        humi_dict["unit"] = "percentage"
        humi_dict["payload"] = self.humidity

        result = [co2_dict, temp_dict, humi_dict]
        return result


class SensorDataFactory:
    '''
    Factory class to create sensor data objects.
    '''
    SENSOR_CLASSES: Dict[str, Type[SensorData]] = {
        "pm": PMSensorData,
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


class SensorDataMessage:
    global location_id, location_description
    global message_count

    def __init__(self, num_of_sensors: int) -> None:
        self._sensors_data_dict = {}
        self._num_of_sensors = num_of_sensors
        self._message_template_dict = copy.deepcopy(
            SENSOR_DATA_MESSAGE_TEMPLATE_DICT)
        self._count = 0

    def appendSensor(self, sensor: SensorData):
        """
        Adds a SensorData object to the internal sensors data dictionary.

        The sensor is stored in the dictionary with its class name as the key.

        Args:
            sensor (SensorData): The sensor data object to be added.
        """

        sensor_class = sensor.__class__.__name__
        self._sensors_data_dict[sensor_class] = sensor

    def isFull(self) -> bool:
        return self._num_of_sensors == len(self._sensors_data_dict)

    def getCurrentLocation(self):
        return 0, 0, 0

    def createMessage(self):
        """
        Creates a sensor data message if the sensor list is full.

        This method generates a message dictionary based on the 
        SENSOR_DATA_MESSAGE_TEMPLATE_DICT, populates it with the 
        current sensor data, and returns it as a JSON string.

        Returns:
            tuple: A tuple containing a boolean indicating success 
            and the JSON string of the message. Returns (False, '') 
            if the sensor list is not full.
        """

        if not self.isFull():
            return False, ''

        message_dict = copy.deepcopy(SENSOR_DATA_MESSAGE_TEMPLATE_DICT)

        def createMessageID() -> str:
            global message_count
            msg_id = "sen-" + \
                location_id.zfill(4) + '-' + str(message_count).zfill(8)
            message_count += 1
            return msg_id

        def updatePayload() -> None:
            payload = message_dict["payload"]

            payload["message_id"] = createMessageID()

            payload["timestamp"] = datetime.now().isoformat()

            lat, lon, alt = self.getCurrentLocation()
            payload["location"] = self.createLocationObjectDict(lat, lon, alt)

            n_o_s = 0
            for key, sensor in self._sensors_data_dict.items():
                n_o_s += sensor.num_values
            payload["number_of_sensors"] = int(n_o_s)

            values_list = []
            for key, sensor in self._sensors_data_dict.items():
                curr_list = sensor.getValuesList(start_id=self._count)
                values_list.extend(curr_list)
                self._count += sensor.num_values
            payload["sensor_list"] = values_list

        updatePayload()

        message = json.dumps(message_dict, indent=4)
        return True, message

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


class SimpleRabbitMQPublisher:
    def __init__(
            self,
            host: str, port: int, virtual_host: str,
            username: str, password: str, queue: str):
        """
        Initializes the RabbitMQ publisher with the provided connection parameters.

        :param host: The hostname or IP address of the RabbitMQ broker.
        :param port: The port number to connect to the RabbitMQ broker.
        :param virtual_host: The virtual host to use when connecting.
        :param username: The username for authentication.
        :param password: The password for authentication.
        """
        credentials = pika.PlainCredentials(username, password)
        parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host=virtual_host,
            credentials=credentials
        )
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.queue = queue
        self.channel.queue_declare(queue=self.queue, durable=True)

    def publish(self, message: str | dict) -> bool:
        try:
            if isinstance(message, dict):
                message_body = json.dumps(obj=message)
            else:
                message_body = message
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queue,
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


rabbitmq_publisher = SimpleRabbitMQPublisher(
    host=amqp_host, port=amqp_port, virtual_host=amqp_vhost,
    username=amqp_username, password=amqp_password, queue=amqp_sensor_queue)


class MQTTClient:
    global number_of_sensors
    global rabbitmq_publisher

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
        self._sensor_message = SensorDataMessage(
            num_of_sensors=number_of_sensors)

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
        """
        Handles incoming MQTT messages.

        Decodes the payload of the received message and processes it
        using the messageProcessing method.

        Parameters:
            client (paho.mqtt.client.Client): The MQTT client instance.
            userdata (any): The private user data as set in Client() or userdata_set().
            msg (paho.mqtt.client.MQTTMessage): The message instance containing
            the topic and payload.
        """

        msg_payload = msg.payload.decode()
        self.messageProcessing(msg_str=msg_payload)

    def messageProcessing(self, msg_str: str):
        try:
            msg_dict = json.loads(msg_str)
        except json.JSONDecodeError as e:
            return

        sensor = SensorDataFactory.from_dict(msg_dict)
        sensor.complete()

        self._sensor_message.appendSensor(sensor=sensor)
        result, message = self._sensor_message.createMessage()
        if result:
            rabbitmq_publisher.publish(message=message)
            self._sensor_message = SensorDataMessage(
                num_of_sensors=number_of_sensors)

###############################################################################


###############################################################################

if __name__ == '__main__':
    mqtt_client = MQTTClient(host=mqtt_host, port=mqtt_port)
    mqtt_client._client.loop_forever()
