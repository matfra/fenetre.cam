# Dockerfile

# Use an official Python 3.12 image as a base
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Install required system packages (ffmpeg)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies if necessary
# Uncomment the following line if you need to install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the local files into the container
COPY camaredn.py timelapse.py daylight.py archive.py /app/

# Set entrypoint to allow dynamic config.yaml file specification
ENTRYPOINT ["python", "camaredn.py", "--config"]

