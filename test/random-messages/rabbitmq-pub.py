import pika
import time
import json
import sys
from enum import Enum

is_cloud = False
local_username = 'aiot'
local_password = 'ivsr@2019'
local_host = '192.168.0.112'

cloud_amqp_url = ''
OBJECT_MSG_QUEUE_NAME = 'object'
SENSOR_MSG_QUEUE_NAME = 'sensor'
NOTIFICATION_MSG_QUEUE_NAME = 'notification'


class MessageType(Enum):
    OBJECT = 1
    SENSOR = 2
    NOTIFICATION = 3


class MessageTemplate:
    OBJECT_MSG_TEM = dict({
        "message_id": "sen-0000-00000000",
        "timestamp": "2023-12-25T07:38:42.491",
        "location": {
            "id": "0000",
            "lat": 21.005453,
            "lon": 105.8451935,
            "alt": 48.15574793,
            "description": "ROOM E-722s"
        },
        "number_of_sensors": 6,
        "sensor_list": [
            {
                "id": "0000",
                "name": "max30102-spo2",
                "description": "MAX30102 - Blood Oxygen Saturation",
                "unit": "percentage",
                "payload": 98.45
            },
            {
                "id": "0001",
                "name": "max30102-hr",
                "description": "MAX30102 - Heart-rate",
                "unit": "RPM",
                "payload": 80
            },
            {
                "id": "0002",
                "name": "gy91-mpu9250",
                "description": "MPU9250 - IMU",
                "unit": "",
                "payload": [
                    [
                        -0.047000,
                        0.024000,
                        9.820000
                    ],
                    [
                        0.140000,
                        0.320000,
                        0.300000
                    ],
                    [
                        26.800000,
                        -22.040000,
                        52.100000
                    ]
                ]
            },
            {
                "id": "0003",
                "name": "gy91-bmp280-temp",
                "description": "BMP280 - Temperature",
                "unit": "C",
                "payload": 24.5
            },
            {
                "id": "0004",
                "name": "gy91-bmp280-pres",
                "description": "BMP280 - Pressure",
                "unit": "hPA",
                "payload": 1017.4
            },
            {
                "id": "0005",
                "name": "gy91-bmp280-alt",
                "description": "BMP280 - Altitude",
                "unit": "meter",
                "payload": 81.01
            }
        ]
    })
    SENSOR_MSG_TEM = dict({
        "message_id": "sen-0000-00000000",
        "timestamp": "2023-12-25T07:38:42.491",
        "location": {
            "id": "0000",
            "lat": 21.005453,
            "lon": 105.8451935,
            "alt": 48.15574793,
            "description": "ROOM E-722s"
        },
        "number_of_sensors": 6,
        "sensor_list": [
            {
                "id": "0000",
                "name": "max30102-spo2",
                "description": "MAX30102 - Blood Oxygen Saturation",
                "unit": "percentage",
                "payload": 98.45
            },
            {
                "id": "0001",
                "name": "max30102-hr",
                "description": "MAX30102 - Heart-rate",
                "unit": "RPM",
                "payload": 80
            },
            {
                "id": "0002",
                "name": "gy91-mpu9250",
                "description": "MPU9250 - IMU",
                "unit": "",
                "payload": [
                    [
                        -0.047000,
                        0.024000,
                        9.820000
                    ],
                    [
                        0.140000,
                        0.320000,
                        0.300000
                    ],
                    [
                        26.800000,
                        -22.040000,
                        52.100000
                    ]
                ]
            },
            {
                "id": "0003",
                "name": "gy91-bmp280-temp",
                "description": "BMP280 - Temperature",
                "unit": "C",
                "payload": 24.5
            },
            {
                "id": "0004",
                "name": "gy91-bmp280-pres",
                "description": "BMP280 - Pressure",
                "unit": "hPA",
                "payload": 1017.4
            },
            {
                "id": "0005",
                "name": "gy91-bmp280-alt",
                "description": "BMP280 - Altitude",
                "unit": "meter",
                "payload": 81.01
            }
        ]
    })
    NOTIFICATION_MSG_TEM = dict({
        "message_id": "not-0000-00000000",
        "timestamp": "2023-12-25T07:38:42.491",
        "location": {
            "id": "0000",
            "lat": 21.005453,
            "lon": 105.8451935,
            "alt": 48.15574793,
            "description": "ROOM E-722"
        },
        "CAT": "CAT0",
        "payload": "[ALERT] example",
        "external_messages": [
            {
                "type": "object",
                "message_id": "obj-0000-00000000"
            },
            {
                "type": "sensor",
                "message_id": "sen-0000-000000000"
            }
        ]
    })


def generateMessage(type) -> str:
    '''
    Generate a message based on the given type.

    :param type: The type of message to generate (OBJECT, SENSOR, NOTIFICATION).
    :type type: MessageType

    :return: The generated message as a string.
    :rtype: str
    '''

    def generateObjectMessage() -> str:
        original_message = json.dumps(
            obj=MessageTemplate.OBJECT_MSG_TEM, indent=None)  # None for compact, 4 for human-readable format
        return original_message

    def generateSensorMessage() -> str:
        original_message = json.dumps(
            obj=MessageTemplate.SENSOR_MSG_TEM, indent=None)
        return original_message

    def generateNotificationMessage() -> str:
        original_message = json.dumps(
            obj=MessageTemplate.NOTIFICATION_MSG_TEM, indent=None)
        return original_message

    if type == MessageType.OBJECT:
        return generateObjectMessage()
    if type == MessageType.SENSOR:
        return generateSensorMessage()
    if type == MessageType.NOTIFICATION():
        return generateNotificationMessage()
    return ''


def createChannels(is_cloud: bool):
    '''
    Create a connection to RabbitMQ based on the environment type.

    :param is_cloud: A boolean indicating whether to connect to a cloud-based RabbitMQ instance.

    :return: A tuple of pika.Channel objects for object, sensor, and notification queues.
    '''

    connection = None

    if not is_cloud:
        global local_username, local_password, local_host
        credentials = pika.PlainCredentials(
            username=local_username, password=local_password)
        connection_parameters = pika.ConnectionParameters(
            host=local_host,
            port=5672,
            virtual_host='/',
            credentials=credentials
        )
        connection = pika.BlockingConnection(connection_parameters)
    else:
        global cloud_amqp_url
        connection_parameters = pika.URLParameters(url=cloud_amqp_url)
        connection = pika.BlockingConnection(parameters=connection_parameters)

    if connection is None:
        print(
            f"[ERROR] Failed to create connection to RabbitMQ message broker server\n", file=sys.stderr)
        return None, None, None

    obj_channel = connection.channel()
    obj_channel.queue_declare(queue=OBJECT_MSG_QUEUE_NAME, durable=True)
    sen_channel = connection.channel()
    sen_channel.queue_declare(queue=SENSOR_MSG_QUEUE_NAME, durable=True)
    not_channel = connection.channel()
    not_channel.queue_declare(queue=NOTIFICATION_MSG_QUEUE_NAME, durable=True)

    return obj_channel, sen_channel, not_channel


if __name__ == '__main__':
    obj_channel, sen_channel, not_channel = createChannels(is_cloud=False)
    if (obj_channel is not None) and (sen_channel is not None) and (not_channel is not None):
        print(f"[INFO] Successfully created 3 channels for 3 queues\n",
              file=sys.stdout)

    print(f"{generateMessage(MessageType.OBJECT)}")
