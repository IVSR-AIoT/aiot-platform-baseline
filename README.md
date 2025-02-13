# aiot-platform-baseline

## Installation

## Setup

1. **First, SSH into the Orange Pi Zero 3, ensuring you are on the same network:**

    ```bash
    ssh orangepi@192.168.1.201
    sudo mount 192.168.1.202:/home/ivsr/aiot-platform-baseline/aiml-inference/saved_images /mnt/jetson_dir
    ```

2. **Run the following Docker containers:**

    ```bash
    docker run -d -v /mnt/jetson_dir:/mnt/images model_messages_generator
    docker run -d sensor_messages_generator
    docker run -d messages_delivery
    docker run -d workflow_management
    ```

3. **Check the status of these services. If any of them are not working, restart the respective service:**

    ```bash
    sudo systemctl status scd41.service 
    sudo systemctl status pms5003.service
    sudo systemctl status gps.service
    sudo systemctl status ltr390.service
    ```

    If a service is down, restart it:

    ```bash
    sudo systemctl restart scd41.service
    sudo systemctl restart pms5003.service
    sudo systemctl restart gps.service
    sudo systemctl restart ltr390.service
    ```

## Usage

1. **Register/Re-register this device:**
   - SSH into the Orange Pi Zero 3:

     ```bash
     ssh orangepi@192.168.1.201
     ```

   - Run the device management Docker container:

     ```bash
     docker run -d device_management
     ```

2. **Run the AI/ML inference:**
   - SSH into the NVIDIA Jetson Xavier NX:

     ```bash
     ssh ivsr@192.168.1.202
     ```

   - Navigate to the AI/ML inference directory and run the script:

     ```bash
     cd /home/ivsr/aiot-platform-baseline/aiml-inference && \
     python3 main.py
     ```

## Useful commands:

1. **Kill all running containers:**
  
  ```bash
  docker kill $(docker ps -q)
  ```

2. **Remove all existing images, including their cache for a fresh build:**

  ```bash
  docker rmi $(docker images -q) --force --no-prune
  ```

3. **Build all docker images after a pull:**

  ```bash
  cd /home/orangepi/aiot-platform-baseline/microservices/device_management && \
  docker build -t device_management . && \
  cd /home/orangepi/aiot-platform-baseline/microservices/sensor_messages_generator && \
  docker build -t sensor_messages_generator . && \
  cd /home/orangepi/aiot-platform-baseline/microservices/model_messages_generator && \
  docker build -t model_messages_generator . && \
  cd /home/orangepi/aiot-platform-baseline/microservices/messages_delivery && \
  docker build -t messages_delivery . && \
  cd /home/orangepi/aiot-platform-baseline/microservices/workflow_management && \
  docker build -t workflow_management .
  ```