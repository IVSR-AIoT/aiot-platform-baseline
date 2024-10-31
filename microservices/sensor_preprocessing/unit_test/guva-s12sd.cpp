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
    explicit ADS1118(SPI &spi, float vRef = 4.096f, float conversionFactor = 0.1f)
        : spi(spi), vRef(vRef), conversionFactor(conversionFactor) {}

    /**
     * Reads the analog-to-digital converter (ADC) value from the ADS1118.
     *
     * @return The ADC value read from the ADS1118.
     */
    int16_t readADC()
    {
        uint8_t tx[2] = {0x85, 0x83}; // Configuration command to ADS1118
        uint8_t rx[2] = {0, 0};

        spi.transfer(tx, rx, 2);

        int16_t result = (static_cast<int16_t>(rx[0]) << 8) | rx[1];
        return result;
    }

    /**
     * Calculates the voltage based on the raw ADC value and the reference voltage (vRef).
     *
     * @param rawValue The raw ADC value to calculate the voltage from.
     * @return The calculated voltage based on the raw ADC value and the reference voltage.
     */
    float calculateVoltage(int16_t rawValue) const
    {
        return (rawValue * vRef) / 32768.0f;
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

int main()
{
    const std::string spi_device = "/dev/spidev1.1";
    const uint32_t spi_speed = 500000;
    const uint8_t spi_mode = SPI_MODE_1;
    const uint8_t bits_per_word = 8;

    try
    {
        SPI spi(spi_device, spi_speed, spi_mode, bits_per_word);
        ADS1118 ads1118(spi);

        while (true)
        {
            int16_t rawValue = ads1118.readADC();
            float voltage = ads1118.calculateVoltage(rawValue);
            float uvIntensity = ads1118.calculateUVIntensity(voltage);

            std::cout << "Raw Value: " << rawValue
                      << ", Voltage: " << voltage << " V"
                      << ", UV Intensity: " << uvIntensity << " mW/cm²" << std::endl;

            std::this_thread::sleep_for(std::chrono::seconds(2));
        }
    }
    catch (const std::exception &ex)
    {
        std::cerr << ex.what() << '\n';
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}