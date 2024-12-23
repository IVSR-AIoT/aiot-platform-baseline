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
const std::string CLIENT_ID{"ltr390_publisher"};
const std::string TOPIC{"/ltr390"};

const std::string i2c_bus = "/dev/i2c-3";
const int ltr390_address = 0x53; // I2C address of the LTR390 sensor

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

class LTR390
{
public:
    explicit LTR390(I2CDevice &i2c_device)
        : i2c(i2c_device) {}

    /**
     * Reads UV measurements from the LTR390 sensor.
     *
     * Sends a read command to the sensor, waits for data processing, and parses the received buffer
     * to extract UV values. Updates the provided references with the results.
     *
     * @param uv Reference to store the UV measurement.
     */
    void readMeasurement(uint16_t &uv)
    {
        uint8_t read_command[] = {0x0D};
        uint8_t buffer[2];

        i2c.writeCommand(read_command, sizeof(read_command));

        // Wait for the sensor to process the command and provide data
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        i2c.readData(buffer, sizeof(buffer));

        uv = (static_cast<uint16_t>(buffer[0]) << 8) | buffer[1];
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

class LTRPublisher : public MQTTPublisher
{
public:
    LTRPublisher(const std::string &address, const std::string &client_id)
        : MQTTPublisher(address, client_id) {};

    /**
     * Update UV intensity of the LTRPublisher
     *
     */
    void update(int16_t _uv)
    {
        this->uv = _uv;
    }

protected:
    /**
     * Creates a JSON payload with uv values.
     *
     * @return Json::Value - A JSON object containing uv values.
     */
    virtual Json::Value createPayload() override;

private:
    int16_t uv;
};

Json::Value LTRPublisher::createPayload()
{
    Json::Value payload_json;
    // Populate the payload data
    payload_json["uv"] = this->uv;

    // Create the full message with type and payload
    Json::Value message_json;
    message_json["type"] = "uv";            // Set the type, e.g., "uv" for uv sensor
    message_json["payload"] = payload_json; // Add the payload

    return message_json;
}

/**********************************************************/

int main()
{
    LTRPublisher publisher(SERVER_ADDRESS, CLIENT_ID);
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
        I2CDevice i2c_device(i2c_bus, ltr390_address);
        LTR390 ltr390_sensor(i2c_device);

        while (true)
        {

            std::this_thread::sleep_for(std::chrono::seconds(5));

            uint16_t uv;
            ltr390_sensor.readMeasurement(uv);

            publisher.update(uv);

            publisher.publish(TOPIC);

            std::cout << "LTR390 Data: " << uv << "\n";
            std::this_thread::sleep_for(std::chrono::seconds(5));
        }
    }
    catch (const std::exception &ex)
    {
        std::cerr << ex.what() << '\n';
        publisher.disconnect();
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
