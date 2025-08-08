#!/usr/bin/env python3
import http.server
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import sys
from collections import deque
from datetime import datetime, timedelta
from functools import partial
from io import BytesIO
from threading import Thread
from typing import Callable, Dict, List, Optional, Tuple

import mozjpeg_lossless_optimization
import numpy as np
import pytz
import requests
from absl import app, flags, logging
from astral import LocationInfo
from astral.sun import sun
from PIL import Image
from skimage.metrics import structural_similarity
from waitress import serve as waitress_serve

from fenetre.admin_server import (
    metric_camera_directory_size_bytes,
    metric_capture_failures_total,
    metric_last_successful_picture_timestamp,
    metric_pictures_taken_total,
    metric_processing_time_seconds,
    metric_sleep_time_seconds,
    metric_timelapses_created_total,
    metric_work_directory_size_bytes,
)
from fenetre.archive import archive_daydir, list_unarchived_dirs, scan_and_publish_metrics
from fenetre.config import config_load
from fenetre.daylight import run_end_of_day
from fenetre.gopro_utility import GoProUtilityThread, format_gopro_sd_card
from fenetre.platform_utils import is_raspberry_pi, rotate_log_file
from fenetre.postprocess import gather_metrics, postprocess
from fenetre.timelapse import create_timelapse
from fenetre.ui_utils import copy_public_html_files

# Define flags at module level
flags.DEFINE_string("config", "config.yaml", "path to YAML config file")

FLAGS = flags.FLAGS


DEFAULT_SKY_AREA = "100,0,400,50"
FENETRE_PID_FILE = os.environ.get("FENETRE_PID_FILE", "fenetre.pid")

# Global dictionary to keep track of active camera threads and related utility threads
active_camera_threads = {}
http_server_thread_global = None
http_server_instance = None
admin_server_thread_global = None
admin_server_instance_global = None
exit_event = threading.Event()
timelapse_queue_file = None
timelapse_queue_lock = threading.Lock()


def interruptible_sleep(duration: float, event: threading.Event, check_interval: float = 1.0):
    """Sleeps for a given duration, but checks an event periodically."""
    if duration <= 0:
        return

    end_time = time.time() + duration
    while time.time() < end_time:
        if event.is_set():
            break

        remaining_time = end_time - time.time()
        sleep_duration = min(check_interval, remaining_time)

        if sleep_duration > 0:
            time.sleep(sleep_duration)


def log_camera_error(camera_name: str, error_message: str, global_config: Dict):
    """Logs an error message to a camera-specific log file."""
    log_dir = global_config.get("log_dir")
    if not log_dir:
        return

    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"{camera_name}.log")
    rotate_log_file(log_file_path)
    with open(log_file_path, "a") as f:
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"ERROR: {error_message}\n")
        f.write("-" * 20 + "\n")


def get_pic_from_url(url: str, timeout: int, ua: str = "", camera_name: str = "", camera_config: Dict = None, global_config: Dict = None) -> Image.Image:

    if camera_config is None:
        camera_config = {}
    if global_config is None:
        global_config = {}

    request_url = url
    if camera_config.get("cache_bust", False):
        timestamp = int(time.time())
        if "?" in request_url:
            request_url = f"{request_url}&_={timestamp}"
        else:
            request_url = f"{request_url}?_={timestamp}"

    headers = {"Accept": "image/*,*"}
    if ua:
        requests_version = requests.__version__
        headers = {"User-Agent": f"{ua} v{requests_version}"}
    r = requests.get(request_url, timeout=timeout, headers=headers)

    log_message = (f"URL fetch for {url}:"
                   f"\n\tRequest URL: {r.request.url}"
                   f"\n\tRequest Headers: {r.request.headers}"
                   f"\n\tResponse Status: {r.status_code}"
                   f"\n\tResponse Headers: {r.headers}")

    logging.debug(log_message)

    log_dir = global_config.get("log_dir")
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file_name = f"{camera_name}.log" if camera_name else "url_requests.log"
        log_file_path = os.path.join(log_dir, log_file_name)
        rotate_log_file(log_file_path)
        with open(log_file_path, "a") as f:
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(log_message + "\n")
            f.write("-" * 20 + "\n")

    if r.status_code != 200:
        raise RuntimeError(
            f"HTTP Request Failed!\n"
            f"URL: {request_url}\n"
            f"Status Code: {r.status_code}\n"
            f"Request Headers: {r.request.headers}\n"
            f"Response Headers: {r.headers}\n"
            f"Response Content (first 500 bytes): {r.content[:500]}"
        )

    return Image.open(BytesIO(r.content))


def get_pic_dir_and_filename(camera_name: str) -> Tuple[str, str]:
    tz = pytz.timezone(global_config["timezone"])
    dt = datetime.now(tz)
    return (
        os.path.join(global_config["pic_dir"], camera_name, dt.strftime("%Y-%m-%d")),
        dt.strftime("%Y-%m-%dT%H-%M-%S%Z.jpg"),
    )


def write_pic_to_disk(
    pic: Image.Image, pic_path: str, optimize: bool = False, exif_data: bytes = b""
):
    os.makedirs(os.path.dirname(pic_path), exist_ok=True)
    os.chmod(os.path.dirname(pic_path), 33277)  # rwxrwxr-x
    if logging.level_debug():
        logging.debug(f"Saving picture {pic_path}")
    if optimize is True:
        jpeg_io = BytesIO()
        pic.convert("RGB").save(jpeg_io, format="JPEG", quality=90, exif=exif_data)
        jpeg_io.seek(0)
        jpeg_bytes = jpeg_io.read()
        optimized_jpeg_bytes = mozjpeg_lossless_optimization.optimize(jpeg_bytes)
        with open(pic_path, "wb") as output_file:
            output_file.write(optimized_jpeg_bytes)
    else:
        pic.save(pic_path, exif=exif_data)


def update_latest_link(pic_path: str):
    cam_dir = os.path.join(os.path.dirname(pic_path), os.pardir)
    tmp_link = os.path.join(cam_dir, "new.jpg")
    latest_link = os.path.join(cam_dir, "latest.jpg")
    relative_path = os.path.relpath(pic_path, cam_dir)
    os.symlink(relative_path, tmp_link)
    os.rename(tmp_link, latest_link)


