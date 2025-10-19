import json  # For handling JSON input
import os
import signal
from io import BytesIO

import requests
import yaml
from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_file,
    send_from_directory,
)
from PIL import Image, ImageOps
from prometheus_client import REGISTRY, Counter, Gauge, generate_latest
from werkzeug.exceptions import BadRequest

from fenetre.gopro import GoPro
from fenetre.ui_utils import copy_public_html_files

# Create metrics
metric_pictures_taken_total = Counter(
    "pictures_taken_total", "Total number of pictures taken", ["camera_name"]
)
metric_last_successful_picture_timestamp = Gauge(
    "capture_last_success_timestamp",
    "Timestamp of the last successfully taken picture",
    ["camera_name"],
)
metric_capture_failures_total = Counter(
    "capture_failures_total", "Total number of capture failures", ["camera_name"]
)
metric_timelapses_created_total = Counter(
    "timelapses_created_total",
    "Total number of timelapses created",
    ["camera_name", "type"],
)
metric_timelapse_queue_size = Gauge(
    "timelapse_queue_size", "Number of timelapses in the queue"
)
metric_camera_directory_size_bytes = Gauge(
    "camera_directory_size_bytes",
    "Size of the camera directory in bytes",
    ["camera_name"],
)
metric_work_directory_size_bytes = Gauge(
    "work_dir_size_bytes", "Size of the work directory in bytes"
)
metric_directories_total = Gauge(
    "dir_total_count", "Total number of directories", ["camera_name"]
)
metric_directories_archived_total = Gauge(
    "dir_archived_count", "Number of archived directories", ["camera_name"]
)
metric_directories_timelapse_total = Gauge(
    "dir_timelapse_count",
    "Number of directories with a timelapse file",
    ["camera_name"],
)
metric_directories_daylight_total = Gauge(
    "dir_daylight_count",
    "Number of directories with a daylight.png file",
    ["camera_name"],
)
metric_picture_width_pixels = Gauge(
    "picture_width_pixels", "Width of the captured picture in pixels", ["camera_name"]
)
metric_picture_height_pixels = Gauge(
    "picture_height_pixels", "Height of the captured picture in pixels", ["camera_name"]
)
metric_picture_size_bytes = Gauge(
    "picture_size_bytes", "Size of the captured picture in bytes", ["camera_name"]
)
metric_picture_iso = Gauge(
    "picture_iso", "ISO value of the captured picture", ["camera_name"]
)
metric_picture_focal_length_mm = Gauge(
    "picture_focal_length_mm",
    "Focal length of the captured picture in mm",
    ["camera_name"],
)
metric_picture_aperture = Gauge(
    "picture_aperture", "Aperture value of the captured picture", ["camera_name"]
)
metric_picture_exposure_time_seconds = Gauge(
    "picture_exposure_time_seconds",
    "Exposure time of the captured picture in seconds",
    ["camera_name"],
)
metric_picture_white_balance = Gauge(
    "picture_white_balance",
    "White balance value of the captured picture",
    ["camera_name"],
)
metric_processing_time_seconds = Gauge(
    "capture_processing_time_seconds",
    "Time it took to fetch and process a new picture",
    ["camera_name"],
)
metric_sleep_time_seconds = Gauge(
    "capture_loop_sleep_time_seconds",
    "Time the camera sleeps between pictures",
    ["camera_name"],
)

# GoPro specific metrics
gopro_state_gauge = Gauge("gopro_state", "GoPro State", ["camera_name", "state_name"])
gopro_setting_gauge = Gauge(
    "gopro_setting", "GoPro Setting", ["camera_name", "setting_name"]
)


app = Flask(__name__)


@app.route("/metrics")
def metrics():
    return Response(generate_latest(REGISTRY), mimetype="text/plain")


@app.route("/config", methods=["GET"])
def get_config():
    config_file_path = app.config.get("FENETRE_CONFIG_FILE")
    if not config_file_path:
        return jsonify({"error": "FENETRE_CONFIG_FILE not set in app config."}), 500
    try:
        if not os.path.exists(config_file_path):
            return (
                jsonify({"error": f"Configuration file not found: {config_file_path}"}),
                404,
            )
        with open(config_file_path, "r") as f:
            config_data = yaml.safe_load(f)
        return jsonify({"config": config_data}), 200
    except Exception as e:
        return jsonify({"error": f"Error reading configuration: {str(e)}"}), 500


