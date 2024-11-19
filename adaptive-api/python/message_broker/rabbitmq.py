import pika
import mq_config
import json
import sys

credentials = pika.PlainCredentials(mq_config.USERNAME, mq_config.HOST)
connection_parameters = pika.ConnectionParameters(
    host=mq_config.HOST,
    port=mq_config.PORT,
    virtual_host=mq_config.VIRTUAL_HOST,
    credentials=credentials
)

connection = pika.BlockingConnection(connection_parameters)
channel = connection.channel()
channel.queue_declare(queue=mq_config.QUEUE, durable=True)


def publishMessage(msg_dict: dict) -> bool:
    '''
    Publishes a message to a RabbitMQ queue.

    Args:
        msg_dict (dict): The message content to be published, represented as a dictionary.

    Returns:
        bool: True if the message was successfully published, False otherwise.
    '''

    try:
        message_body = json.dumps(obj=msg_dict)
        channel.basic_publish(
            exchange='',
            routing_key=mq_config.QUEUE,
            body=message_body
        )
    except Exception as e:
        print(f'[ERR]: {e}', file=sys.stderr)
        return False

    return True
