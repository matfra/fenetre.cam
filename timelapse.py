import ffmpeg
import os

import subprocess
import re

from absl import app
from absl import flags
from absl import logging
from typing import Dict, List


def create_timelapse(
    dir: str,
    overwrite: bool,
    ffmpeg_options: str = "",
    tmp_dir: str = "/dev/shm/camaredn",
) -> bool:
    if not os.path.exists(dir):
        raise FileNotFoundError(dir)
    timelapse_filename = re.search("^.*/([^/]+)/?$", dir).groups()[0] + ".mp4"
    timelapse_filepath = os.path.join(dir, timelapse_filename)
    logging.debug(f"timelapse_filename: {timelapse_filename}")
    logging.debug(f"timelapse_filepath: {timelapse_filepath}")

    if os.path.exists(timelapse_filepath) and overwrite is False:
        raise FileExistsError(timelapse_filepath)
    ffmpeg_cmd = [
        "nice",
        "-n10",
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-pattern_type",
        "glob",
        "-i",
        '{}'.format(os.path.join(dir, "*.jpg")),
    ]
    if overwrite:
        ffmpeg_cmd.append("-y")
    ffmpeg_cmd.extend(ffmpeg_options.split(" "))
    ffmpeg_cmd.append(timelapse_filepath)
    logging.info("Running {}".format(" ".join(ffmpeg_cmd)))
    subprocess.run(ffmpeg_cmd)

    return os.path.exists(timelapse_filepath)


def main(argv):
    del argv  # Unused.
    create_timelapse(FLAGS.dir, FLAGS.overwrite, FLAGS.ffmpeg_options)


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string("dir", None, "directory to build a timelapse from")
    flags.DEFINE_bool("overwrite", False, "Overwrite existing timelapse")
    flags.DEFINE_string(
        "ffmpeg_options",
        "-framerate 30",
        "Options passed directly to FFMPEG between input and output",
    )
    flags.mark_flag_as_required("dir")
    app.run(main)
