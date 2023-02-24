import ffmpeg
import os

import subprocess
import re
import butterflow

from absl import app
from absl import flags
from absl import logging
from typing import Dict, List


FLAGS = flags.FLAGS

flags.DEFINE_string("dir", None, "directory to build a timelapse from")
flags.DEFINE_bool("overwrite", False, "Overwrite existing timelapse")
flags.mark_flag_as_required("dir")


def create_timelapse(dir: str, overwrite: bool = False) -> bool:
    if not os.path.exists(dir):
        raise FileNotFoundError(dir)
    timelapse_filename = re.search("^.*/([^/]+)/?$", dir).groups()[0] + ".mp4"
    timelapse_filepath = os.path.join(dir, timelapse_filename)
    logging.debug(f"timelapse_filename: {timelapse_filename}")
    logging.debug(f"timelapse_filepath: {timelapse_filepath}")

    if os.path.exists(timelapse_filepath) and overwrite is False:
        raise FileExistsError(timelapse_filepath)
    ffmpeg_cmd = ["nice", "-n10", "/usr/bin/ffmpeg"]
    if overwrite:
        ffmpeg_cmd.append("-y")
    ffmpeg_cmd.extend(
        [
            "-pattern_type",
            "glob",
            "-i",
            os.path.join(dir, "*.jpg"),
            "-framerate",
            "30",
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "placebo",
            "-s",
            "1920x1080",
            timelapse_filepath,
        ]
    )
    subprocess.run(ffmpeg_cmd)

    return os.path.exists(timelapse_filepath)


def main(argv):
    del argv  # Unused.
    create_timelapse(FLAGS.dir, FLAGS.overwrite)


if __name__ == "__main__":
    app.run(main)
