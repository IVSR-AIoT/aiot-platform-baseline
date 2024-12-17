# GPS Updater
This microservice subscribe to gps topic from MQTT server to get GPS information. 
After that, set 3 key: LOCATION_LAT, LOCATION_LON and LOCATIN_ALT in redis database

## Build

```
sudo docker build -t gps_updater .
```

## Run

```
sudo docker run -d gps_updater
```