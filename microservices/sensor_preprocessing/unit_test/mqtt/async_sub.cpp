#include <iostream>
#include <mqtt/async_client.h>

const std::string SERVER_ADDRESS{"tcp://localhost:1883"};
const std::string CLIENT_ID{"mqtt_cpp_subscriber"};
const std::string TOPIC{"test/topic"};

class callback : public virtual mqtt::callback
{
public:
    void message_arrived(mqtt::const_message_ptr msg) override
    {
        std::cout << "Message received on topic '" << msg->get_topic() << "': "
                  << msg->to_string() << std::endl;
    }
};

int main()
{
    mqtt::async_client client(SERVER_ADDRESS, CLIENT_ID);

    callback cb;
    client.set_callback(cb);

    mqtt::connect_options connOpts;
    connOpts.set_clean_session(true);

    try
    {
        // Connect to the MQTT broker
        std::cout << "Connecting to the MQTT broker at " << SERVER_ADDRESS << "..." << std::endl;
        client.connect(connOpts)->wait();
        std::cout << "Connected." << std::endl;

        // Subscribe to the topic
        std::cout << "Subscribing to topic '" << TOPIC << "'..." << std::endl;
        client.subscribe(TOPIC, 1)->wait();
        std::cout << "Subscribed." << std::endl;

        // Keep the program running to receive messages
        while (true)
        {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "MQTT Exception: " << exc.what() << std::endl;
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
