import sys
import requests
import yaml
import time
from datetime import datetime, timedelta
import os
import pytz

from absl import app
from absl import flags
from absl import logging
from typing import Dict, List

from PIL import Image
from io import BytesIO
from SSIM_PIL import compare_ssim

from threading import Thread
import threading
import http.server
from functools import partial

FLAGS = flags.FLAGS

flags.DEFINE_string("config", None, "path to YAML config file")

flags.mark_flag_as_required("config")


def config_load(config_file_path: str) -> List[Dict]:
    with open(config_file_path, "r") as f:
        config = yaml.safe_load(f)
        res = []
        for section in ["server", "cameras", "global"]:
            res.append(config[section])
        return res


def get_pic_from_url(url: str) -> Image:
    r = requests.get(url, timeout=20)
    return Image.open(BytesIO(r.content))


def get_interval_from_pic(image1: Image, image2: Image):
    x = compare_ssim(image1, image2)
    if not isinstance(x, float):
        logging.warning(
            f"Could not get compute the difference between the last 2 pictures"
        )
        return 10
    if logging.level_debug():
        logging.debug(f"ssim: {x}")
    return int(
        180 * (max(x, 0.5) - 0.45)
    )  # https://www.wolframalpha.com/input?i=180*%28max%28x%2C0.5%29-0.45%29


def get_pic_fullpath(camera_name: str) -> str:
    tz = pytz.timezone(global_config["timezone"])
    dt = tz.localize(datetime.now())
    return os.path.join(
        global_config["pic_dir"],
        camera_name,
        dt.strftime("%Y-%m-%d"),
        dt.strftime("%Y-%m-%dT%H-%M-%S%Z.jpg"),
    )


def write_pic_to_disk(pic: Image, pic_path: str):
    os.makedirs(os.path.dirname(pic_path), exist_ok=True)
    if logging.level_debug():
        logging.debug(f"Saving picture {pic_path}")
    pic.save(pic_path)


def snap(camera_name, camera_config: Dict):
    url = camera_config["url"]
    previous_pic_fullpath = get_pic_fullpath(camera_name)
    previous_pic = get_pic_from_url(url)
    sleep_interval = 5
    while True:
        write_pic_to_disk(previous_pic, previous_pic_fullpath)
        if logging.level_debug():
            logging.debug(f"{camera_name}: Sleeping {sleep_interval}s")
        time.sleep(sleep_interval)
        new_pic_fullpath = get_pic_fullpath(camera_name)
        new_pic = get_pic_from_url(url)
        if new_pic is None:
            logging.warning(f"{camera_name}: Could not fetch picture from {url}")
            continue
        sleep_interval = get_interval_from_pic(previous_pic, new_pic)
        previous_pic = new_pic
        previous_pic_fullpath = new_pic_fullpath


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
            time.sleep(exp_backoff_delay)
            t.start()
        time.sleep(1)


def main(argv):
    del argv  # Unused.

    print(
        "Running under Python {0[0]}.{0[1]}.{0[2]}".format(sys.version_info),
        file=sys.stderr,
    )
    global server_config, cameras_config, global_config
    server_config, cameras_config, global_config = config_load(FLAGS.config)
    global_config["pic_dir"] = os.path.join(global_config["work_dir"], "photos")

    if logging.level_debug():
        logging.debug(
            f"Loaded config: server: {server_config} cameras: {cameras_config} global: {global_config}"
        )

    for cam in cameras_config:
        Thread(
            target=create_and_start_and_watch_thread,
            daemon=True,
            name=f"{cam}_watchdog",
            args=[snap, cam, [cam, cameras_config[cam]], 86400],
        ).start()

    server_thread = Thread(target=server_run, daemon=True, name="http_server")
    logging.info(f"Starting thread {server_thread}")
    server_thread.start()
    server_thread.join()


if __name__ == "__main__":
    app.run(main)
