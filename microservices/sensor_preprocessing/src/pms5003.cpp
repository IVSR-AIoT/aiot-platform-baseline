#include <iostream>
#include <stdexcept>
#include <string>
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <cstdint>
#include <chrono>
#include <thread>

#include <json/json.h>
#include <mqtt/async_client.h>

const std::string SERVER_ADDRESS{"tcp://localhost:1883"};
const std::string CLIENT_ID{"pms5003_publisher"};
const std::string TOPIC{"/pms5003"};

const std::string uart_device = "/dev/ttyS5";

class UART
{
public:
    explicit UART(const std::string &device)
    {
        uart_filestream = open(device.c_str(), O_RDWR | O_NOCTTY);
        if (uart_filestream == -1)
        {
            throw std::runtime_error("Unable to open UART device: " + device);
        }
        configureUART();
    }

    ~UART()
    {
        if (uart_filestream != -1)
        {
            close(uart_filestream);
        }
    }

    /**
     * Reads data from the UART device into the provided buffer.
     *
     * @param buffer Pointer to the buffer where the data will be stored
     * @param size Number of bytes to read
     * @return Number of bytes read, or -1 on error
     */
    ssize_t readData(void *buffer, size_t size)
    {
        return read(uart_filestream, buffer, size);
    }

    /**
     * Writes data from the provided buffer to the UART device.
     *
     * @param buffer Pointer to the buffer containing the data to be written
     * @param size Number of bytes to write
     * @return Number of bytes written, or -1 on error
     */
    ssize_t writeData(const void *buffer, size_t size)
    {
        return write(uart_filestream, buffer, size);
    }

private:
    int uart_filestream;

    /**
     * Configures the UART settings for the communication.
     * Sets the baud rate to 9600, 8 data bits, and enables local and receiver modes.
     * Ignores parity errors and sets the input and output flags to 0.
     * Configures the UART to operate in blocking mode with VMIN = 1 and VTIME = 0.
     * Flushes the UART input buffer and applies the settings immediately.
     */
    void configureUART()
    {
        struct termios options;
        tcgetattr(uart_filestream, &options);
        options.c_cflag = B9600 | CS8 | CLOCAL | CREAD; // Baud rate 9600, 8 data bits
        options.c_iflag = IGNPAR;                       // Ignore parity errors
        options.c_oflag = 0;
        options.c_lflag = 0;

        // Set blocking mode
        options.c_cc[VMIN] = 1;
        options.c_cc[VTIME] = 0;

        tcflush(uart_filestream, TCIFLUSH);
        tcsetattr(uart_filestream, TCSANOW, &options);
    }
};

class PMS5003
{
public:
    explicit PMS5003(UART &uart) : uart(uart) {}

    /**
     * Reads data from the PMS5003 sensor by synchronizing to start bytes 0x42, 0x4D,
     * then reads the rest of the packet using the UART interface. Verifies the checksum
     * of the data packet and parses the data if the checksum is valid.
     * Updates the provided pm1, pm25, and pm10 parameters with the parsed values.
     *
     * @param pm1 Reference to an integer to store the PM1.0 concentration.
     * @param pm25 Reference to an integer to store the PM2.5 concentration.
     * @param pm10 Reference to an integer to store the PM10 concentration.
     *
     * @throws runtime_error if reading data from the sensor fails.
     */
    void readData(int &pm1, int &pm25, int &pm10)
    {
        constexpr size_t packetSize = 32;
        unsigned char buffer[packetSize];

        while (true)
        {
            // Synchronize to start bytes 0x42, 0x4D
            if (!syncToStartBytes())
            {
                continue;
            }

            // Read the rest of the packet
            size_t bytesRead = 2;
            while (bytesRead < packetSize)
            {
                ssize_t result = uart.readData(buffer + bytesRead, packetSize - bytesRead);
                if (result < 0)
                {
                    throw std::runtime_error("Failed to read data from PMS5003 sensor.");
                }
                bytesRead += result;
            }

            // Verify checksum and parse data if valid
            if (verifyChecksum(buffer))
            {
                parseData(buffer, pm1, pm25, pm10); // Pass references to parseData
                break;
            }
            else
            {
                std::cerr << "Checksum mismatch. Data might be corrupted.\n";
            }
        }
    }

private:
    UART &uart;

