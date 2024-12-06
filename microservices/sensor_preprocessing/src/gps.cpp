 // g++ -o gps gps.cpp -lpaho-mqttpp3 -lpaho-mqtt3as -ljsoncpp -std=c++11
#include <iostream>
#include <string>
#include <sstream>
#include <iomanip>
#include <cmath>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <thread>
#include <chrono>
#include <cstring>
#include <cerrno>
#include <fstream> 

#include <json/json.h>
#include <mqtt/async_client.h>

using namespace std;

// read JSON configuration file
Json::Value read_config(const string& filename) {
    ifstream config_file(filename);
    if (!config_file.is_open()) {
        cerr << "Cannot open file " << filename << endl;
        exit(1); 
    }

    Json::Value config;
    config_file >> config;
    return config;
}

// Get configuration information from JSON object
void load_config(const Json::Value& config, 
                 string& server_address, string& client_id, string& topic, 
                 string& gps_serial_port, int& gps_baud_rate) {

    server_address = config["mqtt"]["server_address"].asString();
    client_id = config["mqtt"]["client_id"].asString();
    topic = config["mqtt"]["topic"].asString();

    gps_serial_port = config["gps"]["serial_port"].asString();
    gps_baud_rate = config["gps"]["baud_rate"].asInt();
}


// MQTTPublisher Class
class MQTTPublisher
{
public:
    MQTTPublisher(const string &address, const string &client_id)
        : client_(address, client_id)
    {
        connOpts_.set_clean_session(true);
    }

    ~MQTTPublisher()
    {
        try
        {
            disconnect();
        }
        catch (const mqtt::exception &exc)
        {
            cerr << "Error during disconnect: " << exc.what() << endl;
        }
    }

    bool connect()
    {
        try
        {
            cout << "Connecting to the MQTT broker at " << client_.get_server_uri() << "..." << endl;
            auto tok = client_.connect(connOpts_);
            tok->wait();
            cout << "Connected." << endl;
            return true;
        }
        catch (const mqtt::exception &exc)
        {
            cerr << "MQTT Exception during connect: " << exc.what() << endl;
            return false;
        }
    }

    bool publish(const string &topic, const string& payload, int qos = 1)
    {
        try
        {
            auto pubmsg = mqtt::make_message(topic, payload);
            pubmsg->set_qos(qos);

            cout << "Publishing message..." << endl;
            client_.publish(pubmsg)->wait_for(chrono::seconds(10));
            cout << "Message published." << endl;
            return true;
        }
        catch (const mqtt::exception &exc)
        {
            cerr << "MQTT Exception during publish: " << exc.what() << endl;
            return false;
        }
    }

    void disconnect()
    {
        try
        {
            if (client_.is_connected())
            {
                cout << "Disconnecting..." << endl;
                client_.disconnect()->wait();
                cout << "Disconnected." << endl;
            }
        }
        catch (const mqtt::exception &exc)
        {
            cerr << "MQTT Exception during disconnect: " << exc.what() << endl;
        }
    }

private:
    mqtt::async_client client_;
    mqtt::connect_options connOpts_;
};

class GPSPublisher : public MQTTPublisher
{
public:
    GPSPublisher(const string &address, const string &client_id)
        : MQTTPublisher(address, client_id), latitude(0.0), longitude(0.0) {}

    void update(double lat, double lon)
    {
        latitude = lat;
        longitude = lon;
    }

    string createPayload() 
    {
        Json::Value payload_json;
        payload_json["latitude"] = this->latitude;
        payload_json["longitude"] = this->longitude;

        auto now = chrono::system_clock::now();
        time_t now_c = chrono::system_clock::to_time_t(now);
        string time_str = ctime(&now_c);
        if (!time_str.empty() && time_str.back() == '\n')
        {
            time_str.pop_back();
        }
        payload_json["timestamp"] = time_str;

        Json::Value message_json;
        message_json["type"] = "gps";
        message_json["payload"] = payload_json;

        Json::StreamWriterBuilder writer;
        return Json::writeString(writer, message_json);
    }


private:
    double latitude;
    double longitude;
};

int open_serial_port(const char* portname) {
    int fd = open(portname, O_RDWR | O_NOCTTY | O_NDELAY);
    if (fd == -1) {
        perror("Unable to open serial port");
        exit(1);
    }
    fcntl(fd, F_SETFL, 0);
    return fd;
}

void setup_serial_port(int fd, int gps_baud_rate) {
    struct termios options;
    tcgetattr(fd, &options);
    cfsetispeed(&options, gps_baud_rate);
    cfsetospeed(&options, gps_baud_rate);
    options.c_cflag |= (CLOCAL | CREAD);  // Open serial port
    options.c_cflag &= ~CSIZE;
    options.c_cflag |= CS8;  // 8 data bits
    options.c_cflag &= ~CSTOPB;  // 1 stop bit
    options.c_cflag &= ~PARENB;  // No parity
    options.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG); // Non-canonical mode
    options.c_iflag &= ~(IXON | IXOFF | IXANY); // Disable flow control
    options.c_oflag &= ~OPOST; // Disable post-processing
    tcsetattr(fd, TCSANOW, &options);
}