def get_pic_from_local_command(
    cmd: str, timeout_s: int, camera_name: str, camera_config: Dict
) -> Image.Image:
    log_dir = global_config.get("log_dir")
    if log_dir:
        log_file_path = os.path.join(
            log_dir,
            f"{camera_name}.log",
        )
        rotate_log_file(log_file_path)
        with open(log_file_path, "a") as log_file:
            s = subprocess.run(
                cmd.split(" "),
                stdout=subprocess.PIPE,
                stderr=log_file,
                timeout=timeout_s,
            )
    else:
        s = subprocess.run(
            cmd.split(" "), stdout=subprocess.PIPE, stderr=None, timeout=timeout_s
        )
    return Image.open(BytesIO(s.stdout))


def get_pic_from_picamera2(camera_config: Dict) -> Image.Image:
    """Captures a picture from a Raspberry Pi camera using the picamera2 library."""
    from libcamera import controls
    from picamera2 import Picamera2

    picam2 = Picamera2()

    config = picam2.create_still_configuration()

    # Apply tuning file if specified
    if camera_config.get("tuning_file"):
        tuning = Picamera2.load_tuning_file(camera_config["tuning_file"])
        picam2.configure(config, tuning=tuning)
    else:
        picam2.configure(config)

    # Set controls
    if camera_config.get("exposure_time"):
        picam2.set_controls({"ExposureTime": camera_config["exposure_time"]})
    if camera_config.get("analogue_gain"):
        picam2.set_controls({"AnalogueGain": camera_config["analogue_gain"]})
    if camera_config.get("denoise_mode"):
        picam2.set_controls(
            {"NoiseReductionMode": controls.draft.NoiseReductionModeEnum.HighQuality}
        )

    picam2.start()
    time.sleep(1)

    # Capture to a memory buffer
    buffer = picam2.capture_file("-")
    picam2.stop()

    return Image.open(BytesIO(buffer))


def is_sunrise_or_sunset(camera_config: Dict, global_config: Dict) -> bool:
    """
    Determines if the current time is within the sunrise or sunset window for a given camera.
    """
    if not camera_config.get("sunrise_sunset", {}).get("enabled", False):
        return False

    latitude = camera_config.get("latitude")
    longitude = camera_config.get("longitude")
    if latitude is None or longitude is None:
        return False

    try:
        tz = pytz.timezone(global_config["timezone"])
        now = datetime.now(tz)
        location = LocationInfo(latitude=latitude, longitude=longitude)
        s = sun(location.observer, date=now.date(), tzinfo=location.timezone)

        sunrise_start = s["sunrise"] - timedelta(minutes=30)
        sunrise_end = s["sunrise"] + timedelta(minutes=30)
        sunset_start = s["sunset"] - timedelta(minutes=30)
        sunset_end = s["sunset"] + timedelta(minutes=30)

        return (sunrise_start <= now <= sunrise_end) or (
            sunset_start <= now <= sunset_end
        )

    except Exception as e:
        logging.error(f"Error calculating sunrise/sunset: {e}")
        return False


