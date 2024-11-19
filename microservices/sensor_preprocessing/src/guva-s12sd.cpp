#include <iostream>
#include <stdexcept>
#include <string>
#include <cstdint>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/spi/spidev.h>
#include <cstring>
#include <chrono>
#include <thread>

#include <json/json.h>
#include <mqtt/async_client.h>

const std::string SERVER_ADDRESS{"tcp://localhost:1883"};
const std::string CLIENT_ID{"guva-s12sd_publisher"};
const std::string TOPIC{"/guva-s12sd"};

const std::string spi_device = "/dev/spidev1.1";
const uint32_t spi_speed = 500000;
const uint8_t spi_mode = SPI_MODE_1;
const uint8_t bits_per_word = 8;

class SPI
{
public:
    /**
     * Initializes the SPI object with the specified device, speed, mode, and bits per word.
     * Opens the SPI device, sets the mode, bits per word, and speed using ioctl calls.
     * Throws a runtime_error if any operation fails.
     *
     * @param device The path to the SPI device.
     * @param speed The speed in Hz (default is 500000).
     * @param mode The SPI mode (default is SPI_MODE_1).
     * @param bits The number of bits per word (default is 8).
     */
    SPI(const std::string &device, uint32_t speed = 500000, uint8_t mode = SPI_MODE_1, uint8_t bits = 8)
        : spi_fd(-1), speed(speed), bits_per_word(bits)
    {
        spi_fd = open(device.c_str(), O_RDWR);
        if (spi_fd < 0)
        {
            throw std::runtime_error("Failed to open SPI device: " + device + ", error: " + std::strerror(errno));
        }

        if (ioctl(spi_fd, SPI_IOC_WR_MODE, &mode) < 0 || ioctl(spi_fd, SPI_IOC_RD_MODE, &mode) < 0)
        {
            close(spi_fd);
            throw std::runtime_error("Failed to set SPI mode: " + std::string(std::strerror(errno)));
        }

        if (ioctl(spi_fd, SPI_IOC_WR_BITS_PER_WORD, &bits_per_word) < 0 ||
            ioctl(spi_fd, SPI_IOC_RD_BITS_PER_WORD, &bits_per_word) < 0)
        {
            close(spi_fd);
            throw std::runtime_error("Failed to set SPI bits per word: " + std::string(std::strerror(errno)));
        }

        if (ioctl(spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0 ||
            ioctl(spi_fd, SPI_IOC_RD_MAX_SPEED_HZ, &speed) < 0)
        {
            close(spi_fd);
            throw std::runtime_error("Failed to set SPI speed: " + std::string(std::strerror(errno)));
        }
    }

    ~SPI()
    {
        if (spi_fd >= 0)
        {
            close(spi_fd);
        }
    }

    // Delete copy constructor and assignment operator
    SPI(const SPI &) = delete;
    SPI &operator=(const SPI &) = delete;

    /**
     * Transfers data over SPI by sending and receiving data buffers.
     *
     * @param tx_buf Pointer to the data buffer to be transmitted.
     * @param rx_buf Pointer to the data buffer to store received data.
     * @param length The length of the data buffers.
     * @param delay_usecs The delay in microseconds between transmit and receive (default is 1).
     *
     * @throws std::runtime_error if the SPI message transfer fails.
     */
    void transfer(const uint8_t *tx_buf, uint8_t *rx_buf, size_t length, uint16_t delay_usecs = 1)
    {
        struct spi_ioc_transfer tr
        {
        };
        tr.tx_buf = reinterpret_cast<uintptr_t>(tx_buf);
        tr.rx_buf = reinterpret_cast<uintptr_t>(rx_buf);
        tr.len = length;
        tr.delay_usecs = delay_usecs;
        tr.speed_hz = speed;
        tr.bits_per_word = bits_per_word;

        int ret = ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr);
        if (ret < 1)
        {
            throw std::runtime_error("Failed to transfer SPI message: " + std::string(std::strerror(errno)));
        }
    }

private:
    int spi_fd;
    uint32_t speed;
    uint8_t bits_per_word;
};