double convert_to_decimal(double ddmm, char direction) {
    int degrees = static_cast<int>(ddmm) / 100;
    double minutes = ddmm - (degrees * 100);
    double decimal = degrees + (minutes / 60.0);
    if (direction == 'S' || direction == 'W') {
        decimal = -decimal;
    }
    return decimal;
}

string read_serial_data(int fd) {
    char buf[256];
    memset(buf, 0, sizeof(buf));

    int n = read(fd, buf, sizeof(buf) - 1);

    if (n < 0) {
        if (errno == EAGAIN) {
            return "";  
        } else {
            perror("Error reading from serial port");
            exit(1);
        }
    }

    return string(buf);
}

// Function to check GPS status
bool check_gps_status(int fd) {
    const char* cmd_check = "AT+CGPS?\r\n";
    write(fd, cmd_check, strlen(cmd_check));

    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    string response = read_serial_data(fd);
    if (response.find("CGPS: 1") != string::npos) {
        cout << "GPS is already ON." << endl;
        return true;  
    }
    return false; 
}

int main() {
    // Read configuration from gps.json file
    Json::Value config = read_config("gps.json");

    // Declare variables to store configuration
    string SERVER_ADDRESS, CLIENT_ID, TOPIC, gps_serial_port;
    int gps_baud_rate; 

    // Load configuration from JSON object
    load_config(config, SERVER_ADDRESS, CLIENT_ID, TOPIC, gps_serial_port, gps_baud_rate);

    // Initialize MQTT Publisher
    GPSPublisher publisher(SERVER_ADDRESS, CLIENT_ID);
    try
    {
        if (!publisher.connect())
        {
            cerr << "Failed to connect to MQTT server, exiting..." << endl;
            return EXIT_FAILURE;
        }
    }
    catch (const std::exception &ex)
    {
        cerr << "Failed to connect to MQTT server, exiting...\n";
        cerr << ex.what() << '\n';
        return EXIT_FAILURE;
    }

    // Setup serial port for GPS  
    int serial_fd = open_serial_port(gps_serial_port.c_str());  
    setup_serial_port(serial_fd, gps_baud_rate);  

    if (!check_gps_status(serial_fd)) {
        const char* cmd_on = "AT+CGPS=1\r\n";
        write(serial_fd, cmd_on, strlen(cmd_on));
        cout << "GPS is now ON." << endl;

        std::this_thread::sleep_for(std::chrono::seconds(10)); 
    }

    while (true) {
        const char* cmd_info = "AT+CGPSINFO\r\n";
        write(serial_fd, cmd_info, strlen(cmd_info));

        std::this_thread::sleep_for(std::chrono::milliseconds(500));

        string gps_data = read_serial_data(serial_fd);
        
        if (gps_data.empty()) {
            std::this_thread::sleep_for(std::chrono::seconds(5));  
            continue;
        }
        
        cout << "Received GPS data: " << gps_data << endl;

        if (gps_data.find("+CGPSINFO:") != string::npos) {
            size_t pos = gps_data.find("+CGPSINFO:");
            if (pos != string::npos) {
                string gps_info = gps_data.substr(pos + 11);
                cout << "GPS info: " << gps_info << endl;
                
                // Parse latitude and longitude
                double lat_ddmm, lon_ddmm;
                char lat_dir, lon_dir;
                int parsed = sscanf(gps_info.c_str(), "%lf,%c,%lf,%c", &lat_ddmm, &lat_dir, &lon_ddmm, &lon_dir);

                if (parsed == 4) {
                    double latitude = convert_to_decimal(lat_ddmm, lat_dir);
                    double longitude = convert_to_decimal(lon_ddmm, lon_dir);

                    if (latitude != 0.0 && longitude != 0.0) {
                        publisher.update(latitude, longitude);

                        // Create payload JSON
                        string payload = publisher.createPayload();

                        // Publish data to MQTT
                        if (publisher.publish(TOPIC, payload)) {
                            cout << "Latitude: " << latitude << ", Longitude: " << longitude << endl;
                            cout << "Google Maps URL: https://www.google.com/maps?q=" << fixed << setprecision(6)
                                 << latitude << "," << longitude << endl;
                        } else {
                            cerr << "Failed to publish GPS data to MQTT." << endl;
                        }
                    } else {
                        cout << "Invalid GPS data received." << endl;
                    }
                } else {
                    cout << "Failed to parse GPS data correctly." << endl;
                }
            }
        }

        std::this_thread::sleep_for(std::chrono::seconds(10));
    }

    close(serial_fd);
    publisher.disconnect();

    return EXIT_SUCCESS;
}
