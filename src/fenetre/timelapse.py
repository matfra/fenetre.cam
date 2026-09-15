import glob
import json
import logging
import logging.handlers
import os
import subprocess
import tempfile
import threading
from io import TextIOWrapper
from typing import Optional
import shutil
import math

from PIL import Image

from fenetre.admin_server import metric_timelapse_queue_size
from fenetre.platform_utils import is_raspberry_pi
from fenetre import profiler

logger = logging.getLogger(__name__)


def get_image_dimensions(image_path: str):
    """Gets the dimensions of an image."""
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        logger.error(f"Error getting dimensions for {image_path}: {e}")
        return None


def _filter_image_files(image_files, destructive: bool = False):
    images_count_before = len(image_files)
    logger.debug(
        "Found %s pictures. Looking for duplicates or 0-bytes ones", images_count_before
    )
    previous_image_size_bytes = 0
    filtered = []
    for image_path in image_files:
        image_size_bytes = os.path.getsize(image_path)
        if image_size_bytes == 0:
            logger.warning("Deleting 0-byte image: %s", image_path)
            if destructive:
                os.remove(image_path)
            continue
        if image_size_bytes == previous_image_size_bytes:
            logger.warning("Deleting duplicate image: %s", image_path)
            if destructive:
                os.remove(image_path)
            continue
        filtered.append(image_path)
        previous_image_size_bytes = image_size_bytes
    logger.warning("Kept %s out of %s in %s", len(filtered), images_count_before, image_files[0] if image_files else "")
    return filtered, images_count_before


def _compute_scale_vf(width: int, height: int, max_width: int, max_height: int) -> str:
    aspect_ratio = width / height
    if aspect_ratio > 16 / 9:
        if width >= max_width:
            return f"scale={max_width}:-2"
        if width >= 2560:
            return "scale=2560:-2"
        return "scale=1920:-2"
    if height >= max_height:
        return f"scale=-2:{max_height}"
    if height >= 1440:
        return "scale=-2:1440"
    if height >= 1080:
        return "scale=-2:1080"
    return "scale=-2:720"


def _setup_ffmpeg_log_stream(log_dir: Optional[str], log_max_bytes: int, log_backup_count: int):
    ffmpeg_log_stream = subprocess.DEVNULL
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

        for handler in ffmpeg_logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                ffmpeg_log_stream = handler.stream
                break
    else:
        logger.info("ffmpeg logs will be discarded (enable debug mode to see them).")
    return ffmpeg_log_stream


def _update_latest_timelapse_reference(dir: str, timelapse_filepath: str):
    camera_name = os.path.basename(os.path.dirname(dir))
    cameras_json_path = os.path.join(os.path.dirname(os.path.dirname(dir)), "cameras.json")
    if not os.path.exists(cameras_json_path):
        return
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


def _load_hls_manifest(manifest_path: str) -> dict:
    if not os.path.exists(manifest_path):
        return {"last_image": None, "segments": []}
    with open(manifest_path, "r") as f:
        return json.load(f)


def _write_hls_manifest(manifest_path: str, manifest: dict):
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def _write_hls_playlist(playlist_path: str, segments: list):
    target_duration = 1
    if segments:
        target_duration = max(1, math.ceil(max(segment["duration"] for segment in segments)))
    with open(playlist_path, "w") as f:
        f.write("#EXTM3U\n")
        f.write("#EXT-X-VERSION:3\n")
        f.write("#EXT-X-PLAYLIST-TYPE:EVENT\n")
        f.write(f"#EXT-X-TARGETDURATION:{target_duration}\n")
        f.write("#EXT-X-MEDIA-SEQUENCE:0\n")
        for segment in segments:
            f.write(f"#EXTINF:{segment['duration']:.6f},\n")
            f.write(f"{segment['path']}\n")


