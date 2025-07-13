#!/usr/bin/env python3

import os
import glob
import pytz
import time
from datetime import datetime
from absl import app
from absl import flags
from absl import logging

from daylight import run_end_of_day
from timelapse import create_timelapse

import os


# TODO:
# - Make an archival loop instead of relying one external crontab
# for d in $(ls -1 /srv/fenetre/data/photos/) ; do /srv/fenetre/venv/bin/python /srv/fenetre/archive.py --camera_dir=/srv/fenetre/data/photos/$d --dry_run=False ; done
# - mark for archiving and only archive after N days
# - If missing timelapses and daylight are found, offer to add the in the queue
# - Make the queue for daylight and timelapse a file on the FS (use async read/write if necessary?)
from config import config_load


def keep_only_a_subset_of_jpeg_files(
    directory: str, dry_run=True, image_ext="jpg", files_to_keep=48
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

    if keep_interval == 0:
        logging.warning(
            f"{directory} has only {num_jpeg_files} out of {files_to_keep} pictures to keep. Nothing to do there. Perhaps this is an incomplete day?"
        )
        return
    delete_count = 0
    for i in range(num_jpeg_files):
        if i % keep_interval == 0:
            logging.debug(f"Keeping {jpeg_files[i]}")
            continue
        logging.debug(f"Deleting {jpeg_files[i]}")
        if dry_run:
            continue
        os.remove(jpeg_files[i])
        delete_count += 1
    logging.info(f"Deleted {delete_count}/{num_jpeg_files} files in {directory}.")
    archive_filepath = os.path.join(directory, "archived")
    if dry_run:
        return
    with open(archive_filepath, "w") as f:
        logging.info(f"Writing archived file: {archive_filepath}")
        pass


def list_unarchived_dirs(camera_dir, archived_marker_file="archived"):
    res = []
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
            # Count the number of jpg files in the subdirectory.
            photos_count = len(glob.glob(os.path.join(daydir, "*.jpg")))
            # Check if the subdirectory contains a file named archived.
            if os.path.isfile(os.path.join(daydir, archived_marker_file)):
                if photos_count > 48:
                    logging.warning(
                        f"{daydir} is archived but has {photos_count} photos. "
                        "This is unexpected, please check the directory."
                    )
                else:
                    logging.debug(f"{daydir} is already archived.")
                    # Continue to the next subdirectory.
                    continue
            res.append(daydir)
    return res


def check_dir_has_timelapse(daydir, timelapse_video_ext="mp4"):
    subdirectory = os.path.basename(daydir)
    timelapse_filepath = os.path.join(daydir, f"{subdirectory}.{timelapse_video_ext}")
    if not os.path.isfile(timelapse_filepath):
        return False
    if os.path.getsize(timelapse_filepath) > 1024 * 1024:
        return True
    return False


def check_dir_has_daylight_band(daydir):
    return os.path.isfile(os.path.join(daydir, "daylight.png"))


def get_today_date() -> str:
    tz = pytz.timezone(global_config["timezone"])
    dt = datetime.now(tz)
    return dt.strftime("%Y-%m-%d")


def is_dir_older_than_n_days(daydir, n_days=3):
    dir_date = datetime.strptime(os.path.basename(daydir), "%Y-%m-%d")
    return (datetime.now() - dir_date).days > n_days


def archive_daydir(daydir: str, dry_run: bool = True, create_daylight_bands: bool = False, create_timelapses: bool = False):
    today_date = get_today_date()
    if os.path.basename(daydir) == today_date:
        logging.info(
            f"Not archiving {daydir} as it's today and may still be in progress"
        )
        return False

    if not is_dir_older_than_n_days(daydir):
        # TODO(P3): Make the daydir customizable
        logging.info(f"Skipping {daydir} as it is not old enough")
        return False


    if not check_dir_has_daylight_band(daydir):
        if create_daylight_bands:
            logging.info(f"Creating daylight band for {daydir}")
            if not dry_run:
                run_end_of_day(cam, daydir, sky_area)

        logging.warning(f"{daydir} does not contain a daylight file. We are not archiving this.")
        return False

    # Check if the subdirectory contains a file name daylight.png and a file named $year-$month-$day.webm.
    if not check_dir_has_timelapse(
        daydir, global_config.get("timelapse_file_extension", "mp4")
    ):
        if create_timelapses:
            logging.info(f"Creating timelapse for {daydir}")
            create_timelapse(
                dir=daydir,
                overwrite=True,
                ffmpeg_options=global_config.get(
                    "ffmpeg_options", "-framerate 30"
                ),
                two_pass=global_config.get("ffmpeg_2pass", False),
                file_ext=global_config.get("timelapse_file_extension", "mp4"),
                dry_run=dry_run,
            )
        else:
            logging.warning(f"{daydir} does not contain a timelapse file.")
            return False

    logging.info(f"Archiving {daydir}. (dry run: {dry_run})")
    # Keep only 48 of the jpeg files in the subdirectory, distributed equally across all the existing files.
    keep_only_a_subset_of_jpeg_files(daydir, dry_run=dry_run)


def main(argv):
    del argv  # Unused.

    # TODO: Are global variable really necessary?
    global server_config, cameras_config, global_config
    server_config, cameras_config, global_config = config_load(FLAGS.config)
    global_config["pic_dir"] = os.path.join(global_config["work_dir"], "photos")
    for cam in cameras_config:
        camera_dir = os.path.join(global_config["pic_dir"], cam)
        sky_area = cameras_config[cam].get("sky_area", None)
        if sky_area is None:
            logging.warning(f"No sky area defined for cam {cam}")
        if not os.path.isdir(camera_dir):
            logging.warning(f"Could not find directory {camera_dir} for camera: {cam}.")
            continue
        for daydir in list_unarchived_dirs(camera_dir):
            archive_daydir(daydir, FLAGS.dry_run, FLAGS.create_daylight_bands, FLAGS.create_timelapses)

if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_bool("create_timelapses", False, "Create missing timelapses")
    flags.DEFINE_bool("create_daylight_bands", False, "Create missing daylight")
    flags.DEFINE_bool("dry_run", True, "Do not delete the files")
    flags.DEFINE_string("config", None, "path to YAML config file")
    flags.mark_flag_as_required("config")
    app.run(main)
