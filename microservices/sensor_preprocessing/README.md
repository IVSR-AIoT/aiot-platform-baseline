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
3. Services load/start:
   ```
   sudo cp pms5003.service /etc/systemd/system/
   sudo cp guva_s12sd.service /etc/systemd/system/
   sudo cp scd41.service /etc/systemd/system/
   sudo cp gps.service /etc/systemd/system/

   sudo systemctl daemon-reload

   sudo systemctl enable scd41.service
   sudo systemctl enable pms5003.service
   sudo systemctl enable guva_s12sd.service
   sudo systemctl enable gps.service
   
   sudo systemctl start scd41.service
   sudo systemctl start pms5003.service
   sudo systemctl start guva_s12sd.service
   sudo systemctl start gps.service

   # Check
   sudo systemctl status scd41.service
   sudo systemctl status pms5003.service
   sudo systemctl status guva_s12sd.service
   sudo systemctl status gps.service   
   ```