def create_incremental_hls_timelapse(
    dir: str,
    log_dir: Optional[str] = None,
    tmp_dir: Optional[str] = "/dev/shm/fenetre",
    dry_run: bool = False,
    ffmpeg_options: str = None,
    framerate: Optional[int] = None,
    hls_segment_type: str = "mpegts",
    hls_segment_extension: Optional[str] = None,
    log_max_bytes: int = 10000000,
    log_backup_count: int = 5,
) -> bool:
    if not os.path.exists(dir):
        raise FileNotFoundError(dir)

    image_files = sorted(glob.glob(os.path.join(os.path.abspath(dir), "*.jpg")))
    image_files, _ = _filter_image_files(image_files, destructive=False)
    if not image_files:
        logger.error("No valid jpg images found in %s.", dir)
        return False

    width, height = get_image_dimensions(image_files[0])
    if width is None or height is None:
        return False

    if is_raspberry_pi():
        default_encoder_options = "-c:v h264_v4l2m2m -b:v 5M"
        max_width = 1920
        max_height = 1080
        if framerate is None:
            framerate = 30
    else:
        default_encoder_options = "-c:v libx264 -preset veryfast -crf 23"
        max_width = 3840
        max_height = 2160
        if framerate is None:
            framerate = 30

    scale_vf = _compute_scale_vf(width, height, max_width, max_height)
    base_name = os.path.basename(dir)
    playlist_path = os.path.join(dir, f"{base_name}.m3u8")
    legacy_segment_dir = os.path.join(dir, f"{base_name}.segments")
    manifest_path = os.path.join(dir, f".{base_name}.hls-manifest.json")
    manifest = _load_hls_manifest(manifest_path)

    last_image = manifest.get("last_image")
    if last_image and last_image in image_files:
        new_images = image_files[image_files.index(last_image) + 1 :]
    elif last_image:
        logger.warning(
            "Frequent HLS manifest for %s references missing image %s. Rebuilding playlist.",
            dir,
            last_image,
        )
        shutil.rmtree(legacy_segment_dir, ignore_errors=True)
        for segment_path in glob.glob(os.path.join(dir, "segment-*.*")):
            os.remove(segment_path)
        init_path = os.path.join(dir, "init.mp4")
        if os.path.exists(init_path):
            os.remove(init_path)
        if os.path.exists(playlist_path):
            os.remove(playlist_path)
        manifest = {"last_image": None, "segment_index": 0}
        new_images = image_files
    else:
        new_images = image_files

    # Migrate away from the legacy segment subdirectory. ffmpeg's HLS muxer keeps
    # playlist URIs flat, so storing the segments next to the playlist avoids broken
    # relative paths like `segment-000000.ts` pointing at a missing file.
    if os.path.isdir(legacy_segment_dir):
        logger.info("Removing legacy HLS segment directory %s before rebuild", legacy_segment_dir)
        shutil.rmtree(legacy_segment_dir, ignore_errors=True)
        for segment_path in glob.glob(os.path.join(dir, "segment-*.*")):
            os.remove(segment_path)
        init_path = os.path.join(dir, "init.mp4")
        if os.path.exists(init_path):
            os.remove(init_path)
        if os.path.exists(playlist_path):
            os.remove(playlist_path)
        manifest = {"last_image": None, "segment_index": 0}
        new_images = image_files

    if not new_images:
        if os.path.exists(playlist_path):
            _update_latest_timelapse_reference(dir, playlist_path)
            return True
        return False

    ffmpeg_log_stream = _setup_ffmpeg_log_stream(log_dir, log_max_bytes, log_backup_count)
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir, exist_ok=True)

    segment_index = int(manifest.get("segment_index", 0))
    if not hls_segment_extension:
        hls_segment_extension = "m4s" if hls_segment_type == "fmp4" else "ts"
    segment_pattern = f"segment-%06d.{hls_segment_extension}"

    duration_per_image = 1.0 / float(framerate)
    concat_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ffconcat",
        prefix="fenetre-hls-",
        dir=tmp_dir,
        delete=False,
    )
    try:
        for image_path in new_images:
            concat_file.write(f"file '{image_path}'\n")
            concat_file.write(f"duration {duration_per_image:.12f}\n")
        concat_file.write(f"file '{new_images[-1]}'\n")
        concat_file.close()

        if not ffmpeg_options:
            ffmpeg_options = default_encoder_options
        final_cmd = [
            "nice",
            "-n10",
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file.name,
            "-vsync",
            "cfr",
            "-r",
            str(framerate),
            "-vf",
            f"{scale_vf},format=yuv420p",
            "-y",
        ]
        final_cmd.extend(ffmpeg_options.split(" "))
        final_cmd.extend(
            [
                "-f",
                "hls",
                "-hls_time",
                "2",
                "-hls_list_size",
                "0",
                "-hls_playlist_type",
                "event",
                "-hls_segment_type",
                hls_segment_type,
                "-hls_flags",
                "append_list+independent_segments+program_date_time+temp_file",
                "-start_number",
                str(segment_index),
                "-hls_segment_filename",
                segment_pattern,
            ]
        )
        if hls_segment_type == "fmp4":
            final_cmd.extend(["-hls_fmp4_init_filename", "init.mp4"])
        final_cmd.append(playlist_path)

        logger.info(
            "Running incremental HLS ffmpeg for %s new images into %s",
            len(new_images),
            playlist_path,
        )
        if not dry_run:
            with profiler.timed("timelapse.frequent_hls_segment"):
                subprocess.run(
                    final_cmd,
                    cwd=dir,
                    check=True,
                    stdout=ffmpeg_log_stream,
                    stderr=ffmpeg_log_stream,
                )
    finally:
        if os.path.exists(concat_file.name):
            os.remove(concat_file.name)
        if isinstance(ffmpeg_log_stream, TextIOWrapper):
            ffmpeg_log_stream.close()

    segment_count = len(
        glob.glob(os.path.join(dir, f"segment-*.{hls_segment_extension}"))
    )
    manifest["last_image"] = new_images[-1]
    manifest["segment_index"] = segment_count
    _write_hls_manifest(manifest_path, manifest)
    _update_latest_timelapse_reference(dir, playlist_path)
    return True


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
    if len(image_files) == 0:
        logger.error(f"No jpg images found in {dir}.")
        return False

    image_files, _ = _filter_image_files(image_files, destructive=True)
    images_count = len(image_files)
    if images_count < 1:
        logger.error(f"No valid jpg images found in {dir} after removing 0-byte files.")
        return False

    width, height = get_image_dimensions(image_files[0])
    if width is None or height is None:
        return False

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

    scale_vf = _compute_scale_vf(width, height, max_width, max_height)

    if file_extension is None:
        # search the ffmpeg_options string for vp9
        if ffmpeg_options:
            if "vp9" in ffmpeg_options:
                file_extension = "webm"
        file_extension = "mp4"

    timelapse_filename = os.path.basename(dir) + "." + file_extension
    timelapse_filepath = os.path.join(dir, timelapse_filename)
    base, ext = os.path.splitext(timelapse_filename)
    tmp_timelapse_filepath = os.path.join(dir, f".{base}.tmp{ext}")

    logger.info(
        f"Encoding {images_count} images to {timelapse_filepath} at {framerate} fps"
    )

    ffmpeg_log_stream = _setup_ffmpeg_log_stream(
        log_dir, log_max_bytes, log_backup_count
    )

    logger.debug(f"timelapse_filepath: {timelapse_filepath}")

    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir, exist_ok=True)
    if os.path.exists(timelapse_filepath) and not overwrite:
        raise FileExistsError(timelapse_filepath)
    if os.path.exists(tmp_timelapse_filepath):
        os.remove(tmp_timelapse_filepath)

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
            with profiler.timed("timelapse.ffmpeg_first_pass"):
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
                os.path.abspath(tmp_timelapse_filepath),
            ]
            logger.info(f"Running ffmpeg second pass: {' '.join(second_pass_cmd)}")
            if not dry_run:
                with profiler.timed("timelapse.ffmpeg_second_pass"):
                    subprocess.run(
                        second_pass_cmd,
                        cwd=tmp_dir,
                        check=True,
                        stdout=ffmpeg_log_stream,
                        stderr=ffmpeg_log_stream,
                    )
    else:
        final_cmd = ffmpeg_cmd + [os.path.abspath(tmp_timelapse_filepath)]
        logger.info(f"Running ffmpeg: {' '.join(final_cmd)}")
        if not dry_run:
            with profiler.timed("timelapse.ffmpeg"):
                subprocess.run(
                    final_cmd,
                    cwd=tmp_dir,
                    check=True,
                    stdout=ffmpeg_log_stream,
                    stderr=ffmpeg_log_stream,
                )
    if isinstance(ffmpeg_log_stream, TextIOWrapper):
        ffmpeg_log_stream.close()

    if not dry_run:
        if (
            os.path.exists(tmp_timelapse_filepath)
            and os.path.getsize(tmp_timelapse_filepath) > 0
        ):
            logger.info(f"Moving {tmp_timelapse_filepath} to {timelapse_filepath}")
            shutil.move(tmp_timelapse_filepath, timelapse_filepath)

    if os.path.exists(timelapse_filepath) and os.path.getsize(timelapse_filepath) > 0:
        _update_latest_timelapse_reference(dir, timelapse_filepath)
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
        with open(timelapse_queue_file, "r") as f:
            lines = f.readlines()
            metric_timelapse_queue_size.set(len(lines))
            backlog_length = len(lines)
            if backlog_length > 0:
                logging.info(f"Timelapse backlog size: {len(lines)}")


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
