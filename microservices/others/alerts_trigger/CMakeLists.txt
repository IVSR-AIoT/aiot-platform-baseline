cmake_minimum_required(VERSION 3.5)
project(alerts_trigger)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Paho MQTT C++ library
find_path(PAHO_MQTT_CPP_INCLUDE_DIR mqtt/async_client.h)

if(PAHO_MQTT_CPP_INCLUDE_DIR)
    message(STATUS "Found Paho MQTT C++ includes at ${PAHO_MQTT_CPP_INCLUDE_DIR}")
else()
    message(FATAL_ERROR "Could not find Paho MQTT C++ includes")
endif()

find_library(PAHO_MQTT_CPP_LIB paho-mqttpp3)

if(PAHO_MQTT_CPP_LIB)
    message(STATUS "Found Paho MQTT C++ library at ${PAHO_MQTT_CPP_LIB}")
else()
    message(FATAL_ERROR "Could not find Paho MQTT C++ library")
endif()

# Find Paho MQTT C library (dependency of the C++ library)
find_library(PAHO_MQTT_C_LIB paho-mqtt3as)

if(PAHO_MQTT_C_LIB)
    message(STATUS "Found Paho MQTT C library at ${PAHO_MQTT_C_LIB}")
else()
    message(FATAL_ERROR "Could not find Paho MQTT C library")
endif()

# **Use pkg-config to find JsonCpp**
find_package(PkgConfig REQUIRED)
pkg_check_modules(JSONCPP jsoncpp)

# Source files
set(ALERTS_SOURCES
    main.cpp
)

# Add executable
add_executable(alert_trigger ${ALERTS_SOURCES})
target_include_directories(alert_trigger PRIVATE
    ${PAHO_MQTT_CPP_INCLUDE_DIR}
)
target_link_libraries(alert_trigger
    ${PAHO_MQTT_CPP_LIB}
    ${PAHO_MQTT_C_LIB}
    pthread
    rt
)