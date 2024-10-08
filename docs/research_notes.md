# RESEARCH NOTES

## SELF-HOSTED SERVICES

### Object Storage Service: *minio*

1. Instruction: https://min.io/docs/minio/container/index.html
2. Installation:
```
sudo docker run -d -p 19000:9000 -p 19001:9001 \
-v /mnt/2E287FDD287FA28F/aiot/minio/data:/data \
-e "MINIO_ROOT_USER=admin" -e "MINIO_ROOT_PASSWORD=ivsr@2019" \
quay.io/minio/minio server /data --console-address ":9001"
```
3. Notes
   1. Mount directory (on server): ```/mnt/2E287FDD287FA28F/aiot/minio```
   2. ROOT Username: ```admin```, ROOT Password: ```ivsr@2019```

### Stream Engine: *ovenmediaengine (ome)*

1. Instruction: https://airensoft.gitbook.io/ovenmediaengine/getting-started
2. Installation:
```
sudo apt install ovenmediaengine
sudo systemctl enable ovenmediaengine # Enable OME to start on boot
```
3. Notes:
   1. Generate TLS certification:
```
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
-keyout ./ssl.key \
-out ./ssl.crt \
subj "/C=VN/ST=HN/L=HUST/O=IVSR/OU=C7/CN=192.168.0.112"
```
   1. Config file location on server: ```/usr/share/ovenmediaengine/conf/Server.xml```
   2. Using RTSP input from IP camera, then output stream is WebRTC:

        - Input source (RTSP Pull): https://airensoft.gitbook.io/ovenmediaengine/live-source/rtsp-pull    

        - Streaming (WebRTV): https://airensoft.gitbook.io/ovenmediaengine/streaming/webrtc-publishing 

4. Addition:
   1. Youtube short introduction video: [Youtube](https://www.youtube.com/watch?v=WmR9IMUD_CY)

### Message Queue Broker: *rabbitmq*
1. Instruction: https://www.rabbitmq.com/docs/download
2. Installation:
```
# latest RabbitMQ 4.0.x
docker run -it --rm -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4.0-management
```
3. Notes:
   1. ADMIN username: `guest`, ADMIN password: `guest` (admin)
   2. RECOMMENDED username: `aiot`, with password: `ivsr@2019` (admin)
   3. Default port for message: `5672`
   4. Default port for management/configuration website: `15672`

### MQTT Message Broker: `mosquitto`
1. Instruction: https://mosquitto.org/
2. Installation:
```
sudo apt-add-repository ppa:mosquitto-dev/mosquitto-ppa
sudo apt-get update
sudo apt install mosquitto mosquitto-clients mosquitto-dev # Broker and client, dev tools
sudo systemctl enable mosquitto # Enable Mosquitto to start on boot
```
3. Notes:
   1. Configuration file on server: `/etc/mosquitto/mosquitto.conf`
   2. Default port for message (both pub and sub): `1883`