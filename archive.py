import os
import re
import subprocess
from typing import Dict
from typing import List
import glob
import ffmpeg
from absl import app
from absl import flags
from absl import logging

import os
import shutil


def keep_only_a_subset_of_jpeg_files(
    directory: str, dry_run=True, image_ext="jpg", video_ext="webm", files_to_keep=48
):
    """Keeps only 48 of the jpeg files in a directory, distributed equally across all the existing files.

    Args:
      directory: The directory to keep the jpeg files.
    """

    # Get a list of all the jpeg files in the directory.
    jpeg_files = glob.glob(os.path.join(directory, f"*.{image_ext}"))

    # Sort the jpeg files by their creation time.
    jpeg_files.sort(key=os.path.getctime)

    num_jpeg_files = len(jpeg_files)
    keep_interval = int(num_jpeg_files / files_to_keep)

    for i in range(num_jpeg_files):
        if i % keep_interval == 0:
            logging.info(f"Keeping {jpeg_files[i]}")
            continue
        logging.info(f"Deleting {jpeg_files[i]}")
        if dry_run:
            continue
        os.remove(jpeg_files[i])
        archive_filepath = os.path.join(directory, "archived")
        with open(archive_filepath, "w") as f:
            logging.debug(f"Writing archived file: {archive_filepath}")
            pass


def main(argv):
    del argv  # Unused.

    camera_dir = FLAGS.camera_dir
    # Iterate over all the subdirectories.
    for subdirectory in os.listdir(camera_dir):
        # Check if the subdirectory is formatted with the name $year-$month-$day.
        if (
            len(subdirectory) == 10
            and subdirectory[0:3].isdigit()
            and subdirectory[5:6].isdigit()
            and subdirectory[8:9].isdigit()
        ):
            daydir = os.path.join(camera_dir, subdirectory)
            # Check if the subdirectory contains a file named archived.
            if os.path.isfile(os.path.join(daydir, "archived")):
                # Continue to the next subdirectory.
                continue

            # Check if the subdirectory contains a file name daylight.png and a file named $year-$month-$day.webm.
            if not os.path.isfile(
                os.path.join(daydir, "daylight.png")
            ) or not os.path.isfile(os.path.join(daydir, f"{subdirectory}.webm")):
                logging.warning(
                    f"{daydir} does not contain a timelapse or a daylight file"
                )
                # Continue to the next subdirectory.
                continue

            # Keep only 48 of the jpeg files in the subdirectory, distributed equally across all the existing files.
            keep_only_a_subset_of_jpeg_files(daydir, dry_run=FLAGS.dry_run)


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string(
        "camera_dir", None, "directory to cleanup"
    )
    flags.DEFINE_string("image_ext", "jpg", "video file extension")
    flags.DEFINE_string("video_ext", "webm", "video file extension")
    flags.DEFINE_bool("dry_run", True, "Do not delete the files")

    flags.mark_flag_as_required("camera_dir")
    app.run(main)
