import pika
import json
import time
import uuid
import sys
import os
import redis
from dotenv import load_dotenv, set_key

# Template for the device registry message
DEVICE_REGISTRY_MSG_TEM = {
    "mac_address": "00:00:00:00:00:00",
    "data": {
        "name": "",
        "description": ""
    }
}

# Path to the .env file and the keys used within it
DOTENV_FILE_PATH = ".env"
DOTENV_KEY_DEVICE_ID = 'DEVICE_ID'
DOTENV_KEY_HEARTBEAT_DURATION = 'HEARTBEAT_DURATION'

REDIS_KEY_DEVICE_ID = DOTENV_KEY_DEVICE_ID
REDIS_KEY_HEARTBEAT_DURATION = DOTENV_KEY_HEARTBEAT_DURATION
REDIS_KEY_MAC_ADDRESS = 'MAC_ADDRESS'

# Load environment variables from the specified .env file
load_dotenv(dotenv_path=DOTENV_FILE_PATH)

# Retrieve system configuration from environment variables
# AMQP URL for RabbitMQ connection
cloud_amqp_url = os.getenv('CLOUD_AMQP_URL')
# Queue name for device registration
device_registry_queue = os.getenv('DEVICE_REGISTRY_QUEUE')
# Queue name for accepted devices
accepted_devices_queue = os.getenv('ACCEPTED_DEVICES_QUEUE')
# Timeout duration for retries
retry_timeout = int(os.getenv('RETRY_TIMEOUT'))

# Redis configurations
redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_db = int(os.getenv('REDIS_DB'))


def updateENV(key: str, value: str) -> None:
    """
    Update the .env file with a given key-value pair.

    Args:
        key (str): The key to update in the .env file.
        value (str): The value to set for the key.
    """
    global DOTENV_FILE_PATH
    set_key(dotenv_path=DOTENV_FILE_PATH, key_to_set=key, value_to_set=value)


# Retrieve device information from environment variables
MAC_address = os.getenv('MAC_ADDRESS')
if MAC_address is None or MAC_address == '':
    # Generate the MAC address from the UUID if not provided
    MAC_address = hex(uuid.getnode()).replace('0x', '').upper()
    MAC_address = ':'.join(MAC_address[i:i+2] for i in range(0, 12, 2))
print(f"My MAC: {MAC_address}")
device_name = os.getenv("NAME")               # Device name
device_description = os.getenv("DESCRIPTION")  # Device description

# Initialize result variables
device_id = None                      # Will store the device ID assigned by the server
# Will store the heartbeat duration assigned by the server
device_heartbeat_duration = 0

# Control variables
# Flag to indicate when to stop consuming messages
stop_condition_met = False
connection = None                     # RabbitMQ connection object


def createChannels():
    """
    Create and return channels for the device registry and accepted devices queues.

    Returns:
        tuple: A tuple containing two channel objects for device registry and accepted devices.
    """
    global cloud_amqp_url, device_registry_queue, accepted_devices_queue
    global connection

    try:
        # Close existing connection if any
        connection.close()
    except Exception as e:
        pass  # Ignore exceptions when closing the connection

    # Establish a new connection to the RabbitMQ server
    connection_parameters = pika.URLParameters(url=cloud_amqp_url)
    connection = pika.BlockingConnection(parameters=connection_parameters)

    if connection is None:
        # If connection failed, print error and return None
        print(
            f"[ERROR] Failed to create connection to RabbitMQ message broker server\n", file=sys.stderr)
        return None, None

    # Create a channel for the device registry queue
    dev_reg_channel = connection.channel()
    # dev_reg_channel.queue_declare(
    #     queue=device_registry_queue, durable=False, auto_delete=True)

    # Create a channel for the accepted devices queue
    acp_dev_channel = connection.channel()
    # acp_dev_channel.queue_declare(
    #     queue=accepted_devices_queue, durable=False, auto_delete=True)

    return dev_reg_channel, acp_dev_channel


def generateMessage() -> str:
    """
    Generates a JSON-formatted message using the device's MAC address, name, and description.

    Returns:
        str: A JSON-formatted string containing the device information.
    """
    global MAC_address, device_name, device_description

    # Create a copy of the message template
    message_in_dict = DEVICE_REGISTRY_MSG_TEM.copy()
    # Fill in the device information
    message_in_dict["mac_address"] = MAC_address
    message_in_dict["data"]["name"] = device_name
    message_in_dict["data"]["description"] = device_description

    # Convert the message to a JSON-formatted string
    json_msg = json.dumps(obj=message_in_dict, indent=4)
    return json_msg


