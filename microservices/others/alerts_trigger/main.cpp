#include <iostream>
#include <fstream>
#include <string>
#include <thread>
#include <chrono>
#include <fstream>
#include "mqtt/async_client.h"

// GPIO configuration
const std::string GPIO_PIN = "79"; // GPIO pin number as a string
const std::string GPIO_EXPORT = "/sys/class/gpio/export";
const std::string GPIO_UNEXPORT = "/sys/class/gpio/unexport";
const std::string GPIO_DIRECTION = "/sys/class/gpio/gpio" + GPIO_PIN + "/direction";
const std::string GPIO_VALUE = "/sys/class/gpio/gpio" + GPIO_PIN + "/value";

// Sound command
const std::string SOUND_COMMAND = "aplay /home/orangepi/aiot-platform-baseline/microservices/others/alerts_trigger/alert_sound.wav";

// MQTT server settings (adjust as needed)
const std::string SERVER_ADDRESS{"tcp://localhost:1883"};
const std::string CLIENT_ID{"alert_subscriber"};
const std::string TOPIC{"/alerts"};

// Function to export GPIO
void exportGPIO()
{
    std::ofstream exportFile(GPIO_EXPORT);
    if (!exportFile)
    {
        std::cerr << "Failed to export GPIO pin." << std::endl;
        exit(EXIT_FAILURE);
    }
    exportFile << GPIO_PIN;
    exportFile.close();
}

// Function to unexport GPIO
void unexportGPIO()
{
    std::ofstream unexportFile(GPIO_UNEXPORT);
    if (!unexportFile)
    {
        std::cerr << "Failed to unexport GPIO pin." << std::endl;
        return;
    }
    unexportFile << GPIO_PIN;
    unexportFile.close();
}

// Function to set GPIO direction
void setGPIODirection(const std::string &direction)
{
    std::ofstream directionFile(GPIO_DIRECTION);
    if (!directionFile)
    {
        std::cerr << "Failed to set GPIO direction." << std::endl;
        exit(EXIT_FAILURE);
    }
    directionFile << direction;
    directionFile.close();
}

// Function to write GPIO value
void writeGPIOValue(const std::string &value)
{
    std::ofstream valueFile(GPIO_VALUE);
    if (!valueFile)
    {
        std::cerr << "Failed to write GPIO value." << std::endl;
        exit(EXIT_FAILURE);
    }
    valueFile << value;
    valueFile.close();
}

// Callback class to handle incoming messages and connection events
class callback : public virtual mqtt::callback
{
public:
    // This function is called when a new message arrives
    void message_arrived(mqtt::const_message_ptr msg) override
    {
        std::string payload = msg->to_string();
        std::cout << "Received message on topic " << msg->get_topic()
                  << " with payload: " << payload << std::endl;

        // Check if the payload equals "1"
        if (payload == "1")
        {
            writeGPIOValue("1");                                  // Turn on relay
            system(SOUND_COMMAND.c_str());                        // Play sound
            std::this_thread::sleep_for(std::chrono::seconds(1)); // Wait for 1 second
            writeGPIOValue("0");
        }
    }
};

int main()
{
    // Export and configure GPIO
    exportGPIO();
    setGPIODirection("out");
    writeGPIOValue("0"); // Ensure relay is off

    // Create the MQTT asynchronous client
    mqtt::async_client client(SERVER_ADDRESS, CLIENT_ID);

    // Set our callback handler
    callback cb;
    client.set_callback(cb);

    // Connection options (customize as needed)
    mqtt::connect_options connOpts;

    try
    {
        std::cout << "Connecting to the MQTT broker at " << SERVER_ADDRESS << "..." << std::endl;
        client.connect(connOpts)->wait();
        std::cout << "Connected. Subscribing to topic: " << TOPIC << std::endl;
        client.subscribe(TOPIC, 1)->wait();

        // Keep the main thread alive so that it continues to process incoming messages.
        // In a production application, you might use a more sophisticated loop or signal handling.
        while (true)
        {
            std::this_thread::sleep_for(std::chrono::microseconds(100));
        }

        // Optionally, disconnect (unreachable in this example)
        // client.disconnect()->wait();
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "Error: " << exc.what() << std::endl;
        return 1;
    }

    return 0;
}