@app.route("/config", methods=["PUT"])
def update_config():
    config_file_path = app.config.get("FENETRE_CONFIG_FILE")
    if not config_file_path:
        return jsonify({"error": "FENETRE_CONFIG_FILE not set in app config."}), 500
    try:
        if not request.is_json:
            return jsonify({"error": "Request body must be JSON."}), 415

        new_config_json = request.get_json()
        if not new_config_json:
            return jsonify({"error": "Request body is empty or not valid JSON."}), 400

        # If the whole config is nested under a "config" key, extract it.
        if "config" in new_config_json and len(new_config_json.keys()) == 1:
            new_config_json = new_config_json["config"]

        if not isinstance(new_config_json, dict):
            return (
                jsonify(
                    {"error": "Root element of the configuration must be a dictionary."}
                ),
                400,
            )

        # Convert JSON to YAML
        try:
            new_config_yaml = yaml.dump(
                new_config_json, sort_keys=False, default_flow_style=False, indent=2
            )
        except yaml.YAMLError as e:
            return jsonify({"error": f"Error converting JSON to YAML: {str(e)}"}), 500

        with open(config_file_path, "w") as f:
            f.write(new_config_yaml)

        return (
            jsonify(
                {
                    "message": "Configuration updated successfully (saved as YAML). Reload is required to apply changes."
                }
            ),
            200,
        )
    except BadRequest:
        return (
            jsonify({"error": "Invalid JSON format in request body or empty body."}),
            400,
        )
    except Exception as e:
        print(f"Unexpected error in update_config: {e}")
        return jsonify({"error": f"Error processing configuration: {str(e)}"}), 500


# --- UI Serving Routes ---


@app.route("/")
def serve_ui_page():
    return send_from_directory("static/admin", "index.html")


@app.route("/api/sync_ui", methods=["POST"])
def sync_ui():
    config_file_path = app.config.get("FENETRE_CONFIG_FILE")
    if not config_file_path:
        return jsonify({"error": "FENETRE_CONFIG_FILE not set in app config."}), 500
    try:
        with open(config_file_path, "r") as f:
            config = yaml.safe_load(f)
        work_dir = config.get("global", {}).get("work_dir")
        if not work_dir:
            return jsonify({"error": "work_dir not set in global config."}), 500

        copy_public_html_files(work_dir, config.get("global", {}))
        return jsonify({"message": "UI files synchronized successfully."}), 200
    except Exception as e:
        return jsonify({"error": f"Error synchronizing UI files: {str(e)}"}), 500


# --- API Endpoints for Visual Config Tool ---


@app.route("/api/camera/<string:camera_name>/capture_for_ui", methods=["POST"])
def capture_for_ui(camera_name):
    config_file_path = app.config.get("FENETRE_CONFIG_FILE")
    if not config_file_path:
        return jsonify({"error": "FENETRE_CONFIG_FILE not set in app config."}), 500

    try:
        with open(config_file_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        return (
            jsonify({"error": f"Configuration file {config_file_path} not found."}),
            500,
        )
    except yaml.YAMLError:
        return (
            jsonify({"error": f"Error parsing configuration file {config_file_path}."}),
            500,
        )

    if "cameras" not in config or camera_name not in config["cameras"]:
        return (
            jsonify({"error": f"Camera '{camera_name}' not found in configuration."}),
            404,
        )

    camera_config = config["cameras"][camera_name]
    url = camera_config.get("url")
    gopro_ip = camera_config.get("gopro_ip")

    if not url and not gopro_ip:
        # For now, only support URL and GoPro cameras for this feature.
        return (
            jsonify(
                {
                    "error": f"Camera '{camera_name}' does not have a URL or gopro_ip configured. Only URL/GoPro cameras are supported for UI capture."
                }
            ),
            400,
        )

    try:
        if url:
            # Replicate parts of fenetre.py's get_pic_from_url logic
            global_config = config.get("global", {})
            ua = global_config.get("user_agent", "Fenetre Config UI/1.0")
            headers = {"Accept": "image/*,*"}
            if ua:
                requests_version = requests.__version__
                headers = {"User-Agent": f"{ua} v{requests_version}"}

            timeout = camera_config.get("timeout_s", 20)

            r = requests.get(url, timeout=timeout, headers=headers, stream=True)
            r.raise_for_status()

            # Determine content type
            content_type = r.headers.get("content-type", "application/octet-stream")
            if not content_type.startswith("image/"):
                # Try to infer from URL if content-type is generic
                if ".jpg" in url.lower() or ".jpeg" in url.lower():
                    content_type = "image/jpeg"
                elif ".png" in url.lower():
                    content_type = "image/png"

            img_bytes = BytesIO(r.content)
            img_bytes.seek(0)

            return send_file(img_bytes, mimetype=content_type)

        elif gopro_ip:
            gopro = GoPro(
                ip_address=gopro_ip, gopro_model=camera_config.get("gopro_model", "open_gopro")
            )
            # This is a simplified capture, assuming the GoPro is ready.
            # The main app's GoProUtilityThread handles state management (presets, etc.)
            # which we don't replicate here for a simple capture.
            jpeg_bytes = gopro.capture_photo()
            if not jpeg_bytes:
                return (
                    jsonify(
                        {
                            "error": "Failed to capture photo from GoPro. It might be busy or off."
                        }
                    ),
                    500,
                )

            img_bytes = BytesIO(jpeg_bytes)
            img_bytes.seek(0)
            return send_file(img_bytes, mimetype="image/jpeg")

    except requests.exceptions.RequestException as e:
        return (
            jsonify(
                {
                    "error": f"Error fetching image for camera '{camera_name}' from {url}: {str(e)}"
                }
            ),
            500,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "error": f"Unexpected error capturing image for '{camera_name}': {str(e)}"
                }
            ),
            500,
        )


