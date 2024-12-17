# MODEL MESSAGES GENERATOR

Subscribe to local rabbitmq model-output message queue, 
reformat and publish to local rabbitmq broker for messages delivery microservice. 
Also upload images with timestamp from that message to minio object storage.

## Build

```
sudo docker build -t model_messages_generator .
```

## Run

```
sudo docker run -d -v /home/ivsr/parallel_proc/save_image:/mnt/images model_messages_generator
```