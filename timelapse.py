import os
import re
import subprocess
from typing import Dict
from typing import List

import ffmpeg
from absl import app
from absl import flags
from absl import logging


# TODO: optimize 2 pass encoding for vp9 https://developers.google.com/media/vp9/bitrate-modes

def create_timelapse(
    dir: str,
    overwrite: bool,
    ffmpeg_options: str = "",
    two_pass: bool = False,
    file_ext: str = "mp4",
    tmp_dir: str = "/dev/shm/camaredn"
) -> bool:
    if not os.path.exists(dir):
        raise FileNotFoundError(dir)
    timelapse_filename = re.search("^.*/([^/]+)/?$", dir).groups()[0] + "." + file_ext
    timelapse_filepath = os.path.join(dir, timelapse_filename)
    logging.debug(f"timelapse_filename: {timelapse_filename}")
    logging.debug(f"timelapse_filepath: {timelapse_filepath}")

    # FFMpeg will generate a ffmpeg2pass-0.log file and we need to store it somewhere
    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)
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
    if two_pass:
        ffmpeg_cmd.append("-pass")
        ffmpeg_cmd_first_pass=ffmpeg_cmd.copy()
        ffmpeg_cmd_first_pass.append("1")
        ffmpeg_cmd_first_pass.append(timelapse_filepath)
        ffmpeg_cmd.append("2")
        #ffmpeg_cmd_first_pass.extend("-an -f null /dev/null".split(" "))
        logging.info("Running FFmpeg first pass: {}".format(" ".join(ffmpeg_cmd_first_pass)))
        subprocess.run(ffmpeg_cmd_first_pass, cwd=tmp_dir)

    ffmpeg_cmd.append(timelapse_filepath)
    logging.info("Running {}".format(" ".join(ffmpeg_cmd)))
    subprocess.run(ffmpeg_cmd, cwd=tmp_dir)

    return os.path.exists(timelapse_filepath)


def main(argv):
    del argv  # Unused.
    create_timelapse(FLAGS.dir, FLAGS.overwrite, FLAGS.ffmpeg_options, FLAGS.two_pass, FLAGS.file_ext)


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string("dir", None, "directory to build a timelapse from")
    flags.DEFINE_string("file_ext", 'mp4', "video file extension")
    flags.DEFINE_bool("overwrite", False, "Overwrite existing timelapse")
    flags.DEFINE_bool("two_pass", False, "Tell ffmpeg to do 2 pass encoding. Recommended for VP9")
    flags.DEFINE_string(
        "ffmpeg_options",
        "-framerate 30",
        "Options passed directly to FFMPEG between input and output",
    )
    flags.mark_flag_as_required("dir")
    app.run(main)
