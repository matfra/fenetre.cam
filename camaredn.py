#!/usr/bin/env python3
import http.server
import json
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from datetime import timedelta
from functools import partial
from io import BytesIO
from threading import Thread
from typing import Dict
from typing import List

import mozjpeg_lossless_optimization
import pytz
import requests
import yaml
from absl import app
from absl import flags
from absl import logging
from PIL import Image
from SSIM_PIL import compare_ssim

from timelapse import create_timelapse
from daylight import run_end_of_day


DEFAULT_SKY_AREA = "100,0,400,50"


def config_load(config_file_path: str) -> List[Dict]:
    with open(config_file_path, "r") as f:
        config = yaml.safe_load(f)
        res = []
        for section in ["http_server", "cameras", "global"]:
            res.append(config[section])
        return res


def get_pic_from_url(url: str, timeout: int, ua: str = None) -> Image:
    headers = {"Accept": "image/*,*"}
    if ua:
        requests_version = requests.__version__
        headers = {"User-Agent": f"{ua} v{requests_version}"}
    r = requests.get(url, timeout=timeout, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(
            f"HTTP Request Failed!\n"
            f"URL: {url}\n"
            f"Status Code: {r.status_code}\n"
            f"Request Headers: {r.request.headers}\n"
            f"Response Headers: {r.headers}\n"
            f"Response Content (first 500 bytes): {r.content[:500]}"
        )

    return Image.open(BytesIO(r.content))


def get_pic_dir_and_filename(camera_name: str) -> str:
    tz = pytz.timezone(global_config["timezone"])
    dt = datetime.now(tz)
    return (
        os.path.join(global_config["pic_dir"], camera_name, dt.strftime("%Y-%m-%d")),
        dt.strftime("%Y-%m-%dT%H-%M-%S%Z.jpg"),
    )


def write_pic_to_disk(pic: Image, pic_path: str, optimize: bool = False):
    os.makedirs(os.path.dirname(pic_path), exist_ok=True)
    os.chmod(os.path.dirname(pic_path), 33277)  # rwxrwxr-x
    if logging.level_debug():
        logging.debug(f"Saving picture {pic_path}")
    if optimize is True:
        jpeg_io = BytesIO()
        pic.convert("RGB").save(jpeg_io, format="JPEG", quality=90)
        jpeg_io.seek(0)
        jpeg_bytes = jpeg_io.read()
        optimized_jpeg_bytes = mozjpeg_lossless_optimization.optimize(jpeg_bytes)
        with open(pic_path, "wb") as output_file:
            output_file.write(optimized_jpeg_bytes)
    else:
        pic.save(pic_path)


def update_latest_link(pic_path: str):
    cam_dir = os.path.join(os.path.dirname(pic_path), os.pardir)
    tmp_link = os.path.join(cam_dir, "new.jpg")
    latest_link = os.path.join(cam_dir, "latest.jpg")
    relative_path = os.path.relpath(pic_path, cam_dir)
    os.symlink(relative_path, tmp_link)
    os.rename(tmp_link, latest_link)


def get_pic_from_local_command(cmd: str, timeout_s: int) -> Image:
    s = subprocess.run(cmd.split(" "), stdout=subprocess.PIPE, timeout=timeout_s)
    return Image.open(BytesIO(s.stdout))


def snap(camera_name, camera_config: Dict):
    url = camera_config.get("url")
    timeout = camera_config.get("timeout_s", 20)
    local_command = camera_config.get("local_command")

    def capture() -> Image:
        if url is not None:
            ua = global_config.get("user_agent", None)
            return get_pic_from_url(url, timeout, ua)
        if local_command is not None:
            return get_pic_from_local_command(local_command, timeout)
        # Add more capture methods here
        return None

    # Initialization before the main loop
    previous_pic_dir, previous_pic_filename = get_pic_dir_and_filename(camera_name)
    previous_pic_fullpath = os.path.join(previous_pic_dir, previous_pic_filename)
    previous_pic = capture()
    fixed_snap_interval = camera_config.get("snap_interval_s", None)
    if not camera_name in sleep_intervals:
        sleep_intervals[camera_name] = (
            10 if fixed_snap_interval is None else fixed_snap_interval
        )  # Start at 10 unless manually specified

    # daylight_metadata is a map of picture filename and their average sky color
    daylight_metadata = {}

    # Capture loop
    while True:
        # Immediately save the previous pic to disk.
        write_pic_to_disk(
            previous_pic,
            previous_pic_fullpath,
            camera_config.get("mozjpeg_optimize", False),
        )
        update_latest_link(previous_pic_fullpath)
        if logging.level_debug():
            logging.debug(f"{camera_name}: Sleeping {sleep_intervals[camera_name]}s")
        time.sleep(sleep_intervals[camera_name])
        new_pic_dir, new_pic_filename = get_pic_dir_and_filename(camera_name)
        new_pic_fullpath = os.path.join(new_pic_dir, new_pic_filename)

        if not previous_pic_dir == new_pic_dir:
            # This is a new day. We can now process the previous day.
            timelapse_q.append(previous_pic_dir)
            daylight_q.append(
                (
                    camera_name,
                    previous_pic_dir,
                    camera_config.get("sky_area", DEFAULT_SKY_AREA),
                )
            )

        new_pic = capture()
        if new_pic is None:
            logging.warning(f"{camera_name}: Could not fetch picture from {url}")
            continue
        if fixed_snap_interval is None:
            ssim = get_ssim_for_area(
                previous_pic, new_pic, camera_config.get("ssim_area", None)
            )
            ssim_setpoint = camera_config.get("ssim_setpoint", 0.85)
            if ssim < ssim_setpoint:
                # We need to capture more frequently to get interesting things.
                # sleep_intervals[camera_name] -= 100*(ssim_setpoint-ssim)
                sleep_intervals[camera_name] = sleep_intervals[camera_name] * 0.9
            else:
                # We slow down the pace progressively (to make the timelapse less boring)
                # sleep_intervals[camera_name] += 2
                sleep_intervals[camera_name] += 0.5
            if logging.level_debug():
                logging.debug(
                    f"{camera_name}: ssim {ssim}, setpoint: {ssim_setpoint}, new sleep interval: {sleep_intervals[camera_name]}s"
                )
        previous_pic = new_pic
        previous_pic_dir = new_pic_dir
        previous_pic_fullpath = new_pic_fullpath


def get_ssim_for_area(image1: Image, image2: Image, area: str) -> float:
    if area is None:
        return compare_ssim(image1, image2)
    crop_points = [int(i) for i in area.split(",")]
    logging.debug(f"{crop_points}")
    return compare_ssim(
        image1.crop(crop_points).resize(
            (50, 50)
        ),  # Resize 50x50 gets rid of the noise at night.
        image2.crop(crop_points).resize((50, 50)),
    )


def server_run():
    server_class = http.server.ThreadingHTTPServer
    handler_class = partial(
        http.server.SimpleHTTPRequestHandler, directory=global_config["work_dir"]
    )
    server_address = (server_config["host"], server_config["port"])
    logging.info(f"Starting HTTP Server on {server_address}")
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


def create_and_start_and_watch_thread(
    f: callable, name: str, arguments: List[str] = [], exp_backoff_limit: int = 0
) -> None:
    failure_count = 0
    last_failure = datetime.now()
    global sleep_intervals
    sleep_intervals = {}  # Store the sleep time outside of the thread (which can die)
    while True:
        running_threads_name = [t.name for t in threading.enumerate()]

        if not name in running_threads_name:
            t = Thread(target=f, daemon=False, name=name, args=arguments)
            exp_backoff_delay = min(exp_backoff_limit, 2**failure_count)
            # If the last failure is more than 90 seconds, reset the failure counter
            if datetime.now() - last_failure > timedelta(0, 90, 000000):
                failure_count = 0
            failure_count += 1
            logging.info(
                f"Failed {failure_count} times. Restarting the thread {name} in {exp_backoff_delay}s"
            )
            last_failure = datetime.now()
            time.sleep(exp_backoff_delay)
            t.start()
        time.sleep(1)


def link_html_file(work_dir: str):
    current_dir = os.getcwd()
    shutil.copy(
        os.path.join(current_dir, "index.html"), os.path.join(work_dir, "index.html")
    )


def update_cameras_metadata(cameras_configs: Dict, work_dir: str):
    """cameras.json is a public file describing info about the cameras used to power the map view.
    We add to this file, never delete, but we do update the cameras if their info (i.e. coordinates) changed.
    """

    updated_cameras_metadata = []

    json_filepath = os.path.join(work_dir, "cameras.json")
    with open(json_filepath, "r") as json_file:
        cameras_public_metadata = json.load(json_file)

        for camera_metadata in cameras_public_metadata:
            if camera_metadata["title"] not in cameras_config:
                logging.warning(
                    f"Camera {camera_metadata['title']} is not configured anymore. Delete it from {json_filepath} manually if you want to."
                )
                updated_cameras_metadata.append(camera_metadata)

    for cam in cameras_config:
        metadata = {}
        metadata["title"] = cam
        metadata["url"] = os.path.join("photos", cam)
        metadata["image"] = os.path.join("photos", cam, "latest.jpg")
        metadata["lat"] = cameras_config[cam].get("lat", None)
        metadata["lon"] = cameras_config[cam].get("lon", None)
        updated_cameras_metadata.append(metadata)

    with open(json_filepath, "w") as json_file:
        json.dump(updated_cameras_metadata, json_file, indent=4)


def main(argv):
    del argv  # Unused.

    # TODO: Are global variable really necessary?
    global server_config, cameras_config, global_config
    server_config, cameras_config, global_config = config_load(FLAGS.config)
    global_config["pic_dir"] = os.path.join(global_config["work_dir"], "photos")

    if logging.level_debug():
        logging.debug(
            f"Loaded config: server: {server_config} cameras: {cameras_config} global: {global_config}"
        )

    global timelapse_q, daylight_q
    timelapse_q = deque()
    daylight_q = deque()

    # HTML Interface.
    link_html_file(global_config["work_dir"])
    update_cameras_metadata(cameras_config, global_config["work_dir"])

    # Start camera threads.
    for cam in cameras_config:
        if cameras_config[cam].get("disabled", False) is True:
            # If the camera is disabled, we skip it.
            logging.info(
                f"Camera {cam} is disabled in the config. Skipping it."
            )
            continue
        Thread(
            target=create_and_start_and_watch_thread,
            daemon=True,
            name=f"{cam}_watchdog",
            args=[snap, cam, [cam, cameras_config[cam]], 86400],
        ).start()

    # Optional web server
    if server_config.get("enabled", False):
        server_thread = Thread(target=server_run, daemon=True, name="http_server")
        logging.info(f"Starting thread {server_thread}")
        server_thread.start()

    timelapse_thread = Thread(target=timelapse_loop, daemon=True, name="timelapse_loop")
    logging.info(f"Starting thread {timelapse_loop}")
    timelapse_thread.start()

    daylight_thread = Thread(target=daylight_loop, daemon=True, name="daylight_loop")
    logging.info(f"Starting thread {daylight_loop}")
    daylight_thread.start()

    while True:
        time.sleep(5)


def timelapse_loop():
    """
    This is a loop with a blocking Thread to create timelapses one at a time.
    This prevent overloading the system by creating new daily timelapses for all the cameras at the same time.
    """
    while True:
        if len(timelapse_q) > 0:
            dir = timelapse_q.popleft()
            result = False
            try:
                create_timelapse(
                    dir=dir,
                    overwrite=True,
                    ffmpeg_options=global_config.get("ffmpeg_options", "-framerate 30"),
                    two_pass=global_config.get("ffmpeg_2pass", False),
                    file_ext=global_config.get("timelapse_file_extension", "mp4"),
                    tmp_dir=global_config.get("tmp_dir"),
                )
            except FileExistsError:
                logging.warning(f"Found an existing timelapse in dir {dir}, Skipping.")
            if result is False:
                logging.error(
                    f"There was an error creating the timelapse for dir: {dir}"
                )
        time.sleep(30)

def daylight_loop():
    """
    This is a loop generating the daylight bands, one at a time.
    """
    while True:
        if len(daylight_q) > 0:
            camera_name, daily_pic_dir, sky_area = daylight_q.popleft()
            logging.info(
                f"Running daylight in {daily_pic_dir} with sky_area {sky_area}"
            )
            run_end_of_day(camera_name, daily_pic_dir, sky_area)
        time.sleep(10)


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string("config", None, "path to YAML config file")
    flags.mark_flag_as_required("config")
    app.run(main)
