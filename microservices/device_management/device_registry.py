import pika
import json
import time
import uuid
import sys
import os
from dotenv import load_dotenv


DEVICE_REGISTRY_MSG_TEM = dict({
    "mac_address": "00:00:00:00:00:00",
    "data": {
        "name": "",
        "description": ""
    }
})

load_dotenv()

# System info
cloud_amqp_url = os.getenv('CLOUD_AMQP_URL')
device_registry_queue = os.getenv('DEVICE_REGISTRY_QUEUE')
accepted_devices_queue = os.getenv('ACCEPTED_DEVICES_QUEUE')
retry_timeout = int(os.getenv('RETRY_TIMEOUT'))


# Device info
MAC_address = os.getenv('MAC_ADDRESS')
if MAC_address is None or MAC_address == '':
    MAC_address = hex(uuid.getnode()).replace('0x', '').upper()
    MAC_address = ':'.join(MAC_address[i:i+2] for i in range(0, 12, 2))
device_name = os.getenv("NAME")
device_description = os.getenv("DESCRIPTION")

# Result
device_id = None
device_heartbeat_duration = 0

stop_condition_met = False


def createChannels():
    '''
    Create channels for device registry and accepted devices.

    Returns:
        tuple: A tuple containing two channel objects for device registry and accepted devices.
    '''

    global cloud_amqp_url, device_registry_queue, accepted_devices_queue

    connection = None
    connection_parameters = pika.URLParameters(url=cloud_amqp_url)
    connection = pika.BlockingConnection(parameters=connection_parameters)

    if connection is None:
        print(
            f"[ERROR] Failed to create connection to RabbitMQ message broker server\n", file=sys.stderr)
        return None, None

    dev_reg_channel = connection.channel()
    dev_reg_channel.queue_declare(queue=device_registry_queue, durable=True)

    acp_dev_channel = connection.channel()
    acp_dev_channel.queue_declare(queue=accepted_devices_queue, durable=True)

    return dev_reg_channel, acp_dev_channel


def generateMessage() -> str:
    """
    Generates a JSON message using the MAC address, device name, and device description.

    Returns:
        str: A JSON-formatted message containing the MAC address, device name, and device description.
    """

    global MAC_address, device_name, device_description

    message_in_dict = DEVICE_REGISTRY_MSG_TEM
    message_in_dict["mac_address"] = MAC_address
    message_in_dict["data"]["name"] = device_name
    message_in_dict["data"]["description"] = device_description

    json_msg = json.dumps(obj=message_in_dict, indent=4)
    return json_msg


def callback(ch, method, properties, body):
    '''
    Listen for incoming messages and process them to get the device ID, and heartbeat duration. Returns True if the MAC address matches, False otherwise.
    '''

    global MAC_address, device_heartbeat_duration, device_id
    global stop_condition_met

    decoded_message = body.decode('utf-8')
    decoded_message = decoded_message.replace("\n", "")

    def getMACAddress(msg: str) -> str:
        data = json.loads(msg)
        this_mac_addr = data.get('mac_address')
        if this_mac_addr:
            print("Current MAC:", this_mac_addr)
            return str(this_mac_addr)
        return None

    def getDeviceID(msg: str) -> str:
        data = json.loads(msg)
        this_dev_id = data.get('device_id')
        if this_dev_id:
            return str(this_dev_id)
        return None

    def getHeartbeatDuration(msg: str) -> int:
        data = json.loads(msg)
        this_hb_dur = data.get('heartbeat_duration')
        if this_hb_dur:
            return int(this_hb_dur)
        return None

    # if getMACAddress() != MAC_address:
    #     return False

    # ch.basic_ack(delivery_tag=method.delivery_tag)
    # device_id = getDeviceID(decoded_message)
    # device_heartbeat_duration = getHeartbeatDuration(decoded_message)

    # return True

    if getMACAddress(decoded_message) == MAC_address:
        print("Message with matching MAC address got, stop consumer...")
        stop_condition_met = True
        ch.stop_consuming()
        ch.basic_ack(delivery_tag=method.delivery_tag)
        print("FOUND")
        return

    ch.basic_ack(delivery_tag=method.delivery_tag)


if __name__ == '__main__':
    device_registry_channel, accepted_devices_channel = createChannels()
    if (device_registry_channel is None) or (accepted_devices_channel is None):
        sys.exit(1)

    # accepted_devices_channel.basic_consume(
    #     queue=accepted_devices_queue,
    #     on_message_callback=callback
    # )

    def consume_with_timeout():
        global retry_timeout
        start_time = time.time()

        while True:
            if time.time() - start_time >= retry_timeout:
                print("Timeout reached, stopping consumer...")
                accepted_devices_channel.stop_consuming()
                break

            accepted_devices_channel._process_data_events(time_limit=1)

            print("CHECKPOINT #1")

            if stop_condition_met:
                print("PASSED")
                sys.exit(0)
                break

    accepted_devices_channel.basic_consume(
        queue=accepted_devices_queue,
        on_message_callback=callback,
        auto_ack=False
    )

    while True:
        device_registry_channel.basic_publish(
            exchange='',
            routing_key=device_registry_queue,
            body=generateMessage()
        )

        consume_with_timeout()

        print("RETRY")
