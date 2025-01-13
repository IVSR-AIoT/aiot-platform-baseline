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

// I2C configuration
const std::string I2C_BUS = "/dev/i2c-3"; // I2C bus on Orange Pi Zero 3
const int LTR390_ADDRESS = 0x53;          // I2C address of the LTR390-UV-01 sensor

// Register addresses for LTR390
constexpr uint8_t REG_MAIN_CTRL = 0x00;   // Main Control Register
constexpr uint8_t REG_MEAS_RATE = 0x04;   // Measurement Rate Register
constexpr uint8_t REG_GAIN = 0x05;        // Gain Register
constexpr uint8_t REG_PART_ID = 0x06;     // Part ID Register
constexpr uint8_t REG_MAIN_STATUS = 0x07; // Main Status Register
constexpr uint8_t REG_UVS_DATA = 0x10;    // UVS Data Register (3 bytes)

// Control values
constexpr uint8_t MAIN_CTRL_ENABLE = 0x02;   // Enable sensor
constexpr uint8_t MAIN_CTRL_UVS_MODE = 0x08; // UVS Mode
constexpr double UV_SENSITIVITY = 2300.0;    // Sensor sensitivity (counts/UVI)
constexpr double WFAC = 1.0;                 // Window Factor

// Utility function to calculate UV Index from raw data
double calculate_uv_index(uint32_t raw_uv)
{
    return raw_uv / (UV_SENSITIVITY * WFAC);
}

// I2CDevice Class Definition
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

// LTR390 Class Definition
class LTR390
{
public:
    /**
     * Constructs an LTR390 object with the provided I2CDevice.
     *
     * @param i2c_device Reference to an initialized I2CDevice.
     */
    explicit LTR390(I2CDevice &i2c_device)
        : i2c(i2c_device)
    {
    }

    /**
     * Initializes the LTR390 sensor by configuring necessary registers.
     *
     * @throws std::runtime_error if initialization fails.
     */
    void init()
    {
        // Check sensor ID
        uint8_t id = readRegister(REG_PART_ID);
        std::cout << "Sensor ID: 0x" << std::hex << static_cast<int>(id) << std::dec << std::endl;

        if (id != 0xB2)
        { // Validate sensor ID
            throw std::runtime_error("Invalid sensor ID. Expected 0xB2.");
        }

        // Enable sensor in UVS mode
        writeRegister(REG_MAIN_CTRL, MAIN_CTRL_ENABLE | MAIN_CTRL_UVS_MODE);

        // Configure measurement rate (e.g., 100ms)
        writeRegister(REG_MEAS_RATE, 0x20); // 0x20 corresponds to a specific rate

        // Configure gain (e.g., Gain = 3)
        writeRegister(REG_GAIN, 0x02); // Gain value as per datasheet

        std::cout << "Sensor initialized successfully. Waiting for data..." << std::endl;
    }

    /**
     * Reads the UV index from the sensor.
     *
     * @return The calculated UV index.
     * @throws std::runtime_error if reading data fails.
     */
    double readUV()
    {
        uint8_t status = readRegister(REG_MAIN_STATUS);

        if (status & 0x08)
        { // Check if UVS data is ready
            uint8_t data[3];
            readUVSData(data);

            // Combine the 3 bytes into a single 32-bit raw UV value
            uint32_t raw_uv = (static_cast<uint32_t>(data[2]) << 16) |
                              (static_cast<uint32_t>(data[1]) << 8) |
                              static_cast<uint32_t>(data[0]);

            // Calculate UV Index
            double uv_index = calculate_uv_index(raw_uv);

            return uv_index;
        }

        // std::this_thread::sleep_for(std::chrono::seconds(0.1));
        // If data not ready, return -1 or handle accordingly
        return -1.0;
    }

private:
    I2CDevice &i2c;

    /**
     * Writes a single byte to a specified register.
     *
     * @param reg Register address.
     * @param value Value to write.
     * @throws std::runtime_error if the write operation fails.
     */
    void writeRegister(uint8_t reg, uint8_t value)
    {
        uint8_t buffer[2] = {reg, value};
        i2c.writeCommand(buffer, 2);
    }

    /**
     * Reads a single byte from a specified register.
     *
     * @param reg Register address.
     * @return The byte read from the register.
     * @throws std::runtime_error if the read operation fails.
     */
    uint8_t readRegister(uint8_t reg)
    {
        // Write the register address
        i2c.writeCommand(&reg, 1);

        // Read one byte of data
        uint8_t data;
        i2c.readData(&data, 1);
        return data;
    }

    /**
     * Reads 3 bytes of UVS data from the sensor.
     *
     * @param data Pointer to a 3-byte buffer where the data will be stored.
     * @throws std::runtime_error if the read operation fails.
     */
    void readUVSData(uint8_t *data)
    {
        // Write the starting register address
        uint8_t reg = REG_UVS_DATA;
        i2c.writeCommand(&reg, 1);

        // Read 3 bytes of UVS data
        i2c.readData(data, 3);
    }
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
    void update(double _uv)
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
    double uv;
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
        I2CDevice i2c_device(I2C_BUS, LTR390_ADDRESS);
        LTR390 ltr390_sensor(i2c_device);

        while (true)
        {
            double uv = ltr390_sensor.readUV();

            if (uv < 0.0)
            {
                std::cout << "UV data not ready yet." << std::endl;
            }

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
