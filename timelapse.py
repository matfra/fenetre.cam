import os
import re
import subprocess
from typing import Dict
from typing import List
from PIL import Image
from PIL.ExifTags import TAGS
from datetime import datetime

import ffmpeg
from absl import app
from absl import flags
from absl import logging

from typing import Optional

def _generate_srt_file(image_dir: str, srt_filepath: str):
    image_files = sorted([f for f in os.listdir(image_dir) if f.endswith(".jpg")])
    with open(srt_filepath, "w") as srt_file:
        for i, image_file in enumerate(image_files):
            image_path = os.path.join(image_dir, image_file)
            try:
                img = Image.open(image_path)
                exif_data = img._getexif()
                if exif_data is None:
                    exif_data = {}

                exif_info = {
                    "ExposureTime": "N/A",
                    "FNumber": "N/A",
                    "ISOSpeedRatings": "N/A",
                    "FocalLength": "N/A",
                    "Model": "N/A",
                }

                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag in exif_info:
                        exif_info[tag] = value

                # Extract timestamp from filename
                timestamp_str = os.path.splitext(image_file)[0].replace("T", " ")
                dt_object = datetime.strptime(timestamp_str, "%Y-%m-%d %H-%M-%S")
                timestamp = dt_object.strftime("%Y-%m-%d %H:%M:%S")

                # SRT format
                srt_file.write(f"{i+1}\n")
                start_time = f"00:00:{i:02d},000"
                end_time = f"00:00:{i+1:02d},000"
                srt_file.write(f"{start_time} --> {end_time}\n")
                srt_file.write(f"Timestamp: {timestamp}\n")
                srt_file.write(f"Camera: {exif_info['Model']}, ")
                srt_file.write(f"Focal Length: {exif_info['FocalLength']}mm, ")
                srt_file.write(f"Aperture: f/{exif_info['FNumber']}, ")
                srt_file.write(f"Exposure: {exif_info['ExposureTime']}s, ")
                srt_file.write(f"ISO: {exif_info['ISOSpeedRatings']}\n\n")

            except Exception as e:
                logging.error(f"Error processing {image_path}: {e}")

# TODO: optimize 2 pass encoding for vp9 https://developers.google.com/media/vp9/bitrate-modes



def create_timelapse(
    dir: str,
    overwrite: bool,
    ffmpeg_options: str = "",
    two_pass: bool = False,
    file_ext: str = "mp4",
    tmp_dir: Optional[str] = "/dev/shm/fenetre",
    dry_run: bool = False,
) -> bool:
    if not os.path.exists(dir):
        raise FileNotFoundError(dir)
    timelapse_filename = re.search("^.*/([^/]+)/?$", dir).groups()[0] + "." + file_ext
    timelapse_filepath = os.path.join(dir, timelapse_filename)
    srt_filepath = os.path.join(tmp_dir, f"{timelapse_filename}.srt")
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
        "{}".format(os.path.join(os.path.abspath(dir), "*.jpg")),
    ]
    if overwrite:
        ffmpeg_cmd.append("-y")
    ffmpeg_cmd.extend(ffmpeg_options.split(" "))
    if two_pass:
        ffmpeg_cmd.append("-pass")
        ffmpeg_cmd_first_pass = ffmpeg_cmd.copy()
        ffmpeg_cmd_first_pass.append("1")
        ffmpeg_cmd_first_pass.append(os.path.abspath(timelapse_filepath))
        ffmpeg_cmd.append("2")
        # ffmpeg_cmd_first_pass.extend("-an -f null /dev/null".split(" "))
        logging.info(
            "Running ffmpeg first pass: {}".format(" ".join(ffmpeg_cmd_first_pass))
        )
        if not dry_run:
            subprocess.run(ffmpeg_cmd_first_pass, cwd=tmp_dir)

    ffmpeg_cmd.append(os.path.abspath(timelapse_filepath))
    logging.info("Running ffmpeg second pass: {}".format(" ".join(ffmpeg_cmd)))
    if not dry_run:
        subprocess.run(ffmpeg_cmd, cwd=tmp_dir)

    return os.path.exists(timelapse_filepath)


def main(argv):
    del argv  # Unused.
    create_timelapse(
        FLAGS.dir, FLAGS.overwrite, FLAGS.ffmpeg_options, FLAGS.two_pass, FLAGS.file_ext
    )


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string("dir", None, "directory to build a timelapse from")
    flags.DEFINE_string("file_ext", "mp4", "video file extension")
    flags.DEFINE_bool("overwrite", False, "Overwrite existing timelapse")
    flags.DEFINE_bool(
        "two_pass", False, "Tell ffmpeg to do 2 pass encoding. Recommended for VP9"
    )
    flags.DEFINE_string(
        "ffmpeg_options",
        "-framerate 30",
        "Options passed directly to FFMPEG between input and output",
    )
    flags.mark_flag_as_required("dir")
    app.run(main)
