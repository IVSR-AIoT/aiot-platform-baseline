#include <iostream>
#include <stdexcept>
#include <string>
#include <cstdint>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <cstring>
#include <chrono>
#include <thread>

#include <json/json.h>
#include <mqtt/async_client.h>

const std::string SERVER_ADDRESS{"tcp://localhost:1883"};
const std::string CLIENT_ID{"scd41_publisher"};
const std::string TOPIC{"/scd41"};

const std::string i2c_bus = "/dev/i2c-3";
const int scd41_address = 0x62;

class I2CDevice
{
public:
    /**
     * Initializes an I2CDevice with the specified bus and address.
     * Opens the I2C bus and sets the device address.
     */
    I2CDevice(const std::string &bus, int address)
        : file_descriptor(-1), device_address(address)
    {
        openBus(bus);
        setDeviceAddress();
    }

    ~I2CDevice()
    {
        if (file_descriptor >= 0)
        {
            close(file_descriptor);
        }
    }

    // Delete copy constructor and assignment operator
    I2CDevice(const I2CDevice &) = delete;
    I2CDevice &operator=(const I2CDevice &) = delete;

    /**
     * Writes a command to the I2C device.
     *
     * @param command Pointer to the command buffer to be written.
     * @param length Size of the command buffer.
     * @throws std::runtime_error if the write operation fails.
     */
    void writeCommand(const uint8_t *command, size_t length)
    {
        ssize_t bytes_written = write(file_descriptor, command, length);
        if (bytes_written != static_cast<ssize_t>(length))
        {
            throw std::runtime_error("Failed to write command: " + std::string(std::strerror(errno)));
        }
    }

    /**
     * Reads data from the I2C device into the provided buffer.
     *
     * @param buffer Pointer to the buffer where the data will be stored.
     * @param length Size of the data to be read.
     * @throws std::runtime_error if the read operation fails.
     */
    void readData(uint8_t *buffer, size_t length)
    {
        ssize_t bytes_read = read(file_descriptor, buffer, length);
        if (bytes_read != static_cast<ssize_t>(length))
        {
            throw std::runtime_error("Failed to read data: " + std::string(std::strerror(errno)));
        }
    }

private:
    int file_descriptor;
    int device_address;

    /**
     * Opens the specified I2C bus for communication.
     *
     * @param bus The path to the I2C bus to be opened.
     * @throws std::runtime_error if the bus cannot be opened.
     */
    void openBus(const std::string &bus)
    {
        file_descriptor = open(bus.c_str(), O_RDWR);
        if (file_descriptor < 0)
        {
            throw std::runtime_error("Failed to open the I2C bus: " + std::string(std::strerror(errno)));
        }
    }

    /**
     * Sets the device address for communication over I2C.
     * Uses the file descriptor, I2C_SLAVE, and device address to set the address.
     * Closes the file descriptor and throws a std::runtime_error if setting the address fails.
     */
    void setDeviceAddress()
    {
        if (ioctl(file_descriptor, I2C_SLAVE, device_address) < 0)
        {
            close(file_descriptor);
            throw std::runtime_error("Failed to set I2C address: " + std::string(std::strerror(errno)));
        }
    }
};

class SCD41
{
public:
    explicit SCD41(I2CDevice &i2c_device)
        : i2c(i2c_device) {}

    /**
     * Initiates a measurement by sending the command {0x21, 0xB1} to the SCD41 sensor via I2C communication.
     */
    void startMeasurement()
    {
        uint8_t command[] = {0x21, 0xB1};
        i2c.writeCommand(command, sizeof(command));
    }

    /**
     * Stops the measurement process by sending the command {0x3F, 0x86} to the SCD41 sensor via I2C communication.
     */
    void stopMeasurement()
    {
        uint8_t command[] = {0x3F, 0x86};
        i2c.writeCommand(command, sizeof(command));
    }