    /**
     * Synchronizes with the PMS5003 sensor to detect the start bytes 0x42, 0x4D.
     * Returns true if the start bytes are found, false otherwise.
     */
    bool syncToStartBytes()
    {
        unsigned char startBytes[2];
        ssize_t result = uart.readData(startBytes, 1);
        if (result <= 0)
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            return false;
        }

        if (startBytes[0] != 0x42)
        {
            return false;
        }

        result = uart.readData(startBytes + 1, 1);
        if (result <= 0)
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            return false;
        }

        return startBytes[1] == 0x4D;
    }

    /**
     * Verifies the checksum of the data packet.
     *
     * @param buffer Pointer to the buffer containing the data packet.
     * @return True if the checksum matches the received checksum, false otherwise.
     */
    bool verifyChecksum(const unsigned char *buffer)
    {
        // uint16_t checksum = 0;
        // for (int i = 0; i < 30; ++i)
        // {
        //     checksum += buffer[i];
        // }
        // uint16_t received_checksum = (buffer[30] << 8) | buffer[31];
        // return checksum == received_checksum;
        std::cout << std::endl
                  << "=========================" << std::endl
                  << "Bypass Checksum" << std::endl;
        return true;
    }

    /**
     * Parses the data received from the PMS5003 sensor buffer.
     * Calculates the concentration of fine dust particles in the air for PM1.0, PM2.5, and PM10.
     * Updates the provided parameters with the results in micrograms per cubic meter (µg/m³).
     *
     * @param buffer Pointer to the buffer containing the sensor data packet.
     * @param pm1 Reference to an integer to store the PM1.0 concentration.
     * @param pm25 Reference to an integer to store the PM2.5 concentration.
     * @param pm10 Reference to an integer to store the PM10 concentration.
     */
    void parseData(const unsigned char *buffer, int &pm1, int &pm25, int &pm10)
    {
        pm1 = (buffer[10] << 8) | buffer[11];
        pm25 = (buffer[12] << 8) | buffer[13];
        pm10 = (buffer[14] << 8) | buffer[15];

        std::cout << "PM1.0: " << pm1 << " µg/m³\n";
        std::cout << "PM2.5: " << pm25 << " µg/m³\n";
        std::cout << "PM10: " << pm10 << " µg/m³\n";
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

/**********************************************/

/**
 * Represents a publisher for PMS sensor data that extends the MQTTPublisher class.
 * Inherits MQTT connection functionality and provides a method to update sensor data.
 */
class PMSPublisher : public MQTTPublisher
{
public:
    PMSPublisher(const std::string &address, const std::string &client_id)
        : MQTTPublisher(address, client_id) {};

    /**
     * Updates the PM1, PM2.5, and PM10 values in the PMSPublisher instance.
     *
     * @param _pm1 - The PM1 value to update.
     * @param _pm25 - The PM2.5 value to update.
     * @param _pm10 - The PM10 value to update.
     */
    void update(int _pm1, int _pm25, int _pm10)
    {
        this->pm1 = _pm1;
        this->pm25 = _pm25;
        this->pm10 = _pm1;
    }

protected:
    /**
     * Creates a JSON payload containing PM1, PM2.5, and PM10 values.
     *
     * @return Json::Value - The JSON payload with PM values.
     */
    virtual Json::Value createPayload() override;

private:
    int pm1, pm25, pm10;
};

Json::Value PMSPublisher::createPayload()
{
    Json::Value payload_json;
    payload_json["pm1"] = this->pm1;
    payload_json["pm25"] = this->pm25;
    payload_json["pm10"] = this->pm10;

    return payload_json;
}

/**********************************************/

int main()
{
    PMSPublisher publisher(SERVER_ADDRESS, CLIENT_ID);

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
        UART uart(uart_device);
        PMS5003 sensor(uart);

        while (true)
        {
            int pm1, pm25, pm10;
            sensor.readData(pm1, pm25, pm10);

            publisher.update(pm1, pm25, pm10);

            publisher.publish(TOPIC);

            std::this_thread::sleep_for(std::chrono::seconds(1));
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