def callback(ch, method, properties, body):
    """
    Callback function for processing messages from the accepted devices queue.

    Args:
        ch: The channel object.
        method: Delivery method.
        properties: Message properties.
        body: The message body.
    """
    global MAC_address, device_heartbeat_duration, device_id
    global stop_condition_met
    global redis_host, redis_port, redis_db

    # Decode the message body
    decoded_message = body.decode('utf-8').replace("\n", "")

    def getMACAddress(msg: str) -> str:
        """
        Extracts the MAC address from the message.

        Args:
            msg (str): The JSON-formatted message.

        Returns:
            str: The MAC address if found, else None.
        """
        data = json.loads(msg)
        this_mac_addr = data.get('mac_address')
        if this_mac_addr:
            print("Current MAC:", this_mac_addr)
            return str(this_mac_addr)
        return None

    def getDeviceID(msg: str) -> str:
        """
        Extracts the device ID from the message.

        Args:
            msg (str): The JSON-formatted message.

        Returns:
            str: The device ID if found, else None.
        """
        data = json.loads(msg)
        this_dev_id = data.get('device_id')
        if this_dev_id:
            return str(this_dev_id)
        return None

    def getHeartbeatDuration(msg: str) -> int:
        """
        Extracts the heartbeat duration from the message.

        Args:
            msg (str): The JSON-formatted message.

        Returns:
            int: The heartbeat duration if found, else None.
        """
        data = json.loads(msg)
        this_hb_dur = data.get('heartbeat_duration')
        if this_hb_dur:
            return int(this_hb_dur)
        return None

    # Check if the MAC address in the message matches this device's MAC address
    if getMACAddress(decoded_message) == MAC_address:
        print("Message with matching MAC address received, stopping consumer...")
        stop_condition_met = True  # Set the flag to stop consuming messages

        device_id = getDeviceID(decoded_message)
        device_heartbeat_duration = getHeartbeatDuration(decoded_message)

        # Update the .env file with the received device ID and heartbeat duration
        updateENV(key=DOTENV_KEY_DEVICE_ID, value=device_id)
        updateENV(key=DOTENV_KEY_HEARTBEAT_DURATION,
                  value=str(device_heartbeat_duration))

        # Set the mac, id, heartbeat duration in redis DB
        redis_client = redis.Redis(
            host=redis_host, port=redis_port, db=redis_db)
        redis_client.set(name=REDIS_KEY_MAC_ADDRESS, value=MAC_address)
        redis_client.set(name=REDIS_KEY_DEVICE_ID, value=device_id)
        redis_client.set(name=REDIS_KEY_HEARTBEAT_DURATION,
                         value=device_heartbeat_duration)

        # Acknowledge the message and stop consuming
        ch.basic_ack(delivery_tag=method.delivery_tag)
        ch.stop_consuming()
        return


if __name__ == '__main__':
    # Create channels for device registry and accepted devices queues
    device_registry_channel, accepted_devices_channel = createChannels()
    if (device_registry_channel is None) or (accepted_devices_channel is None):
        sys.exit(1)  # Exit if channels could not be created

    def consume_with_timeout():
        """
        Consumes messages from the accepted devices queue with a timeout.

        If the stop condition is met or the timeout is reached, stops consuming.
        """
        global retry_timeout
        start_time = time.time()

        while True:
            # Check if the retry timeout has been reached
            if time.time() - start_time >= retry_timeout:
                print("Timeout reached, stopping consumer...")
                accepted_devices_channel.stop_consuming()
                break

            # Process data events with a time limit to prevent blocking
            accepted_devices_channel._process_data_events(time_limit=1)

            # If the stop condition is met, exit the program
            if stop_condition_met:
                sys.exit(0)
                break

    # Start consuming messages from the accepted devices queue
    accepted_devices_channel.basic_consume(
        queue=accepted_devices_queue,
        on_message_callback=callback,
        auto_ack=False
    )

    while True:
        # Publish the device registration message to the device registry queue
        msg_body = generateMessage()
        print(f"Pub this msg: {msg_body}")
        device_registry_channel.basic_publish(
            exchange='',
            routing_key=device_registry_queue,
            body=msg_body
        )

        # Consume messages with a timeout
        consume_with_timeout()

        # Close the channels
        device_registry_channel.close()
        accepted_devices_channel.close()

        print("RETRY after 1 second...")

        # Recreate the channels for the next attempt
        device_registry_channel, accepted_devices_channel = createChannels()
        if (device_registry_channel is None) or (accepted_devices_channel is None):
            sys.exit(1)  # Exit if channels could not be recreated

        # Restart consuming messages from the accepted devices queue
        accepted_devices_channel.basic_consume(
            queue=accepted_devices_queue,
            on_message_callback=callback,
            auto_ack=False
        )