    /**
     * Reads CO2, temperature, and humidity measurements from the SCD41 sensor.
     *
     * Sends a read command to the sensor, waits for data processing, and parses the received buffer
     * to extract CO2, temperature, and humidity values. Updates the provided references with the results.
     *
     * @param co2 Reference to store the CO2 measurement.
     * @param temperature Reference to store the temperature measurement.
     * @param humidity Reference to store the humidity measurement.
     */
    void readMeasurement(uint16_t &co2, float &temperature, float &humidity)
    {
        uint8_t read_command[] = {0xEC, 0x05};
        uint8_t buffer[9];

        i2c.writeCommand(read_command, sizeof(read_command));

        // Wait for the sensor to process the command and provide data
        std::this_thread::sleep_for(std::chrono::milliseconds(50));

        i2c.readData(buffer, sizeof(buffer));

        // Parse the buffer into CO2, temperature, and humidity values
        co2 = (static_cast<uint16_t>(buffer[0]) << 8) | buffer[1];
        uint16_t temp_raw = (static_cast<uint16_t>(buffer[3]) << 8) | buffer[4];
        uint16_t hum_raw = (static_cast<uint16_t>(buffer[6]) << 8) | buffer[7];

        temperature = -45.0f + 175.0f * static_cast<float>(temp_raw) / 65536.0f;
        humidity = 100.0f * static_cast<float>(hum_raw) / 65536.0f;
    }

    /**
     * Checks if new measurement data is ready.
     *
     * @return true if data is ready, false otherwise.
     */
    bool isDataReady()
    {
        uint8_t command[] = {0xE4, 0xB8};
        uint8_t buffer[3]; // 2 bytes of status word + CRC

        i2c.writeCommand(command, sizeof(command));

        // Wait for the sensor to process the command
        std::this_thread::sleep_for(std::chrono::milliseconds(1));

        i2c.readData(buffer, sizeof(buffer));

        uint16_t status = (static_cast<uint16_t>(buffer[0]) << 8) | buffer[1];

        // Check the 'data ready' bit (bit 15)
        return (status & 0x8000) != 0;
    }

private:
    I2CDevice &i2c;
};

class MQTTPublisher
{
public:
    /**
     * Constructor for the MQTTPublisher class.
     * Initializes the MQTT client with the provided address and client ID.
     * Sets the connection options to have a clean session.
     *
     * @param address The address of the MQTT broker.
     * @param client_id The client ID for the MQTT connection.
     */
    MQTTPublisher(const std::string &address, const std::string &client_id)
        : client_(address, client_id)
    {
        connOpts_.set_clean_session(true);
    }

    /**
     * Destructor for the MQTTPublisher class.
     * Tries to disconnect the MQTT client when the object is destroyed.
     * If an exception occurs during disconnection, it is caught and an error message is displayed.
     */
    ~MQTTPublisher()
    {
        try
        {
            disconnect();
        }
        catch (const mqtt::exception &exc)
        {
            std::cerr << "Error during disconnect: " << exc.what() << std::endl;
        }
    }

    /**
     * Connects to the MQTT broker using the provided client and connection options.
     *
     * @return true if the connection is successful, false otherwise.
     */
    bool connect()
    {
        try
        {
            // Connect to the MQTT broker
            std::cout << "Connecting to the MQTT broker at " << client_.get_server_uri() << "..." << std::endl;
            auto tok = client_.connect(connOpts_);
            tok->wait();
            std::cout << "Connected." << std::endl;
            return true;
        }
        catch (const mqtt::exception &exc)
        {
            std::cerr << "MQTT Exception during connect: " << exc.what() << std::endl;
            return false;
        }
    }

    /**
     * Publishes a message to the MQTT broker on the specified topic with the given Quality of Service (QoS).
     *
     * @param topic The topic to which the message will be published.
     * @param qos The Quality of Service level for message delivery (default is 1).
     * @return true if the message is successfully published, false otherwise.
     */
    bool publish(const std::string &topic, int qos = 1)
    {
        try
        {
            Json::Value payload_json = createPayload();

            // Serialize JSON to string
            Json::StreamWriterBuilder writer;
            std::string payload = Json::writeString(writer, payload_json);

            auto pubmsg = mqtt::make_message(topic, payload);
            pubmsg->set_qos(qos);

            std::cout << "Publishing message..." << std::endl;
            client_.publish(pubmsg)->wait_for(std::chrono::seconds(10));
            std::cout << "Message published." << std::endl;
            return true;
        }
        catch (const mqtt::exception &exc)
        {
            std::cerr << "MQTT Exception during publish: " << exc.what() << std::endl;
            return false;
        }
    }