class ADS1118
{
public:
    explicit ADS1118(SPI &spi, float vRef = 1.024f, float conversionFactor = 0.1f)
        : spi(spi), vRef(vRef), conversionFactor(conversionFactor) {}

    /**
     * Reads the analog-to-digital converter (ADC) value from the ADS1118.
     *
     * @return The ADC value read from the ADS1118.S
     */
    int16_t readADC()
    {
        uint8_t tx[2] = {0xC5, 0x83}; // Configuration command to ADS1118
        uint8_t rx[2] = {0, 0};

        spi.transfer(tx, rx, 2);

        std::this_thread::sleep_for(std::chrono::milliseconds(10));

        int16_t result = (static_cast<int16_t>(rx[0]) << 8) | rx[1];
        return result;
    }

    /**
     * Calculates the voltage based on the raw ADC value and the reference voltage (vRef).
     *
     * @param raw_value The raw ADC value to calculate the voltage from.
     * @return The calculated voltage based on the raw ADC value and the reference voltage.
     */
    float calculateVoltage(int16_t raw_value) const
    {
        return (raw_value * vRef) / 32768.0f;
    }

    /**
     * Calculates the UV intensity based on the given voltage and the conversion factor.
     *
     * @param voltage The voltage value to calculate the UV intensity from.
     * @return The calculated UV intensity in mW/cm².
     */
    float calculateUVIntensity(float voltage) const
    {
        return voltage / conversionFactor; // Returns in mW/cm²
    }

private:
    SPI &spi;
    float vRef;
    float conversionFactor;
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

/******************************************************/

/**
 * Represents a publisher for UV sensor data that extends the MQTTPublisher class.
 * Inherits MQTT connection functionality and provides a method to update sensor data.
 */
class GuvaPublisher : public MQTTPublisher
{
public:
    GuvaPublisher(const std::string &address, const std::string &client_id)
        : MQTTPublisher(address, client_id) {};

    /**
     * Updates the raw sensor value, voltage, and UV intensity.
     *
     * @param _raw_value: The new raw sensor value to update.
     * @param _voltage: The new voltage value to update.
     * @param _uv_intensity: The new UV intensity value to update.
     */
    void update(int16_t _raw_value, float _voltage, float _uv_intensity)
    {
        this->raw_value = _raw_value;
        this->voltage = _voltage;
        this->uv_intensity = _uv_intensity;
    }

protected:
    /**
     * Creates a JSON payload containing raw sensor values.
     *
     * @return Json::Value - A JSON object with raw sensor values for raw_value, voltage, and uv_intensity.
     */
    virtual Json::Value createPayload() override;

private:
    int16_t raw_value;
    float voltage;
    float uv_intensity;
};

Json::Value GuvaPublisher::createPayload()
{
    Json::Value payload_json;
    // Populate the payload data
    payload_json["raw_value"] = this->raw_value;
    payload_json["voltage"] = this->voltage;
    payload_json["uv_intensity"] = this->uv_intensity;

    // Create the full message with type and payload
    Json::Value message_json;
    message_json["type"] = "uv";            // Set the type, e.g., "uv" for UV sensor
    message_json["payload"] = payload_json; // Add the payload

    return message_json;
}

/******************************************************/

int main()
{
    GuvaPublisher publisher(SERVER_ADDRESS, CLIENT_ID);
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
        SPI spi(spi_device, spi_speed, spi_mode, bits_per_word);
        ADS1118 ads1118(spi);

        while (true)
        {
            int16_t raw_value = ads1118.readADC();
            float voltage = ads1118.calculateVoltage(raw_value);
            float uv_intensity = ads1118.calculateUVIntensity(voltage);

            std::cout << "Raw Value: " << raw_value
                      << ", Voltage: " << voltage << " V"
                      << ", UV Intensity: " << uv_intensity << " mW/cm²" << std::endl;

            publisher.update(raw_value, voltage, uv_intensity);

            publisher.publish(TOPIC);

            std::this_thread::sleep_for(std::chrono::seconds(2));
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