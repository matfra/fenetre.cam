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

### Web UI for Configuration

A web-based UI is provided to easily view and edit the configuration.

*   **Accessing the UI**: Once `config_server.py` is running (see above), open your browser and navigate to:
    ```
    http://<config_server_host>:<config_server_port>/ui
    ```
    For example, if running locally with defaults: `http://localhost:8889/ui`

*   **Features**:
    *   **Load Current Config**: Fetches the active `config.yaml` and dynamically renders an editable form.
    *   **Edit Values**: Modify configuration values directly in the form. Handles nested objects and arrays.
    *   **Add/Remove Array Items**: Basic support for adding new items to arrays and removing existing ones.
    *   **Save to config.yaml**: Saves the current state of the form back to `config.yaml` on the server (converts UI form data to JSON, then server converts JSON to YAML).
    *   **Reload Application Config**: Sends a signal to the main `fenetre.py` process to reload and apply the updated `config.yaml`.
    *   **Link to Visual Crop Tool**: Provides a link to a visual tool for defining crop areas.

#### Visual Crop Configuration Tool

Accessible from the main configuration UI, this tool helps visually define crop areas for cameras.

*   **Access**: Navigate from the main config UI (`/ui`) to the "Visual Crop Configuration Tool" (typically `/static/visual_config.html`).
*   **Functionality**:
    1.  **Select Camera**: Choose a URL-based camera from the dropdown.
    2.  **Fetch Image**: Click "Fetch & Display Image" to load the current image from the camera's URL. The image is displayed, potentially scaled to fit your screen.
    3.  **Define Areas**:
        *   **Crop Area (Red Rectangle)**: Four input fields (X1, Y1, X2, Y2) are initialized to the full displayed image dimensions. Adjust these coordinates manually. A red rectangle on the image visually represents this area.
        *   **Sky Area (Cyan Rectangle, Optional)**: Check "Define Sky Area" to enable its X1,Y1,X2,Y2 input fields. A cyan rectangle will show this area. If a `sky_area` is already defined in `config.yaml` for the camera, its coordinates will be loaded and scaled for display.
        *   **SSIM Area (Yellow Rectangle, Optional)**: Check "Define SSIM Area" to enable its X1,Y1,X2,Y2 input fields. A yellow rectangle will show this area. If an `ssim_area` is defined, it will be loaded and scaled.
        *   **Coordinate System**: All coordinates (X1,Y1,X2,Y2) you input are relative to the *displayed image* on your screen. The tool automatically scales these coordinates to the image's original (natural) dimensions when saving to `config.yaml` or sending for preview.
    4.  **Preview Crop**: Click "Preview Crop". This uses the **Crop Area** coordinates, scales them to the original image dimensions, and sends them to the server with the original fetched image. The server returns a cropped version, displayed below the original. (Sky/SSIM areas are not part of this preview).
    5.  **Apply to Configuration**: Click "Apply Crop to Config" (will be renamed to "Apply Visual Settings" or similar). This will:
        *   Fetch the latest full `config.yaml` content.
        *   For **Crop Area**: Convert the UI X1,Y1,X2,Y2 to a scaled `left,top,right,bottom` string. Update the `postprocessing` array for the selected camera (existing `type: "crop"` steps are removed, new one added).
        *   For **Sky Area**: If "Define Sky Area" is checked, convert its UI coordinates to a scaled `left,top,right,bottom` string and save to the camera's `sky_area` field. If unchecked, `sky_area` is removed from the config.
        *   For **SSIM Area**: If "Define SSIM Area" is checked, convert its UI coordinates to a scaled `left,top,right,bottom` string and save to `ssim_area`. If unchecked, `ssim_area` is removed.
        *   The entire modified configuration is then saved back to `config.yaml`.
    6.  **Reload**: After applying, you'll typically need to go back to the main configuration UI and use the "Reload Application Config" button to make `fenetre.py` pick up the changes.
*   **Layout**: The original image (with drawn rectangles) and the cropped preview image are displayed vertically.
*   **Current Limitations**:
    *   The image fetching for the visual tool primarily supports URL-based cameras.

### API Endpoints

*   **`GET /config`**
    *   Retrieves the current content of `config.yaml`.
    *   **Response**: `200 OK` with JSON body of the configuration (used by the Web UI).

*   **`PUT /config`**
    *   Updates `config.yaml` with the provided JSON data in the request body.
    *   **Request Body**: Raw JSON content. The server converts this to YAML before saving.
    *   **Response**: `200 OK` with `{"message": "Configuration updated successfully (saved as YAML). Reload is required to apply changes."}`.
    *   **Note**: This only updates the file on disk. A subsequent call to `/config/reload` (via API or UI button) is needed to make the running `fenetre.py` application apply these changes.

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
    Save your new configuration to a file, e.g., `new_config.json` (note it should be JSON).
    ```bash
    curl -X PUT -H "Content-Type: application/json" --data-binary "@new_config.json" http://localhost:8889/config
    ```

3.  **Reload configuration in `fenetre.py`**:
    ```bash
    curl -X POST http://localhost:8889/config/reload
    ```

### Limitations of Dynamic Reload

*   While many settings can be reloaded dynamically, changes to certain fundamental aspects of existing, active camera threads (e.g., changing a camera's `url` or `postprocessing` steps) might not fully apply without a full restart of `fenetre.py`. The reload mechanism primarily handles adding/removing cameras, updating global settings, and specific dynamic parameters like `snap_interval_s`.
*   The timelapse and daylight processing loops currently pick up changes to `global_config` (like `ffmpeg_options`) upon their next iteration but are not fully restarted.