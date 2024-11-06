# Use the official Python slim image
FROM python:3.10.12-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (if any are required)
# RUN apt-get update && apt-get install -y [dependencies]

# Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Ensure the entrypoint script has execution permissions
RUN chmod +x entrypoint.sh

# Set environment variables (optional if using --env-file)
# ENV CLOUD_AMQP_URL=amqp://user:pass@host:port/vhost

# Set the entrypoint to the shell script
ENTRYPOINT ["./entrypoint.sh"]
