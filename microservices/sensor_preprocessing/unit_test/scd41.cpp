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

int main()
{
    const std::string i2c_bus = "/dev/i2c-3";
    const int scd41_address = 0x62;

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
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
