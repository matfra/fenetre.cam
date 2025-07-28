import glob
import json
import os
import subprocess
from typing import Optional

from datetime import datetime
from absl import app, flags, logging
from PIL import Image

from fenetre.platform_utils import is_raspberry_pi, rotate_log_file
from io import TextIOWrapper


def get_image_dimensions(image_path: str):
    """Gets the dimensions of an image."""
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        logging.error(f"Error getting dimensions for {image_path}: {e}")
        return None


def create_timelapse(
    dir: str,
    overwrite: bool,
    two_pass: Optional[bool] = False,
    log_dir: Optional[str] = None,
    tmp_dir: Optional[str] = "/dev/shm/fenetre",
    dry_run: bool = False,
    ffmpeg_options: str = None,
    file_extension: str = "mp4",
) -> bool:
    if not os.path.exists(dir):
        raise FileNotFoundError(dir)

    image_files = glob.glob(os.path.join(dir, "*.jpg"))
    images_count = len(image_files)
    if images_count == 0:
        logging.error(f"No jpg images found in {dir}.")
        print("Nothing found")
        return False

    # Delete 0-byte images
    for image_path in image_files:
        if os.path.getsize(image_path) == 0:
            logging.warning(f"Deleting 0-byte image: {image_path}")
            os.remove(image_path)
            images_count -= 1

    if images_count < 1:
        logging.error(
            f"No valid jpg images found in {dir} after removing 0-byte files."
        )
        return False

    width, height = get_image_dimensions(image_files[0])

    if is_raspberry_pi():
        default_encoder_options = "-c:v h264_v4l2m2m -b:v 5M"
        max_width = 1920
        max_height = 1080
        framerate = 30
        two_pass = False  # multi pass encoding not supported with hardware encoder
    else:
        default_encoder_options = "-c:v libvpx-vp9 -b:v 0 -crf 30"
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

    timelapse_filename = os.path.basename(dir) + "." + file_extension
    timelapse_filepath = os.path.join(dir, timelapse_filename)

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        ffmpeg_log_filepath = os.path.join(log_dir, "ffmpeg.log")
        rotate_log_file(ffmpeg_log_filepath)
        ffmpeg_log_stream = open(ffmpeg_log_filepath, "a")
        logging.info(f"FFmpeg log file: {ffmpeg_log_filepath}")
    else:
        logging.info(f"No log_dir defined in configs. ffmpeg logs will be shown here")
        ffmpeg_log_stream = None

    logging.debug(f"timelapse_filepath: {timelapse_filepath}")

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
        logging.info(f"Running ffmpeg first pass: {' '.join(first_pass_cmd)}")
        if not dry_run:
            subprocess.run(
                first_pass_cmd,
                cwd=tmp_dir,
                check=True,
                stdout=ffmpeg_log_stream,
                stderr=ffmpeg_log_stream,
            )

            second_pass_cmd = ffmpeg_cmd + [
                "-pass",
                "2",
                os.path.abspath(timelapse_filepath),
            ]
            logging.info(f"Running ffmpeg second pass: {' '.join(second_pass_cmd)}")
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
        logging.info(f"Running ffmpeg: {' '.join(final_cmd)}")
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

    if os.path.exists(timelapse_filepath):
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


def main(argv):
    del argv  # Unused.
    create_timelapse(FLAGS.dir, FLAGS.overwrite, FLAGS.two_pass, FLAGS.log_dir)


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string("dir", None, "directory to build a timelapse from")
    flags.DEFINE_string("log_dir", None, "directory to store logs")
    flags.DEFINE_bool("overwrite", False, "Overwrite existing timelapse")
    flags.DEFINE_bool(
        "two_pass", False, "Tell ffmpeg to do 2 pass encoding. Recommended for VP9"
    )
    flags.mark_flag_as_required("dir")
    app.run(main)
