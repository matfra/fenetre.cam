# Dockerfile

# Use an official Python 3.12 image as a base
FROM ubuntu:latest

# Set the working directory inside the container
WORKDIR /opt/fenetre

# Install required system packages (ffmpeg)
RUN apt-get update && \
    apt-get install -y python3-venv ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies if necessary
# Uncomment the following line if you need to install dependencies
RUN python3 -m venv /opt/fenetre/venv
RUN mkdir /opt/fenetre/app
COPY requirements.txt /opt/fenetre/app/requirements.txt
RUN /opt/fenetre/venv/bin/pip install --no-cache-dir -r /opt/fenetre/app/requirements.txt

# Copy the local files into the container
COPY . /opt/fenetre/app
VOLUME /opt/fenetre/config.yaml
VOLUME /opt/fenetre/data
VOLUME /opt/fenetre/logs


# Set entrypoint to allow dynamic config.yaml file specification
# ENTRYPOINT ["/opt/fenetre/venv/bin/python", "/opt/fenetre/app/fenetre.py", "--config"]

