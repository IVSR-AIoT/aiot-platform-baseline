#!/bin/bash

while true; do
    python workflow.py
    exit_code=$?
    if [ $exit_code -eq 1 ]; then
        echo "Script exited with code 1, rerunning after 1 second..."
        sleep 1
    else
        break
    fi
done
