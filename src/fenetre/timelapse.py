import glob
import json
import logging
import logging.handlers
import os
import subprocess
import threading
from io import TextIOWrapper
from typing import Optional

from PIL import Image

from fenetre.admin_server import metric_timelapse_queue_size
from fenetre.platform_utils import is_raspberry_pi

logger = logging.getLogger(__name__)


def get_image_dimensions(image_path: str):
    """Gets the dimensions of an image."""
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        logger.error(f"Error getting dimensions for {image_path}: {e}")
        return None


def create_timelapse(
    dir: str,
    overwrite: bool,
    two_pass: Optional[bool] = False,
    log_dir: Optional[str] = None,
    tmp_dir: Optional[str] = "/dev/shm/fenetre",
    dry_run: bool = False,
    ffmpeg_options: str = None,
    file_extension: Optional[str] = None,
    framerate: Optional[int] = None,
    log_max_bytes: int = 10000000,
    log_backup_count: int = 5,
) -> bool:
    if not os.path.exists(dir):
        raise FileNotFoundError(dir)

    image_files = sorted(glob.glob(os.path.join(os.path.abspath(dir), "*.jpg")))
    images_count = len(image_files)
    images_count_before = images_count
    if images_count == 0:
        logger.error(f"No jpg images found in {dir}.")
        return

    logging.debug(
        f"Found {images_count} pictures. Looking for duplicates or 0-bytes ones"
    )
    previous_image_size_bytes = 0
    # Delete 0-byte images
    for image_path in image_files:
        image_size_bytes = os.path.getsize(image_path)
        if image_size_bytes == 0:
            logger.warning(f"Deleting 0-byte image: {image_path}")
            os.remove(image_path)
            images_count -= 1
        elif image_size_bytes == previous_image_size_bytes:
            logger.warning(f"Deleting duplicate image: {image_path}")
            os.remove(image_path)
            images_count -= 1
        previous_image_size_bytes = image_size_bytes

    logger.warning(f"Kept {images_count} out of {images_count_before} in {dir}")
    if images_count < 1:
        logger.error(f"No valid jpg images found in {dir} after removing 0-byte files.")
        return

    width, height = get_image_dimensions(image_files[0])

    if is_raspberry_pi():
        default_encoder_options = "-c:v h264_v4l2m2m -b:v 5M"
        max_width = 1920
        max_height = 1080
        if framerate is None:
            framerate = 30
        two_pass = False  # multi pass encoding not supported with hardware encoder
    else:
        default_encoder_options = "-c:v libvpx-vp9 -b:v 5M"
        max_width = 3840
        max_height = 2160
        if two_pass is None:
            two_pass = True  # VP9 can take advantage of multiple pass
        if len(image_files) > 1200:
            framerate = 60
        else:
            framerate = 30

    aspect_ratio = width / height
    if aspect_ratio > 16 / 9:  # Wider
        if width >= max_width:
            scale_vf = f"scale={max_width}:-2"
        elif width >= 2560:
            scale_vf = "scale=2560:-2"
        else:
            scale_vf = "scale=1920:-2"
    else:  # Taller or 16:9
        if height >= max_height:
            scale_vf = f"scale=-2:{max_height}"
        elif height >= 1440:
            scale_vf = "scale=-2:1440"
        elif height >= 1080:
            scale_vf = "scale=-2:1080"
        else:
            scale_vf = "scale=-2:720"

    if file_extension is None:
        # search the ffmpeg_options string for vp9
        if ffmpeg_options:
            if "vp9" in ffmpeg_options:
                file_extension = "webm"
        file_extension = "mp4"

    timelapse_filename = os.path.basename(dir) + "." + file_extension
    timelapse_filepath = os.path.join(dir, timelapse_filename)

    logger.info(
        f"Encoding {images_count} images to {timelapse_filepath} at {framerate} fps"
    )

    ffmpeg_log_stream = subprocess.DEVNULL

    # Only set up file logging if in debug mode and log_dir is provided
    if log_dir and logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
        ffmpeg_logger = logging.getLogger("ffmpeg")
        if not ffmpeg_logger.hasHandlers():
            log_file_path = os.path.join(log_dir, "ffmpeg.log")
            handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=log_max_bytes,
                backupCount=log_backup_count,
            )
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            ffmpeg_logger.addHandler(handler)
            ffmpeg_logger.setLevel(logging.DEBUG)
            ffmpeg_logger.propagate = False

        # Find the handler's stream to redirect subprocess output
        for handler in ffmpeg_logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                ffmpeg_log_stream = handler.stream
                break
    else:
        logger.info("ffmpeg logs will be discarded (enable debug mode to see them).")

    logger.debug(f"timelapse_filepath: {timelapse_filepath}")

    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir, exist_ok=True)
    if os.path.exists(timelapse_filepath) and not overwrite:
        raise FileExistsError(timelapse_filepath)

    ffmpeg_cmd = [
        # Lower priority
        "nice",
        "-n10",
        "ffmpeg",
        # FFMPEG Global options
        "-hide_banner",
        "-loglevel",
        "warning",
        # FFMPEG Input options
        "-framerate",
        str(framerate),
        "-pattern_type",
        "glob",
        # FFMPEG Input
        "-i",
        os.path.join(os.path.abspath(dir), "*.jpg"),
        #        "-pix_fmt",
        #        "yuv420p",
        # FFMPEG Filters
        "-vf",
        f"{scale_vf},format=yuv420p",
    ]
    if overwrite:
        ffmpeg_cmd.append("-y")
    if not ffmpeg_options:
        # FFMPEG output options
        ffmpeg_options = default_encoder_options
    ffmpeg_cmd.extend(ffmpeg_options.split(" "))

    if two_pass:
        # FFMPEG output
        first_pass_cmd = ffmpeg_cmd + [
            "-pass",
            "1",
            "-an",
            "-f",
            "null",
            "/dev/null",
        ]
        logger.info(f"Running ffmpeg first pass: {' '.join(first_pass_cmd)}")
        if not dry_run:
            subprocess.run(
                first_pass_cmd,
                cwd=tmp_dir,  # We need a temporary file to store the first pass log
                check=True,
                stdout=ffmpeg_log_stream,
                stderr=ffmpeg_log_stream,
            )

            second_pass_cmd = ffmpeg_cmd + [
                "-pass",
                "2",
                os.path.abspath(timelapse_filepath),
            ]
            logger.info(f"Running ffmpeg second pass: {' '.join(second_pass_cmd)}")
            if not dry_run:
                subprocess.run(
                    second_pass_cmd,
                    cwd=tmp_dir,
                    check=True,
                    stdout=ffmpeg_log_stream,
                    stderr=ffmpeg_log_stream,
                )
    else:
        final_cmd = ffmpeg_cmd + [os.path.abspath(timelapse_filepath)]
        logger.info(f"Running ffmpeg: {' '.join(final_cmd)}")
        if not dry_run:
            subprocess.run(
                final_cmd,
                cwd=tmp_dir,
                check=True,
                stdout=ffmpeg_log_stream,
                stderr=ffmpeg_log_stream,
            )
    if isinstance(ffmpeg_log_stream, TextIOWrapper):
        ffmpeg_log_stream.close()

    if os.path.exists(timelapse_filepath) and os.path.getsize(timelapse_filepath) > 0:
        # Update cameras.json if timelapse was created successfully
        camera_name = os.path.basename(os.path.dirname(dir))
        cameras_json_path = os.path.join(
            os.path.dirname(os.path.dirname(dir)), "cameras.json"
        )
        if os.path.exists(cameras_json_path):
            with open(cameras_json_path, "r+") as f:
                data = json.load(f)
                for camera in data.get("cameras", []):
                    if camera.get("title") == camera_name:
                        camera["latest_timelapse"] = os.path.relpath(
                            timelapse_filepath, os.path.dirname(cameras_json_path)
                        )
                        f.seek(0)
                        json.dump(data, f, indent=4)
                        f.truncate()
                        break
        return True
    return False