    /**
     * Disconnects the MQTT client if it is currently connected.
     * Displays status messages before and after disconnection.
     * Catches any MQTT exceptions that occur during the disconnection process and logs them.
     */
    void disconnect()
    {
        try
        {
            if (client_.is_connected())
            {
                std::cout << "Disconnecting..." << std::endl;
                client_.disconnect()->wait();
                std::cout << "Disconnected." << std::endl;
            }
        }
        catch (const mqtt::exception &exc)
        {
            std::cerr << "MQTT Exception during disconnect: " << exc.what() << std::endl;
        }
    }

protected:
    /**
     * Creates a JSON payload for publishing a message.
     * Default implementation sets a message field with a default value.
     *
     * @return The JSON Value representing the payload.
     */
    virtual Json::Value createPayload()
    {
        // Default implementation (can be empty or provide generic data)
        Json::Value payloadJson;
        payloadJson["message"] = "Default payload from MQTTPublisher";
        return payloadJson;
    }

private:
    mqtt::async_client client_;
    mqtt::connect_options connOpts_;
};

/************************************************/

/**
 * Represents a publisher for CO2, Temp, Humi sensor data that extends the MQTTPublisher class.
 * Inherits MQTT connection functionality and provides a method to update sensor data.
 */
class SCDPublisher : public MQTTPublisher
{
public:
    SCDPublisher(const std::string &address, const std::string &client_id)
        : MQTTPublisher(address, client_id) {};

    /**
     * Updates the CO2, temperature, and humidity values of the SCDPublisher instance.
     */
    void update(int16_t _co2, float _temperature, float _humidity)
    {
        this->co2 = _co2;
        this->temperature = _temperature;
        this->humidity = _humidity;
    }

protected:
    /**
     * Creates a JSON payload with CO2, temperature, and humidity values.
     *
     * @return Json::Value - A JSON object containing CO2, temperature, and humidity values.
     */
    virtual Json::Value createPayload() override;

private:
    int16_t co2;
    float temperature, humidity;
};

Json::Value SCDPublisher::createPayload()
{
    Json::Value payload_json;
    payload_json["co2"] = this->co2;
    payload_json["temperature"] = this->temperature;
    payload_json["humidity"] = this->humidity;

    return payload_json;
}

/************************************************/

int main()
{
    SCDPublisher publisher(SERVER_ADDRESS, CLIENT_ID);
    try
    {
        if (!publisher.connect())
        {
            std::cerr << "Failed to connnect to MQTT server, exiting...";
            return EXIT_FAILURE;
        }
    }
    catch (const std::exception &ex)
    {
        std::cerr << "Failed to connnect to MQTT server, exiting...\n";
        std::cerr << ex.what() << '\n';
        return EXIT_FAILURE;
    }

    try
    {
        I2CDevice i2c_device(i2c_bus, scd41_address);
        SCD41 scd41_sensor(i2c_device);

        if (!scd41_sensor.isDataReady())
        {
            scd41_sensor.stopMeasurement();
            scd41_sensor.startMeasurement();
        }

        while (true)
        {
            if (!scd41_sensor.isDataReady())
            {
                continue;
            }
            std::this_thread::sleep_for(std::chrono::seconds(5));

            uint16_t co2;
            float temperature, humidity;

            scd41_sensor.readMeasurement(co2, temperature, humidity);

            publisher.update(co2, temperature, humidity);

            publisher.publish(TOPIC);

            std::cout << "CO2: " << co2 << " ppm, "
                      << "Temperature: " << temperature << " °C, "
                      << "Humidity: " << humidity << " %RH" << std::endl;

            std::this_thread::sleep_for(std::chrono::seconds(5)); // Total interval between readings is 10 seconds
        }

        scd41_sensor.stopMeasurement();
    }
    catch (const std::exception &ex)
    {
        std::cerr << ex.what() << '\n';
        publisher.disconnect();
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
