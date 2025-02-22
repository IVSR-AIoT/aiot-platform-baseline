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

## Build:

1. Build source code:
    ```
    mkdir build && cd build
    cmake ..
    make
    ```

2. Create deamon:
    ```
    cd services
    sudo cp pms5003.service /etc/systemd/system/
    sudo cp guva_s12sd.service /etc/systemd/system/ # Currently unused
    sudo cp scd41.service /etc/systemd/system/
    sudo cp gps.service /etc/systemd/system/
    sudo cp ltr390.service /etc/systemd/system/

    sudo systemctl daemon-reload
    
    sudo systemctl enable guva_s12sd.service # Currently unused
    sudo systemctl start guva_s12sd.service # Currently unused
    sudo systemctl enable scd41.service 
    sudo systemctl start scd41.service
    sudo systemctl enable pms5003.service
    sudo systemctl start pms5003.service
    sudo systemctl enable gps.service
    sudo systemctl start gps.service
    sudo systemctl enable ltr390.service
    sudo systemctl start ltr390.service   
    ```

3. If you gonna change the source code, reload serice:
    ```
    sudo systemctl daemon-reload && \
    sudo systemctl restart scd41.service && \
    sudo systemctl restart pms5003.service && \
    sudo systemctl restart gps.service && \
    sudo systemctl restart ltr390.service
    ```