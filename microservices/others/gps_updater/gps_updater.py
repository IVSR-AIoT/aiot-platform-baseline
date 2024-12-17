import redis
import json
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os
from datetime import datetime

# Load environment variables from .env file
load_dotenv()


class GpsSubscriber:
    def __init__(self):
        # Load Redis and MQTT configurations from environment variables
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = int(os.getenv("REDIS_DB", 0))

        self.mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
        self.mqtt_port = int(os.getenv("MQTT_PORT", 1883))
        self.mqtt_topic = os.getenv("MQTT_TOPIC", "/gps")

        # Initialize Redis connection
        self.redis_client = redis.StrictRedis(
            host=self.redis_host, port=self.redis_port, db=self.redis_db)

        # Initialize MQTT client (modified to avoid callback_api_version issue)
        # `clean_session=True` is typically useful for persistent sessions
        self.client = mqtt.Client()

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def connect_mqtt(self):
        """
        Connects to the MQTT broker.
        """
        print(
            f"Connecting to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}")
        self.client.connect(self.mqtt_broker, self.mqtt_port, 60)

    def start_listening(self):
        """
        Starts the MQTT client loop to listen for incoming messages.
        """
        print(f"Subscribing to topic {self.mqtt_topic}")
        self.client.subscribe(self.mqtt_topic)
        self.client.loop_forever()  # Keep the loop running

    def on_connect(self, client, userdata, flags, rc):
        """
        Callback function when MQTT client connects to broker.
        """
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print(f"Failed to connect to MQTT Broker, return code {rc}")

    def on_message(self, client, userdata, msg):
        """
        Callback function when a message is received from MQTT broker.
        """
        print(f"Received message on topic {msg.topic}: {msg.payload.decode()}")

        # Parse the incoming MQTT message
        self.parse(msg.payload.decode())

    def parse(self, mqtt_message):
        """
        Parses the incoming MQTT message, extracting the GPS data and storing it in Redis.
        """
        try:
            # Load the MQTT message into a Python dictionary
            message = json.loads(mqtt_message)

            # Extract GPS data from the payload
            payload = message.get("payload", {})
            latitude = payload.get("latitude", None)
            longitude = payload.get("longitude", None)
            timestamp = payload.get("timestamp", None)

            if latitude is not None and longitude is not None:
                # Default altitude value (as given in the question)
                altitude = 15.000000

                # Round values to 6 digits after the decimal
                latitude = round(latitude, 6)
                longitude = round(longitude, 6)
                altitude = round(altitude, 6)

                # Store the values in Redis
                self.redis_client.set("LOCATION_LAT", latitude)
                self.redis_client.set("LOCATION_LON", longitude)
                self.redis_client.set("LOCATION_ALT", altitude)
                self.redis_client.set("GPS_LAST_UPDATED", datetime.now().isoformat())
                print(
                    f"GPS updated in Redis: LAT={latitude}, LON={longitude}, ALT={altitude}")
            else:
                print("Invalid GPS data in MQTT message.")
        except Exception as e:
            print(f"Error parsing MQTT message: {e}")


# Example usage:
if __name__ == "__main__":
    # Create the GpsSubscriber instance
    publisher = GpsSubscriber()

    # Connect to MQTT broker
    publisher.connect_mqtt()

    # Start listening for incoming messages on the specified MQTT topic
    publisher.start_listening()