def add_to_timelapse_queue(
    daydir: str, timelapse_queue_file: str, lock: threading.Lock
):
    """Adds a directory to the timelapse queue file if it's not already there."""
    with lock:
        # a+ creates the file if it does not exist and opens it for reading and appending.
        with open(timelapse_queue_file, "a+") as f:
            f.seek(0)  # Go to the beginning to read the content
            lines = f.readlines()
            daydir_stripped = daydir.strip()
            # Check if daydir is already in the queue
            for line in lines:
                if daydir_stripped == line.strip():
                    logging.info(
                        f"{daydir_stripped} was already in the timelapse queue. Not adding it again."
                    )
                    return

            # Add the new daydir and sort the queue
            lines.append(f"{daydir_stripped}\n")
            # Sort by date descending, so newest are first.
            lines.sort(key=lambda p: os.path.basename(p.strip()), reverse=True)
            f.seek(0)
            f.truncate()
            f.writelines(lines)
            logging.info(
                f"Added {daydir_stripped} to the timelapse queue. Queue size: {len(lines)}"
            )
            metric_timelapse_queue_size.set(len(lines))


def get_queue_size_and_set_metric(timelapse_queue_file: str, lock: threading.Lock):
    """Reads the queue file and sets the initial value for the metric."""
    with lock:
        try:
            with open(timelapse_queue_file, "r") as f:
                lines = f.readlines()
                metric_timelapse_queue_size.set(len(lines))
                logging.info(f"Initial timelapse queue size: {len(lines)}")
        except FileNotFoundError:
            metric_timelapse_queue_size.set(0)
            logging.info("Initial timelapse queue size: 0 (file not found)")


def get_next_from_timelapse_queue(
    timelapse_queue_file: str, lock: threading.Lock
) -> Optional[str]:
    """Gets the next item from the queue without removing it."""
    with lock:
        try:
            with open(timelapse_queue_file, "r") as f:
                lines = f.readlines()
                if not lines:
                    return None
                return lines[0].strip()
        except FileNotFoundError:
            return None


def remove_from_timelapse_queue(
    daydir: str, timelapse_queue_file: str, lock: threading.Lock
):
    """Removes a specific directory from the timelapse queue file."""
    logging.info(f"Removing {daydir} from {timelapse_queue_file}.")
    with lock:
        try:
            with open(timelapse_queue_file, "r+") as f:
                lines = f.readlines()
                new_lines = [line for line in lines if line.strip() != daydir.strip()]
                if len(new_lines) < len(lines):
                    f.seek(0)
                    f.truncate()
                    f.writelines(new_lines)
                    logging.info(f"Removed {daydir.strip()} from timelapse queue.")
                    metric_timelapse_queue_size.set(len(new_lines))
                else:
                    logging.warning(
                        f"Tried to remove {daydir.strip()} from timelapse queue, but it was not found."
                    )
        except FileNotFoundError:
            logging.error(f"Timelapse queue file not found at {timelapse_queue_file}")
