# Dockerfile

# Use an official Python 3.12 image as a base
FROM ubuntu:latest

# Install required system packages (ffmpeg)
RUN apt-get update && \
    apt-get install -y python3-venv ffmpeg

# For Intel only
RUN apt-get install -y intel-media-va-driver-non-free intel-opencl-icd libmfx1

RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /srv/fenetre/app
RUN mkdir -p src/fenetre

# Install Python dependencies if necessary
# Uncomment the following line if you need to install dependencies
RUN python3 -m venv /srv/fenetre/venv
COPY requirements.txt .
RUN /srv/fenetre/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy the local files into the container
COPY src/fenetre /srv/fenetre/app/src/fenetre
COPY pyproject.toml .
RUN /srv/fenetre/venv/bin/pip install -e .

# This has to match the host system
RUN groupadd -g 109 render 
# RUN usermod -aG render ubuntu

VOLUME /srv/fenetre/config.yaml
VOLUME /srv/fenetre/data
VOLUME /srv/fenetre/logs

# Set entrypoint to allow dynamic config.yaml file specification
ENTRYPOINT ["/srv/fenetre/venv/bin/fenetre", "--config", "/srv/fenetre/config.yaml"]

