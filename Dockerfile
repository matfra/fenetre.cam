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
COPY fenetre.py timelapse.py daylight.py archive.py index.html /app/
COPY config_server.py /app/

# Add the lib directoy to /app
COPY lib /app/lib

# Add the static directory for the config server UI to /app/static
COPY static /app/static/

# Set entrypoint to allow dynamic config.yaml file specification
ENTRYPOINT ["python", "fenetre.py", "--config"]