@app.route("/api/camera/preview_crop", methods=["POST"])
def preview_crop():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided in the request."}), 400

    crop_data_str = request.form.get("crop_data")
    if not crop_data_str:
        return jsonify({"error": "No crop_data provided in the request form."}), 400

    try:
        crop_data = json.loads(crop_data_str)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON in crop_data."}), 400

    x = crop_data.get("x")
    y = crop_data.get("y")
    width = crop_data.get("width")
    height = crop_data.get("height")

    if None in [x, y, width, height]:
        return (
            jsonify(
                {"error": "Missing one or more crop coordinates (x, y, width, height)."}
            ),
            400,
        )

    try:
        x, y, width, height = int(x), int(y), int(width), int(height)
    except ValueError:
        return jsonify({"error": "Crop coordinates must be integers."}), 400

    if width <= 0 or height <= 0:
        return jsonify({"error": "Crop width and height must be positive."}), 400

    file = request.files["image"]

    try:
        img = Image.open(file.stream)
        img = ImageOps.exif_transpose(img)

        # Crop box is (left, upper, right, lower)
        crop_box = (x, y, x + width, y + height)

        # Ensure crop box is within image bounds
        img_width, img_height = img.size
        actual_crop_box = (
            max(0, crop_box[0]),
            max(0, crop_box[1]),
            min(img_width, crop_box[2]),
            min(img_height, crop_box[3]),
        )

        if (
            actual_crop_box[0] >= actual_crop_box[2]
            or actual_crop_box[1] >= actual_crop_box[3]
        ):
            return (
                jsonify(
                    {
                        "error": "Crop area is outside image bounds or has zero/negative dimensions after clamping."
                    }
                ),
                400,
            )

        cropped_img = img.crop(actual_crop_box)

        img_io = BytesIO()
        # Determine format; default to JPEG if not obvious, or preserve original if possible
        img_format = img.format if img.format else "JPEG"
        if img_format.upper() == "JPG":
            img_format = "JPEG"  # Common alias

        cropped_img.save(img_io, format=img_format)
        img_io.seek(0)

        mimetype = f"image/{img_format.lower()}"
        if img_format == "JPEG" and not mimetype.endswith("jpeg"):
            mimetype = "image/jpeg"

        return send_file(img_io, mimetype=mimetype)

    except FileNotFoundError:
        return jsonify({"error": "Image file somehow not found after upload."}), 500
    except IOError:
        return (
            jsonify(
                {
                    "error": "Cannot process image file. It might be corrupted or not a supported format."
                }
            ),
            400,
        )
    except Exception as e:
        print(f"Error in preview_crop: {e}")
        return jsonify({"error": f"Error during image processing: {str(e)}"}), 500


@app.route("/config/reload", methods=["POST"])
def reload_config():
    """
    Signals the main fenetre.py process to reload its configuration.
    """
    fenetre_pid_file_path = app.config.get("FENETRE_PID_FILE_PATH")
    if not fenetre_pid_file_path:
        return jsonify({"error": "FENETRE_PID_FILE_PATH not set in app config."}), 500

    try:
        if os.path.exists(fenetre_pid_file_path):
            with open(fenetre_pid_file_path, "r") as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid = int(pid_str)
                    # Send SIGHUP to the process to trigger a configuration reload.
                    os.kill(pid, signal.SIGHUP)
                    return (
                        jsonify({"message": f"Reload signal sent to process {pid}."}),
                        200,
                    )
                else:
                    return jsonify({"error": "PID file is empty."}), 500
        else:
            return (
                jsonify(
                    {
                        "error": f"PID file not found: {fenetre_pid_file_path}. Cannot signal reload."
                    }
                ),
                404,
            )

    except FileNotFoundError:
        return (
            jsonify(
                {
                    "error": f"PID file not found: {fenetre_pid_file_path}. Cannot signal reload."
                }
            ),
            404,
        )
    except ProcessLookupError:
        return (
            jsonify(
                {
                    "error": f"Process with PID read from {fenetre_pid_file_path} not found. It might have exited."
                }
            ),
            500,
        )
    except ValueError:
        return jsonify({"error": f"Invalid PID found in {fenetre_pid_file_path}."}), 500
    except Exception as e:
        return jsonify({"error": f"Error signaling reload: {str(e)}"}), 500


# The run_server() function and if __name__ == '__main__': block are removed.
# fenetre.py will now manage the lifecycle of this Flask app.
