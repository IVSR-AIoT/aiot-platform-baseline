cmake_minimum_required(VERSION 3.5)
project(guva_s12sd_publisher)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Include the src directory
include_directories(
    ${PROJECT_SOURCE_DIR}/src
)

# Find Paho MQTT C++ library
find_path(PAHO_MQTT_CPP_INCLUDE_DIR mqtt/async_client.h)
if (PAHO_MQTT_CPP_INCLUDE_DIR)
    message(STATUS "Found Paho MQTT C++ includes at ${PAHO_MQTT_CPP_INCLUDE_DIR}")
else()
    message(FATAL_ERROR "Could not find Paho MQTT C++ includes")
endif()

find_library(PAHO_MQTT_CPP_LIB paho-mqttpp3)
if (PAHO_MQTT_CPP_LIB)
    message(STATUS "Found Paho MQTT C++ library at ${PAHO_MQTT_CPP_LIB}")
else()
    message(FATAL_ERROR "Could not find Paho MQTT C++ library")
endif()

# Find Paho MQTT C library (dependency of the C++ library)
find_library(PAHO_MQTT_C_LIB paho-mqtt3as)
if (PAHO_MQTT_C_LIB)
    message(STATUS "Found Paho MQTT C library at ${PAHO_MQTT_C_LIB}")
else()
    message(FATAL_ERROR "Could not find Paho MQTT C library")
endif()

# **Use pkg-config to find JsonCpp**
find_package(PkgConfig REQUIRED)
pkg_check_modules(JSONCPP jsoncpp)

if (JSONCPP_FOUND)
    message(STATUS "Found JsonCpp via pkg-config")
else()
    message(FATAL_ERROR "Could not find JsonCpp via pkg-config")
endif()

# Source files
set(GUVA_SOURCES
    src/guva-s12sd.cpp
)
set(PMS_SOURCES
    src/pms5003.cpp
)
set(SCD_SOURCES
    src/scd41.cpp
)

# Add executable
add_executable(guva_publisher ${GUVA_SOURCES})
target_include_directories(guva_publisher PRIVATE
    ${PAHO_MQTT_CPP_INCLUDE_DIR}
    ${JSONCPP_INCLUDE_DIRS}
)
target_link_libraries(guva_publisher
    ${PAHO_MQTT_CPP_LIB}
    ${PAHO_MQTT_C_LIB}
    ${JSONCPP_LIBRARIES}
    pthread
    rt
)

# Add executable
add_executable(pms_publisher ${PMS_SOURCES})
target_include_directories(pms_publisher PRIVATE
    ${PAHO_MQTT_CPP_INCLUDE_DIR}
    ${JSONCPP_INCLUDE_DIRS}
)
target_link_libraries(pms_publisher
    ${PAHO_MQTT_CPP_LIB}
    ${PAHO_MQTT_C_LIB}
    ${JSONCPP_LIBRARIES}
    pthread
    rt
)

# Add executable
add_executable(scd_publisher ${SCD_SOURCES})
target_include_directories(scd_publisher PRIVATE
    ${PAHO_MQTT_CPP_INCLUDE_DIR}
    ${JSONCPP_INCLUDE_DIRS}
)
target_link_libraries(scd_publisher
    ${PAHO_MQTT_CPP_LIB}
    ${PAHO_MQTT_C_LIB}
    ${JSONCPP_LIBRARIES}
    pthread
    rt
)