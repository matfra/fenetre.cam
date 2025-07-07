# fenetre

Takes pictures periodically ( Raspberry Pi camera, GoPro, local command or any URL), make timelapse and publish them on a self-hosted website. Try it with you own cameras! Example: https://fenetre.cam


This is the inspired by https://github.com/matfra/isitfoggy.today and https://github.com/matfra/camaredn

This is mostly written in Python and meant to run on Linux in a virtualenv or in docker.

Currently supported picture sources:
- any local command yielding an image format supported by PIL https://pillow.readthedocs.io/en/latest/reference/features.html#features-module
- GoPro Hero 9+ via Bluetooth + WiFi with https://gopro.github.io/OpenGoPro/
- Raspberry Pi camera (tested with v2 and HQ)

## TODO:

## How to run?
If you have a GoPro, you will need to run
`git submodule update --init --recursive`


### UI:
- Each camera should have a main visualization page
- If cameras don't have coordinates (lat and lon), don't display the map. Display only the right panel

### Utility
- Enforce the disk usage limits
- Add an http listener for a prometheus exporter
- Create counters for the number of pictures taken since start for each camera
- Create counters for the size of each camera directory

### Picture capture:
- Implement native libcamera python functions instead of relying on libcamera-still
- Add a preprocessing stage based on the previous picture to customize settings for the next picture
- Add a postprocessing stage with basic features to crop, resize, correct AWB, etc.
- Add support for time of day (day/sunset/sunrise/night) for different frequency and settings/profiles

### GoPro
- Add the ability to enable Wi-Fi AP on a GoPro using Bluetooth
- Fix unittests with the correct paths
- Create a custom photo profile
- Use the Python SDK https://gopro.github.io/OpenGoPro/python_sdk/api.html

## Configuration Management Interface

Fenetre now includes a separate HTTP server for managing its configuration (`config.yaml`) dynamically. This allows for viewing, updating, and reloading the application's configuration without needing to restart the main `fenetre.py` process.

**By default, the configuration server runs on `http://0.0.0.0:8889`.**

### Prerequisites

1.  **Install Flask**: If not already installed, add `Flask` to your `requirements.txt` and install it:
    ```bash
    pip install Flask PyYAML
    ```

2.  **Running `config_server.py`**:
    The configuration server (`config_server.py`) must be run as a separate process alongside the main `fenetre.py` application.
    ```bash
    python config_server.py
    ```
    You can configure its host, port, the path to `config.yaml`, and the path to `fenetre.pid` using environment variables:
    *   `CONFIG_SERVER_HOST` (default: `0.0.0.0`)
    *   `CONFIG_SERVER_PORT` (default: `8889`)
    *   `CONFIG_FILE_PATH` (default: `config.yaml`) - This should point to the same `config.yaml` used by `fenetre.py`.
    *   `FENETRE_PID_FILE` (default: `fenetre.pid`) - `fenetre.py` writes its process ID here, which the config server uses to send a reload signal. Ensure this path is consistent between both processes.

### API Endpoints

*   **`GET /config`**
    *   Retrieves the current content of `config.yaml`.
    *   **Response**: `200 OK` with JSON body of the configuration.

*   **`PUT /config`**
    *   Updates `config.yaml` with the provided YAML data in the request body.
    *   **Request Body**: Raw YAML content.
    *   **Response**: `200 OK` with `{"message": "Configuration updated successfully. Reload is required to apply changes."}`.
    *   **Note**: This only updates the file on disk. A subsequent call to `/config/reload` is needed to make the running `fenetre.py` application apply these changes.

*   **`POST /config/reload`**
    *   Signals the main `fenetre.py` process to reload its configuration from `config.yaml`.
    *   `fenetre.py` will attempt to apply changes, which may include:
        *   Updating global settings.
        *   Starting/stopping threads for added/removed cameras.
        *   Restarting the main file-serving HTTP server if its configuration (e.g., port) changed.
        *   Updating `snap_interval_s` for existing cameras.
    *   **Response**: `200 OK` with `{"message": "Reload signal sent to process <pid>."}` if successful.
    *   **Important**: The main `fenetre.py` application must be running and have successfully written its PID to the `FENETRE_PID_FILE` (default: `fenetre.pid`) for the reload signal to be sent.

### Example Workflow (using `curl`)

1.  **View current configuration**:
    ```bash
    curl http://localhost:8889/config
    ```

2.  **Update configuration**:
    Save your new configuration to a file, e.g., `new_config.yaml`.
    ```bash
    curl -X PUT -H "Content-Type: application/x-yaml" --data-binary "@new_config.yaml" http://localhost:8889/config
    ```
    *(Note: `application/x-yaml` or `text/yaml` are common Content-Types for YAML)*

3.  **Reload configuration in `fenetre.py`**:
    ```bash
    curl -X POST http://localhost:8889/config/reload
    ```

### Limitations of Dynamic Reload

*   While many settings can be reloaded dynamically, changes to certain fundamental aspects of existing, active camera threads (e.g., changing a camera's `url` or `postprocessing` steps) might not fully apply without a full restart of `fenetre.py`. The reload mechanism primarily handles adding/removing cameras, updating global settings, and specific dynamic parameters like `snap_interval_s`.
*   The timelapse and daylight processing loops currently pick up changes to `global_config` (like `ffmpeg_options`) upon their next iteration but are not fully restarted.