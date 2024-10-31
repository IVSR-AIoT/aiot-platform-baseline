# USEFUL NOTES

## Make a copy of this directory for your modification

## Installation:
1. Paho MQTT Cpp: [github](https://github.com/eclipse/paho.mqtt.cpp)
    ```
    # Build the Paho C++ and Paho C libraries together
    git clone https://github.com/eclipse/paho.mqtt.cpp
    cd paho.mqtt.cpp

    git submodule init
    git submodule update

    cmake -Bbuild -H. -DPAHO_WITH_MQTT_C=ON -DPAHO_BUILD_EXAMPLES=ON
    sudo cmake --build build/ --target install

    sudo ldconfig
    ```

2. Mosquitto MQTT Broker:
    ```
    sudo apt-get install mosquitto mosquitto-clients # broker and client
    sudo systemctl start mosquitto
    sudo systemctl enable mosquitto
    ```