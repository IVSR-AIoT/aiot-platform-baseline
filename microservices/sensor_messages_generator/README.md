# SENSOR MESSAGES GENERATOR

Subscribe to sensor data MQTT topics, creates json-format message and publish to local rabbitmq broker for messages delivery microservice

## Build 

```
sudo docker build -t sensor_messages_generator .
```

## Run

```
sudo docker run -d sensor_messages_generator
```