import pika
from datetime import datetime, timezone
import time
import json
import sys
from enum import Enum
import random

is_cloud = False
local_username = 'aiot'
local_password = 'ivsr@2019'
local_host = '192.168.0.112'

cloud_amqp_url = 'amqps://lylwzvfg:wdwjwIBl3UfCNglKQ6xXejn1PG0_9hg4@armadillo.rmq.cloudamqp.com/lylwzvfg'
OBJECT_MSG_QUEUE_NAME = 'object'
SENSOR_MSG_QUEUE_NAME = 'sensor'
NOTIFICATION_MSG_QUEUE_NAME = 'notification'


class MessageType(Enum):
    OBJECT = 1
    SENSOR = 2
    NOTIFICATION = 3


class MessageTemplate:
    OBJECT_MSG_TEM = dict({
        "message_id": "obj-0000-00000000",
        "timestamp": "2023-12-25T07:38:42.491",
        "location": {
            "id": "0000",
            "lat": 21.005453,
            "lon": 105.8451935,
            "alt": 48.15574793,
            "description": "ROOM E-722"
        },
        "specs": {
            "description": "Human and Vehicle detection",
            "camera": {
                "id": "0001",
                "type": "RGB"
            }
        },
        "number_of_objects": 3,
        "object_list": [
            {
                "Human": {
                    "id": "01",
                    "gender": "Male",
                    "age": "20",
                    "bbox": {
                        "topleftx": 32,
                        "toplefty": 0,
                        "bottomrightx": 177,
                        "bottomrighty": 0
                    },
                    "image_URL": "https://picsum.photos/1280/720"
                }
            },
            {
                "Human": {
                    "id": "02",
                    "gender": "Female",
                    "age": "30",
                    "bbox": {
                        "topleftx": 35,
                        "toplefty": 0,
                        "bottomrightx": 145,
                        "bottomrighty": 0
                    }
                },
                "image_URL": "https://picsum.photos/1280/720"
            },
            {
                "Vehicle": {
                    "id": "03",
                    "type": "Personal car",
                    "brand": "BMW",
                    "color": "Black",
                    "Licence": "29A-12345",
                    "bbox": {
                        "topleftx": 345,
                        "toplefty": 0,
                        "bottomrightx": 108,
                        "bottomrighty": 20
                    },
                    "image_URL": "https://picsum.photos/1280/720"
                }
            }
        ],
        "number_of_events": 2,
        "event_list": [
            {
                "human_event": {
                    "object_id": "01",
                    "action": "EVENT_HUMAN_RUN",
                    "video_URL": "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4"
                },
                "vehicle_event": {
                    "object_id": "03",
                    "action": "EVENT_VEHICLE_PARK",
                    "video_URL": "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_2mb.mp4"
                }
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


def generateMessage(type, id: int) -> str:
    '''
    Generate a message based on the given type.

    :param type: The type of message to generate (OBJECT, SENSOR, NOTIFICATION).
    :type type: MessageType

    :return: The generated message as a string.
    :rtype: str
    '''

    def generateObjectMessage(id: int) -> str:
        message_in_dict = MessageTemplate.OBJECT_MSG_TEM
        message_in_dict["message_id"] = "obj-0000-" + str(id).zfill(8)
        message_in_dict["timestamp"] = datetime.now(
            timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

        # None for compact, 4 for human-readable format
        json_message = json.dumps(obj=message_in_dict, indent=4)
        return json_message

    def generateSensorMessage(id: int) -> str:
        message_in_dict = MessageTemplate.SENSOR_MSG_TEM
        message_in_dict["message_id"] = "sen-0000-" + str(id).zfill(8)
        message_in_dict["timestamp"] = datetime.now(
            timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

        def update_sensor_payloads(sensor_list):
            for sensor in sensor_list:
                if sensor["name"] == "max30102-spo2":
                    # Update payload to a random float between 90 and 100, with 2 digits after the decimal point
                    sensor["payload"] = round(random.uniform(90, 100), 2)
                elif sensor["name"] == "max30102-hr":
                    # Update payload to a random integer between 60 and 150
                    sensor["payload"] = random.randint(60, 150)
        update_sensor_payloads(message_in_dict["sensor_list"])

        # None for compact, 4 for human-readable format
        json_message = json.dumps(obj=message_in_dict, indent=4)
        return json_message

    def generateNotificationMessage(id: int) -> str:
        message_in_dict = MessageTemplate.NOTIFICATION_MSG_TEM
        message_in_dict["message_id"] = "not-0000-" + str(id).zfill(8)
        message_in_dict["timestamp"] = datetime.now(
            timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        message_in_dict["CAT"] = "CAT" + str(random.randint(0, 5))

        def update_external_messages(external_message_list):
            object_msg = external_message_list[0]
            object_msg["message_id"] = "obj-0000-" + str(id).zfill(8)
            sensor_msg = external_message_list[1]
            sensor_msg["message_id"] = "sen-0000-" + str(id).zfill(8)
        update_external_messages(message_in_dict["external_messages"])

        # None for compact, 4 for human-readable format
        json_message = json.dumps(obj=message_in_dict, indent=4)
        return json_message

    if type == MessageType.OBJECT:
        return generateObjectMessage(id=id)
    if type == MessageType.SENSOR:
        return generateSensorMessage(id=id)
    if type == MessageType.NOTIFICATION:
        return generateNotificationMessage(id=id)
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
    obj_channel, sen_channel, not_channel = createChannels(is_cloud=True)
    if (obj_channel is not None) and (sen_channel is not None) and (not_channel is not None):
        print(f"[INFO] Successfully created 3 channels for 3 queues\n",
              file=sys.stdout)

    for id in range(0, 10):
        obj_channel.basic_publish(
            exchange='',
            routing_key=OBJECT_MSG_QUEUE_NAME,
            body=generateMessage(MessageType.OBJECT, id=id)
        )
        sen_channel.basic_publish(
            exchange='',
            routing_key=SENSOR_MSG_QUEUE_NAME,
            body=generateMessage(MessageType.SENSOR, id=id))
        not_channel.basic_publish(
            exchange='',
            routing_key=NOTIFICATION_MSG_QUEUE_NAME,
            body=generateMessage(MessageType.NOTIFICATION, id=id)
        )

        random_sleep_duration = round(random.uniform(0, 1), 2)
        time.sleep(float(random_sleep_duration))