def snap(camera_name, camera_config: Dict):
    url = camera_config.get("url")
    timeout = camera_config.get("timeout_s", 60)
    local_command = camera_config.get("local_command")
    gopro_ip = camera_config.get("gopro_ip")

    def capture() -> Image.Image:
        logging.info(f"{camera_name}: Fetching new picture.")
        if url is not None:
            ua = global_config.get("user_agent", "")
            return get_pic_from_url(url, timeout, ua, camera_name, camera_config, global_config)
        if local_command is not None:
            return get_pic_from_local_command(
                local_command, timeout, camera_name, camera_config
            )
        if gopro_ip is not None:
            gopro_instance = active_camera_threads.get(camera_name, {}).get(
                "gopro_instance"
            )
            if not gopro_instance:
                raise RuntimeError(f"GoPro instance not found for camera {camera_name}")
            jpeg_bytes = gopro_instance.capture_photo()
            try:
                # new_pic is only used to check if the image is valid
                Image.open(BytesIO(jpeg_bytes))
            except Image.UnidentifiedImageError:
                logging.error(
                    f"Failed to open image from GoPro: {gopro_ip}. Resetting gopro"
                )
                format_gopro_sd_card(gopro_ip)
                raise
            return Image.open(BytesIO(jpeg_bytes))
        if camera_config.get("capture_method") == "picamera2":
            return get_pic_from_picamera2(camera_config)
        return None

    # Initialization before the main loop
    previous_pic_dir, previous_pic_filename = get_pic_dir_and_filename(camera_name)
    previous_pic_fullpath = os.path.join(previous_pic_dir, previous_pic_filename)
    try:
        previous_pic = capture()
    except Exception as e:
        error_msg = f"Failed to capture initial image for {camera_name}: {e}"
        logging.error(error_msg, exc_info=True)
        log_camera_error(camera_name, error_msg, global_config)
        raise
    previous_exif = previous_pic.info.get("exif") or b""
    if len(camera_config.get("postprocessing", [])) > 0:
        previous_pic, previous_exif = postprocess(
            previous_pic, camera_config.get("postprocessing", [])
        )
    fixed_snap_interval = camera_config.get("snap_interval_s", None)
    if camera_name not in sleep_intervals:
        sleep_intervals[camera_name] = (
            float(fixed_snap_interval)
            if isinstance(fixed_snap_interval, (int, float))
            else 60.0
        )

    # Capture loop
    while not exit_event.is_set():
        # Immediately save the previous pic to disk.
        write_pic_to_disk(
            previous_pic,
            previous_pic_fullpath,
            camera_config.get("mozjpeg_optimize", False),
            previous_exif,
        )
        if camera_config.get("gather_metrics", True):
            try:
                gather_metrics(previous_pic_fullpath, camera_name)
            except Exception as e:
                logging.error(
                    f"Error gathering metrics for {previous_pic_fullpath}: {e}"
                )
        metric_pictures_taken_total.labels(camera_name=camera_name).inc()
        metric_last_successful_picture_timestamp.labels(
            camera_name=camera_name
        ).set_to_current_time()
        update_latest_link(previous_pic_fullpath)
        metadata = {
            "last_picture_url": os.path.relpath(
                previous_pic_fullpath,
                os.path.join(previous_pic_fullpath, os.path.pardir, os.path.pardir),
            ),
        }
        metadata_path = os.path.join(previous_pic_dir, os.path.pardir, "metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=4)
            logging.debug(f"{camera_name}: Updated metadata file {metadata_path}")

        if exit_event.is_set():
            logging.info(f"{camera_name}: Exiting snap loop.")
            return

        current_sleep_interval = sleep_intervals[camera_name]
        if is_sunrise_or_sunset(camera_config, global_config):
            current_sleep_interval = global_config.get("sunrise_sunset_interval_s", 10)
            logging.info(
                f"{camera_name}: Sunrise/sunset detected, using fast interval: {current_sleep_interval}s"
            )

        metric_sleep_time_seconds.labels(camera_name=camera_name).set(
            current_sleep_interval
        )
        logging.info(f"{camera_name}: Sleeping {current_sleep_interval}s")
        interruptible_sleep(current_sleep_interval, exit_event)

        start_time = time.time()
        new_pic_dir, new_pic_filename = get_pic_dir_and_filename(camera_name)
        new_pic_fullpath = os.path.join(new_pic_dir, new_pic_filename)

        if not previous_pic_dir == new_pic_dir:
            # This is a new day. We can now process the previous day.
            daylight_q.append(
                (
                    camera_name,
                    previous_pic_dir,
                    camera_config.get("sky_area", DEFAULT_SKY_AREA),
                )
            )

        try:
            new_pic = capture()
        except Exception as e:
            error_msg = f"Could not fetch picture for {camera_name}: {e}"
            logging.warning(error_msg)
            log_camera_error(camera_name, error_msg, global_config)
            metric_capture_failures_total.labels(camera_name=camera_name).inc()
            raise
        new_exif = new_pic.info.get("exif") or b""
        if new_pic is None:
            logging.warning(f"{camera_name}: Could not fetch picture.")
            raise ValueError
        if len(camera_config.get("postprocessing", [])) > 0:
            new_pic, new_exif = postprocess(
                new_pic, camera_config.get("postprocessing", [])
            )
        if fixed_snap_interval is None:
            ssim = get_ssim_for_area(
                previous_pic, new_pic, camera_config.get("ssim_area", None)
            )
            ssim_setpoint = camera_config.get("ssim_setpoint", 0.85)
            if ssim < ssim_setpoint:
                sleep_intervals[camera_name] = sleep_intervals[camera_name] * 0.9
            else:
                sleep_intervals[camera_name] += 0.5
            if logging.level_debug():
                logging.debug(
                    f"{camera_name}: ssim {ssim}, setpoint: {ssim_setpoint}, new sleep interval: {sleep_intervals[camera_name]}s"
                )

        end_time = time.time()
        metric_processing_time_seconds.labels(camera_name=camera_name).set(
            end_time - start_time
        )
        previous_pic = new_pic
        previous_exif = new_exif
        previous_pic_dir = new_pic_dir
        previous_pic_fullpath = new_pic_fullpath


def get_ssim_for_area(
    image1: Image.Image, image2: Image.Image, area: Optional[str]
) -> float:
    if image1.size != image2.size:
        logging.error(
            f"Images {image1.size} and {image2.size} are not the same size, cannot compare SSIM."
        )
        return 1.0

    target_image1 = image1
    target_image2 = image2

    # Compute SSIM on the full image.
    if area:
        # Prevents the linter from complaining about the type of crop_points.
        crop_points_list = [float(i) for i in area.split(",")]
        crop_points = (
            crop_points_list[0],
            crop_points_list[1],
            crop_points_list[2],
            crop_points_list[3],
        )
        logging.debug(f"{crop_points}")
        target_image1 = image1.resize((50, 50), box=crop_points)
        target_image2 = image2.resize((50, 50), box=crop_points)

    image1_np = np.array(target_image1.convert("L"))
    image2_np = np.array(target_image2.convert("L"))

    return structural_similarity(image1_np, image2_np, data_range=255)


def server_run():
    server_class = http.server.ThreadingHTTPServer
    handler_class = partial(
        http.server.SimpleHTTPRequestHandler, directory=global_config["work_dir"]
    )

    listen_str = server_config.get("listen", "0.0.0.0:8888")
    try:
        host, port_str = listen_str.split(":")
        port = int(port_str)
        server_address = (host, port)
    except ValueError:
        logging.error(f"Invalid listen address format in http_server config: '{listen_str}'. It should be 'host:port'. Defaulting to 0.0.0.0:8888.")
        server_address = ("0.0.0.0", 8888)

    logging.info(f"Starting HTTP Server on {server_address}")
    httpd = server_class(server_address, handler_class)
    global http_server_instance
    http_server_instance = httpd
    logging.info(f"HTTP server instance {http_server_instance} started.")
    try:
        httpd.serve_forever()
    except Exception as e:
        if not exit_event.is_set():
            logging.error(f"HTTP server crashed: {e}", exc_info=True)
    finally:
        logging.info(f"HTTP server {server_address} stopped.")


def stop_http_server():
    global http_server_instance, http_server_thread_global
    if http_server_instance:
        logging.info("Attempting to shut down HTTP server...")
        http_server_instance.shutdown()
        http_server_instance.server_close()
        http_server_instance = None
        logging.info("HTTP server shut down.")
    if http_server_thread_global and http_server_thread_global.is_alive():
        logging.info("Waiting for HTTP server thread to join...")
        http_server_thread_global.join(timeout=5)
        if http_server_thread_global.is_alive():
            logging.warning("HTTP server thread did not join in time.")
        else:
            logging.info("HTTP server thread joined.")
    http_server_thread_global = None


# --- Config Server Management ---
def run_admin_server_func(
    listeners: str, flask_app, fenetre_config_file: str, fenetre_pid_file: str
):
    """Runs the Flask admin server."""
    flask_app.config["FENETRE_CONFIG_FILE"] = fenetre_config_file
    flask_app.config["FENETRE_PID_FILE_PATH"] = fenetre_pid_file
    flask_app.config["EXIT_EVENT"] = exit_event

    global admin_server_instance_global
    try:
        logging.info(f"Starting admin server on {listeners}")
        waitress_serve(flask_app, listen=listeners, threads=4, _quiet=False)
    except SystemExit:
        logging.info("admin server shutting down (SystemExit caught).")
    except Exception as e:
        if not exit_event.is_set():
            logging.error(f"admin server crashed: {e}", exc_info=True)
    finally:
        logging.info(f"admin server stopped.")
        admin_server_instance_global = None


def stop_admin_server():
    global admin_server_thread_global, admin_server_instance_global
    logging.info("Attempting to shut down Config Server...")

    # Signaling shutdown to a blocking WSGI server in a thread is complex.
    # If waitress or werkzeug were run with a programmatic server object, we could call .shutdown() or similar.
    # Since we call serve() or run_simple() which block, we rely on exit_event and thread joining.
    # The most reliable way is if the server itself checks exit_event or has a shutdown endpoint.
    # For now, we set exit_event, which should be checked by Flask routes if they are long-running (not typical).
    # The server thread itself, if daemon, will be killed on app exit.
    # For SIGHUP reloads where we want to stop/start it, joining the thread is key.
    # If the server doesn't exit cleanly from exit_event, the join might hang or timeout.

    # Flask's development server (werkzeug.serving.run_simple) can be stopped by sending a SIGINT to the process,
    # or by making a request to a special /shutdown route (if implemented).
    # Waitress might need a similar mechanism or a more direct control.
    # For now, the primary mechanism is exit_event and thread join.
    # If admin_server_instance_global held a server object with a shutdown method, we'd call it here.
    # Since it doesn't (waitress_serve and werkzeug_run_simple are blocking calls),
    # we rely on the thread terminating when exit_event is set (if the server respects it) or during join.

    if admin_server_thread_global and admin_server_thread_global.is_alive():
        logging.info("Config server thread is alive. Waiting for it to join...")
        # exit_event is already set by the main shutdown_application or handle_sighup logic if it's a full stop.
        # If this is a specific stop for the config server (e.g. disabled in config), ensure exit_event is relevant.
        # For simplicity, assume global exit_event is the main control.
        admin_server_thread_global.join(timeout=10)  # Wait for thread to finish
        if admin_server_thread_global.is_alive():
            logging.warning(
                "Config server thread did not join in time. It might not support graceful shutdown perfectly."
            )
        else:
            logging.info("Config server thread joined.")
    else:
        logging.info("Config server thread already stopped or not started.")

    admin_server_thread_global = None
    admin_server_instance_global = None  # Ensure cleaned up


def create_and_start_and_watch_thread(
    f: Callable,
    name: str,
    arguments: List[str] = [],
    exp_backoff_limit: int = 0,
    camera_name_for_management: Optional[str] = None,
) -> None:
    failure_count = 0
    last_failure = datetime.now()
    # sleep_intervals is now managed globally by the reload logic if needed for specific cameras
    # global sleep_intervals
    # sleep_intervals = {} # This was problematic as it reset sleep_intervals on thread restart.
    # It should be initialized once globally or per camera by the main logic.

    thread_instance = None  # Keep a reference to the running thread

    while not exit_event.is_set():
        # Check if this thread (for a specific camera) should still be running
        if (
            camera_name_for_management
            and camera_name_for_management not in cameras_config
        ):
            logging.info(
                f"Camera {camera_name_for_management} removed from config. Watchdog {name} stopping."
            )
            if thread_instance and thread_instance.is_alive():
                # The 'snap' function needs to respect exit_event to terminate gracefully.
                # Forcing a stop is harder; relying on exit_event being set for the thread.
                logging.info(
                    f"Thread {name} for {camera_name_for_management} should stop due to config removal."
                )
            return  # Exit the watchdog loop for this camera

        if not thread_instance or not thread_instance.is_alive():
            # Prune old thread reference from active_camera_threads if it matches this watchdog's managed camera
            if (
                camera_name_for_management
                and active_camera_threads.get(camera_name_for_management, {}).get(
                    "watchdog_thread"
                )
                == thread_instance
            ):
                # This ensures we don't clear another thread's reference if names collide or structure changes
                pass  # The new thread will be added below

            thread_instance = Thread(target=f, daemon=False, name=name, args=arguments)

            # Store the new thread instance for management if it's a camera thread
            if camera_name_for_management:
                if camera_name_for_management not in active_camera_threads:
                    active_camera_threads[camera_name_for_management] = {}
                active_camera_threads[camera_name_for_management][
                    "watchdog_thread"
                ] = thread_instance
                # Also ensure sleep_intervals is initialized for this camera if not already
                if camera_name_for_management not in sleep_intervals:
                    cam_conf = cameras_config.get(camera_name_for_management, {})
                    fixed_snap_interval = cam_conf.get("snap_interval_s", None)
                    sleep_intervals[camera_name_for_management] = (
                        float(fixed_snap_interval)
                        if isinstance(fixed_snap_interval, (int, float))
                        else 60.0
                    )

            exp_backoff_delay = min(exp_backoff_limit, 2**failure_count)
            if datetime.now() - last_failure > timedelta(
                seconds=90
            ):  # Corrected timedelta
                failure_count = 0

            if failure_count > 0:  # Only log and sleep if it's a restart
                logging.info(
                    f"Thread {name} (re)start attempt {failure_count}. Delaying {exp_backoff_delay}s."
                )
                if camera_name_for_management:
                    metric_capture_failures_total.labels(
                        camera_name=camera_name_for_management
                    ).inc()
                interruptible_sleep(exp_backoff_delay, exit_event)

            failure_count += 1
            last_failure = datetime.now()
            try:
                thread_instance.start()
                logging.info(f"Thread {name} started.")
            except Exception as e:
                logging.error(f"Failed to start thread {name}: {e}", exc_info=True)
                thread_instance = None  # Ensure we try to restart it

        interruptible_sleep(5, exit_event)  # Check every 5 seconds


def update_cameras_metadata(cameras_configs: Dict, work_dir: str):
    """cameras.json is a public file describing info about the cameras used to power the map view.
    We add to this file, never delete, but we do update the cameras if their info (i.e. coordinates) changed.
    """

    updated_cameras_metadata = {"cameras": [], "global": {}}
    json_filepath = os.path.join(work_dir, "cameras.json")

    if os.path.exists(json_filepath):
        try:
            with open(json_filepath, "r") as json_file:
                cameras_public_metadata = json.load(json_file)

            # Handle both old (list) and new (dict) formats
            if isinstance(cameras_public_metadata, list):
                logging.warning(
                    f"Old format detected for {json_filepath}. It will be updated to the new format."
                )
                old_camera_list = cameras_public_metadata
            elif isinstance(cameras_public_metadata, dict):
                old_camera_list = cameras_public_metadata.get("cameras", [])
            else:
                logging.warning(
                    f"Unrecognized format for {json_filepath}. It will be overwritten."
                )
                old_camera_list = []

            for camera_metadata in old_camera_list:
                if camera_metadata.get("title") not in cameras_config:
                    logging.warning(
                        f"Camera {camera_metadata.get('title')} is not configured anymore. "
                        f"Delete it from {json_filepath} manually if you want to."
                    )
                    updated_cameras_metadata["cameras"].append(camera_metadata)

        except (json.JSONDecodeError, TypeError) as e:
            logging.warning(
                f"Could not parse {json_filepath} or it has an invalid format. It will be overwritten. Error: {e}"
            )

    for cam in cameras_config:
        metadata = {}
        metadata["title"] = cam
        metadata["url"] = f"map.html?camera={cam}"
        metadata["fullscreen_url"] = f"fullscreen.html?camera={cam}"
        metadata["livefeed_url"] = cameras_config[cam].get("url") or cameras_config[
            cam
        ].get("local_command")
        metadata["description"] = cameras_config[cam].get("description", "")
        metadata["snap_interval_s"] = (
            cameras_config[cam].get("snap_interval_s") or "dynamic"
        )
        metadata["dynamic_metadata"] = os.path.join("photos", cam, "metadata.json")
        metadata["image"] = os.path.join("photos", cam, "latest.jpg")
        metadata["lat"] = cameras_config[cam].get("lat")
        metadata["lon"] = cameras_config[cam].get("lon")
        updated_cameras_metadata["cameras"].append(metadata)

    updated_cameras_metadata["global"] = {
        "timelapse_file_extension": timelapse_config.get("file_extension", "webm"),
        "frequent_timelapse_file_extension": timelapse_config.get("frequent_timelapse", {}).get("file_extension", "mp4")
    }

    with open(json_filepath, "w") as json_file:
        json.dump(updated_cameras_metadata, json_file, indent=4)


def main(argv):
    del argv  # Unused.

    # Write PID to file
    try:
        with open(FENETRE_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
        logging.info(f"PID {os.getpid()} written to {FENETRE_PID_FILE}")
    except IOError as e:
        logging.error(f"Failed to write PID file: {e}", exc_info=True)
        # Depending on strictness, might exit or just warn
        # For now, warn and continue. Reload via PID signal won't work.

    global exit_event
    exit_event = threading.Event()

    # Setup signal handling for SIGHUP for config reload and SIGINT/SIGTERM for graceful exit
    signal.signal(signal.SIGHUP, handle_sighup)
    signal.signal(signal.SIGINT, signal_handler_exit)  # Graceful exit on Ctrl+C
#    signal.signal(
#        signal.SIGTERM, signal_handler_exit
#    )  # Graceful exit on kill/systemd stop

    # Initialize global sleep_intervals (important for camera threads)
    global sleep_intervals
    sleep_intervals = {}

    load_and_apply_configuration(initial_load=True)  # Uses FLAGS.config by default

    global timelapse_queue_file
    timelapse_queue_file = os.path.join(
        global_config.get("work_dir"), "timelapse_queue.txt"
    )
    if not os.path.exists(timelapse_queue_file):
        open(timelapse_queue_file, "a").close()  # Create the file if it does not exist

    # These queues are global and should persist across reloads if fenetre.py itself isn't restarted.
    # If reload implies restarting these loops, then re-initialization might be needed in reload_configuration_logic
    global daylight_q, archive_q, frequent_timelapse_q
    daylight_q = deque()
    archive_q = deque()
    frequent_timelapse_q = deque()

    # Timelapse and Daylight threads are started here.
    # Consider if they need to be managed (restarted) on config changes.
    # For now, they use global_config, which gets updated.
    # If their core behavior (e.g., ffmpeg_options) changes, a restart might be cleaner.
    # However, these are long-running loops processing queues; restarting them might be disruptive.
    # Let's assume for now that updating global_config is sufficient for them.
    global timelapse_thread_global, daylight_thread_global, archive_thread_global, frequent_timelapse_loop_thread_global
    frequent_timelapse_loop_thread_global = Thread(
        target=frequent_timelapse_loop, daemon=True, name="frequent_timelapse_loop"
    )
    frequent_timelapse_loop_thread_global.start()
    logging.info(f"Starting thread {frequent_timelapse_loop_thread_global.name}")

    timelapse_thread_global = Thread(
        target=timelapse_loop, daemon=True, name="timelapse_loop"
    )
    timelapse_thread_global.start()
    logging.info(f"Starting thread {timelapse_thread_global.name}")

    daylight_thread_global = Thread(
        target=daylight_loop, daemon=True, name="daylight_loop"
    )
    daylight_thread_global.start()
    logging.info(f"Starting thread {daylight_thread_global.name}")

    archive_thread_global = Thread(
        target=archive_loop, daemon=True, name="archive_loop"
    )
    archive_thread_global.start()
    logging.info(f"Starting thread {archive_thread_global.name}")

    if timelapse_config.get("frequent_timelapse"):
        frequent_timelapse_scheduler_thread_global = Thread(
            target=frequent_timelapse_scheduler_loop,
            daemon=True,
            name="frequent_timelapse_scheduler_loop",
        )
        frequent_timelapse_scheduler_thread_global.start()
        logging.info(f"Starting thread {frequent_timelapse_scheduler_thread_global.name}")
    else:
        logging.info("Frequent timelapse scheduler is disabled.")

    disk_management_thread_global = Thread(
        target=disk_management_loop, daemon=True, name="disk_management_loop"
    )
    disk_management_thread_global.start()
    logging.info(f"Starting thread {disk_management_thread_global.name}")

    try:
        while not exit_event.is_set():
            # Main loop can perform periodic checks or just wait for exit_event
            time.sleep(1)  # Keep main thread alive and responsive to signals
    except KeyboardInterrupt:  # Should be caught by SIGINT handler now
        logging.info(
            "KeyboardInterrupt caught in main loop (should have been handled by SIGINT). Exiting."
        )
        # This path should ideally not be taken if SIGINT handler works as expected.
    finally:
        logging.info("Main loop exiting. Cleaning up...")
        shutdown_application()


def load_and_apply_configuration(initial_load=False, config_file_override=None):
    """Loads configuration and applies it.
    If initial_load is True, it loads all configs and starts all services.
    If initial_load is False (on SIGHUP), it only reloads camera configs.
    """
    global server_config, cameras_config

    logging.info("Loading and applying configuration...")

    config_path_to_load = config_file_override if config_file_override else FLAGS.config
    if not config_path_to_load:
        logging.error(
            "No configuration file path specified. Cannot load configuration."
        )
        return

    # Load new configuration
    (
        new_server_config,
        new_cameras_config,
        new_global_config,
        new_admin_server_config,
        new_timelapse_config,
    ) = config_load(config_path_to_load)

    if initial_load:
        global global_config, admin_server_config, flask_app_instance, timelapse_config
        server_config = new_server_config
        global_config = new_global_config
        admin_server_config = new_admin_server_config
        timelapse_config = new_timelapse_config
        global_config["pic_dir"] = os.path.join(
            global_config.get("work_dir", "."), "photos"
        )

        try:
            from .admin_server import app as imported_flask_app

            flask_app_instance = imported_flask_app
        except ImportError as e:
            logging.error(
                f"Failed to import Flask app from admin_server: {e}. Config server UI will not be available."
            )
            flask_app_instance = None

        # Start HTTP Server if enabled
        if server_config.get("enabled", False):
            http_server_thread_global = Thread(
                target=server_run, daemon=True, name="http_server"
            )
            http_server_thread_global.start()

        # Start Config Server if enabled
        if admin_server_config.get("enabled", False) and flask_app_instance:
            main_config_file_path = FLAGS.config
            pid_file_path = FENETRE_PID_FILE
            admin_server_thread_global = Thread(
                target=run_admin_server_func,
                args=(
                    admin_server_config.get("listen", "0.0.0.0:8889"),
                    flask_app_instance,
                    main_config_file_path,
                    pid_file_path,
                ),
                daemon=True,
                name="admin_server_flask",
            )
            admin_server_thread_global.start()
    else:  # This is a reload
        # If server was enabled and is now disabled, stop it
        if server_config.get("enabled", False) and not new_server_config.get(
            "enabled", False
        ):
            stop_http_server()
        server_config = new_server_config

    # Update cameras_config and manage camera threads
    cameras_config = new_cameras_config
    if global_config.get("work_dir"):
        update_cameras_metadata(cameras_config, global_config["work_dir"])
        copy_public_html_files(global_config["work_dir"], global_config)
    else:
        logging.error(
            "work_dir not set in global config. Cannot update camera metadata."
        )

    manage_camera_threads()

    manage_camera_threads()


def manage_camera_threads():
    """Starts and stops camera threads based on the current cameras_config."""
    current_camera_names = set(cameras_config.keys())
    threads_to_remove = []

    # Stop threads for removed or disabled cameras
    for cam_name, thread_info in list(active_camera_threads.items()):
        if cam_name not in current_camera_names or cameras_config[cam_name].get(
            "disabled", False
        ):
            logging.info(
                f"Camera {cam_name} removed or disabled. Stopping its threads."
            )
            if (
                "watchdog_manager_thread" in thread_info
                and thread_info["watchdog_manager_thread"].is_alive()
            ):
                # The watchdog manager will see the camera is gone and exit.
                # We join to ensure it cleans up.
                thread_info["watchdog_manager_thread"].join(timeout=5)
            if (
                "gopro_utility" in thread_info
                and thread_info["gopro_utility"].is_alive()
            ):
                thread_info["gopro_utility"].stop()
                thread_info["gopro_utility"].join(timeout=5)
            threads_to_remove.append(cam_name)

    for cam_name in threads_to_remove:
        if cam_name in active_camera_threads:
            del active_camera_threads[cam_name]
        if cam_name in sleep_intervals:
            del sleep_intervals[cam_name]

    # Start threads for new or enabled cameras
    for cam_name, cam_conf in cameras_config.items():
        if cam_conf.get("disabled", False):
            continue

        if (
            cam_name not in active_camera_threads
            or not active_camera_threads[cam_name]
            .get("watchdog_manager_thread", {})
            .is_alive()
        ):
            logging.info(f"Starting/Restarting threads for camera {cam_name}")

            # Initialize sleep interval
            fixed_snap_interval = cam_conf.get("snap_interval_s", None)
            sleep_intervals[cam_name] = (
                float(fixed_snap_interval)
                if isinstance(fixed_snap_interval, (int, float))
                else 60.0
            )

            # Start watchdog manager for the snap thread
            watchdog_name = f"{cam_name}_watchdog_manager"
            cam_watchdog_thread = Thread(
                target=create_and_start_and_watch_thread,
                daemon=True,
                name=watchdog_name,
                args=[snap, f"{cam_name}_snap", [cam_name, cam_conf], 86400, cam_name],
            )
            cam_watchdog_thread.start()
            if cam_name not in active_camera_threads:
                active_camera_threads[cam_name] = {}
            active_camera_threads[cam_name][
                "watchdog_manager_thread"
            ] = cam_watchdog_thread

            # Start GoPro utility thread if needed
            if cam_conf.get("gopro_ip"):
                from .gopro import GoPro

                gopro_instance = GoPro(
                    ip_address=cam_conf.get("gopro_ip"),
                    root_ca=cam_conf.get("gopro_root_ca"),
                    log_dir=global_config.get("log_dir"),
                    latitude=cam_conf.get("lat"),
                    longitude=cam_conf.get("lon"),
                    timezone=global_config.get("timezone"),
                    preset_day=cam_conf.get("gopro_preset_day"),
                    preset_night=cam_conf.get("gopro_preset_night"),
                )
                gopro_utility_thread = GoProUtilityThread(
                    gopro_instance, cam_name, cam_conf, exit_event
                )
                gopro_utility_thread.start()
                if cam_name not in active_camera_threads:
                    active_camera_threads[cam_name] = {}
                active_camera_threads[cam_name]["gopro_utility"] = gopro_utility_thread
                active_camera_threads[cam_name]["gopro_instance"] = gopro_instance
        else:
            # For existing, running cameras, we could update settings like sleep_interval here if they change.
            fixed_snap_interval = cam_conf.get("snap_interval_s", None)
            if fixed_snap_interval is not None:
                new_interval = float(fixed_snap_interval)
                if sleep_intervals.get(cam_name) != new_interval:
                    logging.info(
                        f"Updating snap interval for camera {cam_name} to {new_interval}s"
                    )
                    sleep_intervals[cam_name] = new_interval


def handle_sighup(signum, frame):
    """Signal handler for SIGHUP to reload configuration."""
    logging.info(f"SIGHUP received. Reloading configuration from {FLAGS.config}...")
    # Schedule the reload to happen in the main thread or a dedicated thread
    # to avoid issues with signal handlers and complex operations.
    # For now, directly calling, but be wary of re-entrancy or blocking issues.
    # A queue processed by the main loop would be more robust for production.
    load_and_apply_configuration()  # Uses FLAGS.config by default


def signal_handler_exit(signum, frame):
    """Signal handler for SIGINT and SIGTERM to gracefully shut down."""
    signal_name = signal.Signals(signum).name
    if exit_event.is_set():
        logging.warning(f"Forcing shutdown.")
        sys.exit(0)
    logging.info(f"{signal_name} received. Initiating graceful shutdown...")
    exit_event.set()  # Signal all threads to exit
    # The main loop's finally block will call shutdown_application()


def shutdown_application():
    """Cleans up resources before exiting."""
    logging.info("Starting application shutdown sequence...")
    exit_event.set()  # Ensure it's set for all threads

    # Stop camera threads and their utility threads
    for cam_name, thread_info in list(active_camera_threads.items()):
        logging.info(f"Stopping threads for camera {cam_name}...")
        watchdog_manager = thread_info.get(
            "watchdog_manager_thread"
        )  # The thread that runs create_and_start_and_watch_thread
        gopro_utility = thread_info.get("gopro_utility")

        # The create_and_start_and_watch_thread loop itself respects exit_event.
        # The 'snap' thread started by it also respects exit_event.
        # So, setting exit_event should lead to their termination.
        # GoProUtilityThread should also respect exit_event.

        if gopro_utility and gopro_utility.is_alive():
            gopro_utility.join(timeout=10)  # Wait for GoPro utility thread
            if gopro_utility.is_alive():
                logging.warning(
                    f"GoPro utility thread for {cam_name} did not exit gracefully."
                )

        # The watchdog_manager_thread (which runs create_and_start_and_watch_thread) will exit once exit_event is set.
        # It, in turn, manages the actual snap_thread. The snap_thread also checks exit_event.
        if watchdog_manager and watchdog_manager.is_alive():
            watchdog_manager.join(timeout=10)  # Wait for the manager of the snap thread
            if watchdog_manager.is_alive():
                logging.warning(
                    f"Watchdog manager thread for {cam_name} did not exit gracefully."
                )

        # The actual snap thread (watchdog_thread in older naming) is managed by create_and_start_and_watch_thread
        # and should have been joined by its manager if it was robust.
        # Double check if it's still there and alive (shouldn't be if manager joined)
        snap_thread = thread_info.get("watchdog_thread")
        if snap_thread and snap_thread.is_alive():
            snap_thread.join(timeout=10)
            if snap_thread.is_alive():
                logging.warning(
                    f"Snap thread {snap_thread.name} for {cam_name} did not exit gracefully."
                )

    # Stop HTTP server
    stop_http_server()

    # Stop Config Server
    stop_admin_server()

    # Stop Timelapse and Daylight threads
    global timelapse_thread_global, daylight_thread_global
    if timelapse_thread_global and timelapse_thread_global.is_alive():
        timelapse_thread_global.join(timeout=10)
        if timelapse_thread_global.is_alive():
            logging.warning("Timelapse thread did not exit gracefully.")
    if daylight_thread_global and daylight_thread_global.is_alive():
        daylight_thread_global.join(timeout=10)
        if daylight_thread_global.is_alive():
            logging.warning("Daylight thread did not exit gracefully.")

    # Clean up PID file
    try:
        if os.path.exists(FENETRE_PID_FILE):
            os.remove(FENETRE_PID_FILE)
            logging.info(f"PID file {FENETRE_PID_FILE} removed.")
    except IOError as e:
        logging.error(f"Error removing PID file: {e}", exc_info=True)

    logging.info("Application shutdown complete.")
    # sys.exit(0) # Explicitly exit. This might be too abrupt if called from signal handler context.
    # Rely on main thread exiting naturally after exit_event is processed.

def frequent_timelapse_scheduler_loop():
    """
    This is a loop that schedules timelapse creation for the current day periodically.
    """
    interval = timelapse_config.get("frequent_timelapse").get("interval_s", 1200)
    while not exit_event.is_set():
        logging.info(f"Time to update today's timelapses.")
        for camera_name in cameras_config:
            pic_dir, _ = get_pic_dir_and_filename(camera_name)
            timelapse_settings_tuple = (pic_dir, timelapse_config.get("frequent_timelapse"))
            frequent_timelapse_q.append(timelapse_settings_tuple)
            interruptible_sleep(interval, exit_event)

def frequent_timelapse_loop():
    while not exit_event.is_set():
        if len(frequent_timelapse_q) == 0:
            time.sleep(5)
            continue
        timelapse_settings_tuple = frequent_timelapse_q.popleft()
        pic_dir, timelapse_settings = timelapse_settings_tuple
        try:
            result = create_timelapse(
                dir=pic_dir,
                overwrite=True,
                two_pass=timelapse_settings.get("ffmpeg_2pass", False),
                log_dir=global_config.get("log_dir"),
                ffmpeg_options=timelapse_settings.get("ffmpeg_options", ""),
                file_extension=timelapse_settings.get("file_extension"),
                framerate=timelapse_settings.get("framerate"),
            )
            if result:
                camera_name = os.path.basename(
                    os.path.dirname(os.path.normpath(pic_dir))
                )
                metric_timelapses_created_total.labels(
                    camera_name=camera_name
                ).inc()
            else:
                logging.error(
                    f"There was an error creating the timelapse for dir: {pic_dir}"
                )
        except FileExistsError:
            logging.warning(
                f"Found an existing timelapse in dir {pic_dir}, Skipping."
            )
        except Exception as e:
            logging.error(
                f"There was an error creating the timelapse for dir: {pic_dir}: {e}",
                exc_info=True,
            )
        time.sleep(5)

def timelapse_loop():
    """
    This is a loop with a blocking Thread to create high quality timelapses one at a time.
    This prevent overloading the system by creating new daily timelapses for all the cameras at the same time.
    """
    while not exit_event.is_set():
        dir_to_process = None
        with timelapse_queue_lock:
            with open(timelapse_queue_file, "r+") as f:
                lines = f.readlines()
                if lines:
                    dir_to_process = lines.pop(0).strip()
                    f.seek(0)
                    f.truncate()
                    f.writelines(lines)

        if dir_to_process:
            try:
                result = create_timelapse(
                    dir=dir_to_process,
                    overwrite=True,
                    two_pass=timelapse_config.get("ffmpeg_2pass", True),
                    log_dir=global_config.get("log_dir"),
                    ffmpeg_options=timelapse_config.get("ffmpeg_options", "-c:v libvpx-vp9 -b:v 0 -crf 30 -deadline best"),
                    file_extension=timelapse_config.get("file_extension", "webm"),
                    framerate=timelapse_config.get("framerate", 60),
                )
                if result:
                    camera_name = os.path.basename(
                        os.path.dirname(os.path.normpath(dir_to_process))
                    )
                    metric_timelapses_created_total.labels(
                        camera_name=camera_name
                    ).inc()
                    # Now we can delete the frequent timelapse file if it exists
                    frequent_timelapse_config = timelapse_config.get("frequent_timelapse", {})
                    if frequent_timelapse_config:
                        frequent_timelapse_file_extention = frequent_timelapse_config.get("file_extension", "mp4")
                        if frequent_timelapse_file_extention != timelapse_config.get("file_extension", "webm"):
                            frequent_timelapse_filepath = os.path.join(dir_to_process, os.path.basename(dir_to_process) + "." + frequent_timelapse_file_extention)
                            if os.path.exists(frequent_timelapse_filepath):
                                os.remove(frequent_timelapse_filepath)
                                logging.info(f"Deleted frequent timelapse file: {frequent_timelapse_filepath}")
                else:
                    logging.error(
                        f"There was an error creating the timelapse for dir: {dir_to_process}"
                    )
            except FileExistsError:
                logging.warning(
                    f"Found an existing timelapse in dir {dir_to_process}, Skipping."
                )
            except Exception as e:
                logging.error(
                    f"There was an error creating the timelapse for dir: {dir_to_process}: {e}",
                    exc_info=True,
                )
        time.sleep(1)


def daylight_loop():
    """
    This is a loop generating the daylight bands, one at a time.
    """
    while not exit_event.is_set():
        if len(daylight_q) > 0:
            camera_name, daily_pic_dir, sky_area = daylight_q.popleft()
            logging.info(
                f"Running daylight in {daily_pic_dir} with sky_area {sky_area}"
            )
            run_end_of_day(camera_name, daily_pic_dir, sky_area)
            with timelapse_queue_lock:
                with open(timelapse_queue_file, "a") as f:
                    f.write(f"{daily_pic_dir}\n")
            archive_q.append(daily_pic_dir)
        time.sleep(1)


def get_dir_size(path="."):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size


def disk_management_loop():
    """
    This is a loop that manages disk space.
    """
    storage_management_config = global_config.get("storage_management", {})
    if not storage_management_config.get("enabled", False):
        logging.info("Disk management is disabled.")
        return

    interval = storage_management_config.get("check_interval_s", 300)
    dry_run = storage_management_config.get("dry_run", True)

    while not exit_event.is_set():
        # Manage per-camera limits
        for camera_name, camera_config in cameras_config.items():
            camera_limit_gb = camera_config.get("work_dir_max_size_GB")
            if camera_limit_gb is None:
                continue

            camera_dir = os.path.join(global_config["pic_dir"], camera_name)
            if not os.path.isdir(camera_dir):
                continue

            current_size_bytes = get_dir_size(camera_dir)
            metric_camera_directory_size_bytes.labels(camera_name=camera_name).set(
                current_size_bytes
            )

            limit_bytes = camera_limit_gb * (1024**3)

            if current_size_bytes > limit_bytes:
                logging.info(
                    f"Camera {camera_name} is over its limit of {camera_limit_gb} GB. Current size: {current_size_bytes / (1024**3):.2f} GB. Deleting oldest directories."
                )
                subdirs = sorted([d.path for d in os.scandir(camera_dir) if d.is_dir() and d.name != "daylight"])
                for subdir in subdirs:
                    if current_size_bytes <= limit_bytes:
                        break
                    dir_to_delete_size = get_dir_size(subdir)
                    if dry_run:
                        logging.info(
                            f"[DRY RUN] Would delete {subdir} to free up {dir_to_delete_size / (1024**2):.2f} MB"
                        )
                    else:
                        logging.info(
                            f"Deleting {subdir} to free up {dir_to_delete_size / (1024**2):.2f} MB"
                        )
                        shutil.rmtree(subdir)
                    current_size_bytes -= dir_to_delete_size

        # Manage global limit
        global_limit_gb = storage_management_config.get("work_dir_max_size_GB")
        if global_limit_gb is not None:
            work_dir = global_config.get("work_dir")
            current_work_dir_size = get_dir_size(work_dir)
            metric_work_directory_size_bytes.set(current_work_dir_size)
            global_limit_bytes = global_limit_gb * (1024**3)

            if current_work_dir_size > global_limit_bytes:
                logging.info(
                    f"Global work_dir is over its limit of {global_limit_gb} GB. Current size: {current_work_dir_size / (1024**3):.2f} GB. Deleting oldest directories across all cameras."
                )

                all_day_dirs = []
                for camera_name in cameras_config:
                    camera_dir = os.path.join(global_config["pic_dir"], camera_name)
                    if os.path.isdir(camera_dir):
                        all_day_dirs.extend(
                            [d.path for d in os.scandir(camera_dir) if d.is_dir() and d.name != "daylight"]
                        )

                all_day_dirs.sort(key=lambda x: os.path.basename(x))

                for day_dir in all_day_dirs:
                    if current_work_dir_size <= global_limit_bytes:
                        break
                    dir_to_delete_size = get_dir_size(day_dir)
                    if dry_run:
                        logging.info(
                            f"[DRY RUN] Would delete {day_dir} to free up {dir_to_delete_size / (1024**2):.2f} MB"
                        )
                    else:
                        logging.info(
                            f"Deleting {day_dir} to free up {dir_to_delete_size / (1024**2):.2f} MB"
                        )
                        shutil.rmtree(day_dir)
                    current_work_dir_size -= dir_to_delete_size

        logging.debug(f"Disk management sleeping for {interval} seconds.")
        interruptible_sleep(interval, exit_event)


def archive_loop():
    """
    This is a loop with a blocking Thread to archive pictures one at a time.
    """
    while not exit_event.is_set():
        for camera_name, camera_config in cameras_config.items():
            camera_dir = os.path.join(global_config["pic_dir"], camera_name)
            scan_and_publish_metrics(camera_name, camera_dir, global_config)
            daydirs = list_unarchived_dirs(camera_dir)
            for daydir in daydirs:
                archive_daydir(
                    daydir=daydir,
                    global_config=global_config,
                    cam=camera_name,
                    sky_area=camera_config.get("sky_area"),
                    dry_run=False,
                    #TODO: Enable this after making the daylight an external file queue
                    create_daylight_bands=False,
                    daylight_bands_queue_file=None,
                    create_timelapses=True,
                    timelapse_queue_file=timelapse_queue_file,
                    timelapse_queue_file_lock=timelapse_queue_lock
                )
        interruptible_sleep(600, exit_event)


def run():
    """Entry point for the fenetre console script."""
    app.run(main)


if __name__ == "__main__":
    run()
