#!/bin/bash

# Start all Docker Compose services
start_services() {
    echo "Starting services..."

    # Start backend
    docker compose -f docker-compose.backend.yml up -d --build

    # Start frontend
    docker compose -f docker-compose.frontend.yml up -d --build

    echo "All services have been started."
}

# Stop all Docker Compose services
stop_services() {
    echo "Shutting down services..."

    # Stop backend
    docker compose -f docker-compose.backend.yml down

    # Stop frontend
    docker compose -f docker-compose.frontend.yml down

    echo "All services have been shut down."
}

# Check the argument to decide whether to start or stop services
if [ "$1" == "start" ]; then
    start_services
elif [ "$1" == "stop" ]; then
    stop_services
else
    echo "Usage: $0 {start|stop}"
    exit 1
fi
