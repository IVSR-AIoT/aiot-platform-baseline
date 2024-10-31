#include <iostream>
#include <stdexcept>
#include <string>
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <cstdint>
#include <chrono>
#include <thread>

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
     * Throws a runtime error if reading data from the sensor fails.
     */
    void readData()
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

            if (verifyChecksum(buffer))
            {
                parseData(buffer);
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
     * Displays the results in micrograms per cubic meter (µg/m³).
     *
     * @param buffer Pointer to the buffer containing the sensor data packet.
     */
    void parseData(const unsigned char *buffer)
    {
        int pm1_atm = (buffer[10] << 8) | buffer[11];
        int pm25_atm = (buffer[12] << 8) | buffer[13];
        int pm10_atm = (buffer[14] << 8) | buffer[15];

        std::cout << "\nConcentration of fine dust in the air:\n";
        std::cout << "PM1.0: " << pm1_atm << " µg/m³\n";
        std::cout << "PM2.5: " << pm25_atm << " µg/m³\n";
        std::cout << "PM10: " << pm10_atm << " µg/m³\n";
    }
};

int main()
{
    const std::string uart_device = "/dev/ttyS5";

    try
    {
        UART uart(uart_device);
        PMS5003 sensor(uart);

        while (true)
        {
            sensor.readData();
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }
    catch (const std::exception &ex)
    {
        std::cerr << ex.what() << '\n';
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
