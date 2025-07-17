import os
import re
import subprocess
from typing import Optional

from absl import app, flags, logging

def is_raspberry_pi():
    """Checks if the current platform is a Raspberry Pi."""
    try:
        with open('/proc/device-tree/model', 'r') as f:
            if 'raspberry pi' in f.read().lower():
                return True
    except FileNotFoundError:
        pass
    return False

def create_timelapse(
    dir: str,
    overwrite: bool,
    two_pass: bool = False,
    tmp_dir: Optional[str] = "/dev/shm/fenetre",
    dry_run: bool = False,
) -> bool:
    if not os.path.exists(dir):
        raise FileNotFoundError(dir)

    if is_raspberry_pi():
        ffmpeg_options = "-c:v h264_v4l2m2m -b:v 10M"
        file_ext = "mp4"
    else:
        ffmpeg_options = "-c:v libvpx-vp9 -b:v 0 -crf 30"
        file_ext = "webm"

    timelapse_filename = os.path.basename(dir) + "." + file_ext
    timelapse_filepath = os.path.join(dir, timelapse_filename)
    logging.debug(f"timelapse_filename: {timelapse_filename}")
    logging.debug(f"timelapse_filepath: {timelapse_filepath}")

    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir, exist_ok=True)
    if os.path.exists(timelapse_filepath) and not overwrite:
        raise FileExistsError(timelapse_filepath)

    ffmpeg_cmd = [
        "nice",
        "-n10",
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-pattern_type",
        "glob",
        "-i",
        os.path.join(os.path.abspath(dir), "*.jpg"),
        "-pix_fmt", "yuv420p",
        "-framerate", "60",
        "-vf", "scale=1920:-2,format=yuv420p",
    ]
    if overwrite:
        ffmpeg_cmd.append("-y")
    ffmpeg_cmd.extend(ffmpeg_options.split(" "))

    if two_pass:
        first_pass_cmd = ffmpeg_cmd + ["-pass", "1", "-an", "-f", "null", "/dev/null"]
        logging.info(f"Running ffmpeg first pass: {' '.join(first_pass_cmd)}")
        if not dry_run:
            subprocess.run(first_pass_cmd, cwd=tmp_dir, check=True)
        
        second_pass_cmd = ffmpeg_cmd + ["-pass", "2", os.path.abspath(timelapse_filepath)]
        logging.info(f"Running ffmpeg second pass: {' '.join(second_pass_cmd)}")
        if not dry_run:
            subprocess.run(second_pass_cmd, cwd=tmp_dir, check=True)
    else:
        final_cmd = ffmpeg_cmd + [os.path.abspath(timelapse_filepath)]
        logging.info(f"Running ffmpeg: {' '.join(final_cmd)}")
        if not dry_run:
            subprocess.run(final_cmd, cwd=tmp_dir, check=True)

    return os.path.exists(timelapse_filepath)


def main(argv):
    del argv  # Unused.
    create_timelapse(
        FLAGS.dir, FLAGS.overwrite, FLAGS.two_pass
    )


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string("dir", None, "directory to build a timelapse from")
    flags.DEFINE_bool("overwrite", False, "Overwrite existing timelapse")
    flags.DEFINE_bool(
        "two_pass", False, "Tell ffmpeg to do 2 pass encoding. Recommended for VP9"
    )
    flags.mark_flag_as_required("dir")
    app.run(main)
