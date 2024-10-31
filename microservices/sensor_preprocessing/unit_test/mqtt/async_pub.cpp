#include <iostream>
#include <mqtt/async_client.h>

const std::string SERVER_ADDRESS{"tcp://localhost:1883"};
const std::string CLIENT_ID{"mqtt_cpp_publisher"};
const std::string TOPIC{"test/topic"};

int main()
{
    mqtt::async_client client(SERVER_ADDRESS, CLIENT_ID);

    mqtt::connect_options connOpts;
    connOpts.set_clean_session(true);

    try
    {
        // Connect to the MQTT broker
        std::cout << "Connecting to the MQTT broker at " << SERVER_ADDRESS << "..." << std::endl;
        auto tok = client.connect(connOpts);
        tok->wait();
        std::cout << "Connected." << std::endl;

        // Publish a message
        std::string payload = "Hello MQTT from C++!";
        auto pubmsg = mqtt::make_message(TOPIC, payload);
        pubmsg->set_qos(1);

        std::cout << "Publishing message..." << std::endl;
        client.publish(pubmsg)->wait_for(std::chrono::seconds(10));
        std::cout << "Message published." << std::endl;

        // Disconnect
        std::cout << "Disconnecting..." << std::endl;
        client.disconnect()->wait();
        std::cout << "Disconnected." << std::endl;
    }
    catch (const mqtt::exception &exc)
    {
        std::cerr << "MQTT Exception: " << exc.what() << std::endl;
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
