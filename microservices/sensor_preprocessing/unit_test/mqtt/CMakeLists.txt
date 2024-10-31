# CMakeLists.txt
cmake_minimum_required(VERSION 3.5)
project(mqtt_examples)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PahoMqttCpp REQUIRED)

add_executable(async_pub async_pub.cpp)
target_link_libraries(async_pub PahoMqttCpp::paho-mqttpp3)

add_executable(async_sub async_sub.cpp)
target_link_libraries(async_sub PahoMqttCpp::paho-mqttpp3)