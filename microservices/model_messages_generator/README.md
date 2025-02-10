# MODEL MESSAGES GENERATOR

Subscribe to local rabbitmq model-output message queue, 
reformat and publish to local rabbitmq broker for messages delivery microservice. 
Also upload images with timestamp from that message to minio object storage.

## Build

```
sudo docker build -t model_messages_generator .
```

## Run

RUN THIS BEFORE RUN THE AIML INFERENCE

```
sudo docker run -d -v /home/ivsr/aiot-platform-baseline/aiml-inference/saved_images:/mnt/images model_messages_generator
```