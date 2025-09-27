#!/usr/bin/env python3

import glob
import logging
import os
import threading
from datetime import datetime

import pytz
from absl import app, flags

from fenetre.admin_server import (
    metric_directories_archived_total,
    metric_directories_daylight_total,
    metric_directories_timelapse_total,
    metric_directories_total,
)
from fenetre.config import config_load
from fenetre.daylight import run_end_of_day
from fenetre.timelapse import create_timelapse, add_to_timelapse_queue
from .logging_utils import apply_module_levels, setup_logging

logger = logging.getLogger(__name__)


def scan_and_publish_metrics(camera_name: str, camera_dir: str, global_config: dict):
    """Scans a camera directory and publishes metrics."""
    if not os.path.isdir(camera_dir):
        return

    subdirs = [d.path for d in os.scandir(camera_dir) if d.is_dir()]
    metric_directories_total.labels(camera_name=camera_name).set(len(subdirs))

    archived_count = 0
    timelapse_count = 0
    daylight_count = 0
    for subdir in subdirs:
        if os.path.exists(os.path.join(subdir, "archived")):
            archived_count += 1
        if check_dir_has_timelapse(subdir):
            timelapse_count += 1
        if check_dir_has_daylight_band(subdir):
            daylight_count += 1

    metric_directories_archived_total.labels(camera_name=camera_name).set(
        archived_count
    )
    metric_directories_timelapse_total.labels(camera_name=camera_name).set(
        timelapse_count
    )
    metric_directories_daylight_total.labels(camera_name=camera_name).set(
        daylight_count
    )


def keep_only_a_subset_of_jpeg_files(
    directory: str, dry_run=True, image_ext="jpg", files_to_keep=48
):
    """Keeps only 48 of the jpeg files in a directory, distributed equally across all the existing files.

    Args:
      directory: The directory to keep the jpeg files.
    """

    jpeg_files = glob.glob(os.path.join(directory, f"*.{image_ext}"))

    # Sort the jpeg files by their creation time.
    jpeg_files.sort(key=os.path.getctime)

    num_jpeg_files = len(jpeg_files)
    keep_interval = int(num_jpeg_files / files_to_keep)

    if keep_interval == 0:
        logger.warning(
            f"{directory} has only {num_jpeg_files} out of {files_to_keep} pictures to keep. Nothing to do there. Perhaps this is an incomplete day?"
        )
        return
    delete_count = 0
    for i in range(num_jpeg_files):
        if i % keep_interval == 0:
            logger.debug(f"Keeping {jpeg_files[i]}")
            continue
        logger.debug(f"Deleting {jpeg_files[i]}")
        if dry_run:
            continue
        os.remove(jpeg_files[i])
        delete_count += 1
    logger.info(f"Deleted {delete_count}/{num_jpeg_files} files in {directory}.")
    archive_filepath = os.path.join(directory, "archived")
    if dry_run:
        return
    open(archive_filepath, "w").close()
    logger.info(f"Writing archived file: {archive_filepath}")


def list_unarchived_dirs(camera_dir, archived_marker_file="archived"):
    res = []
    # Iterate over all the subdirectories.
    for entry in os.scandir(camera_dir):
        if not entry.is_dir():
            continue

        subdirectory = entry.name
        # Check if the subdirectory is formatted with the name $year-$month-$day.
        try:
            datetime.strptime(subdirectory, "%Y-%m-%d")
        except ValueError:
            continue

        daydir = entry.path
        if os.path.isfile(os.path.join(daydir, archived_marker_file)):
            photos_count = len(glob.glob(os.path.join(daydir, "*.jpg")))
            if photos_count > 95:  # 48 * 2 - 1
                logger.warning(
                    f"{daydir} is archived but has {photos_count} photos. "
                    "This is unexpected, please check the directory."
                )
            logger.debug(f"{daydir} is already archived.")
            continue
        res.append(daydir)
    return res


def check_dir_has_timelapse(daydir):
    subdirectory = os.path.basename(daydir)
    for timelapse_video_ext in ["mp4", "webm"]:
        timelapse_filepath = os.path.join(
            daydir, f"{subdirectory}.{timelapse_video_ext}"
        )
        if os.path.isfile(timelapse_filepath):
            if os.path.getsize(timelapse_filepath) > 1024 * 1024:
                return True
    return False


def check_dir_has_daylight_band(daydir):
    return os.path.isfile(os.path.join(daydir, "daylight.png"))


def get_today_date(global_config: dict) -> str:
    tz = pytz.timezone(global_config["timezone"])
    dt = datetime.now(tz)
    return dt.strftime("%Y-%m-%d")


def is_dir_older_than_n_days(daydir, n_days=3):
    dir_date = datetime.strptime(os.path.basename(daydir), "%Y-%m-%d")
    return (datetime.now() - dir_date).days > n_days


def archive_daydir(
    daydir: str,
    global_config: dict,
    cam: str,
    sky_area: tuple,
    dry_run: bool = True,
    create_daylight_bands: bool = False,
    daylight_bands_queue_file: str = None,
    daylight_bands_queue_file_lock: threading.Lock = None,
    create_timelapses: bool = False,
    timelapse_queue_file: str = None,
    timelapse_queue_file_lock: threading.Lock = None,
):
    """When this is called from fenetre main runner, we don't want to create timelapses diretly but add them to a queue instead."""
    today_date = get_today_date(global_config)
    if os.path.basename(daydir) == today_date:
        logger.debug(
            f"Not archiving {daydir} as it's today and may still be in progress"
        )
        return False

    if not is_dir_older_than_n_days(daydir):
        # TODO(P3): Make the daydir customizable
        logger.debug(f"Skipping {daydir} as it is not old enough")
        return False

    if not check_dir_has_daylight_band(daydir):
        if create_daylight_bands:
            logger.info(f"Creating daylight band for {daydir}")
            if not dry_run:
                run_end_of_day(cam, daydir, sky_area)

        logger.warning(
            f"{daydir} does not contain a daylight file. We are not archiving this."
        )
        return False

    # Check if the subdirectory contains a file name daylight.png and a file named $year-$month-$day.webm.
    if not check_dir_has_timelapse(daydir):
        if create_timelapses:
            if not timelapse_queue_file:
                logger.info(f"Creating timelapse for {daydir}")
                create_timelapse(
                    dir=daydir,
                    overwrite=True,
                    log_dir=global_config.get("log_dir"),
                    two_pass=timelapse_config.get("ffmpeg_2pass", False),
                    dry_run=dry_run,
                    ffmpeg_options=timelapse_config.get("ffmpeg_options"),
                    file_extension=timelapse_config.get("file_extension"),
                )
            else:
                add_to_timelapse_queue(
                    daydir, timelapse_queue_file, timelapse_queue_file_lock
                )
                return False
        else:
            logger.warning(f"{daydir} does not contain a timelapse file.")
            return False

    logger.info(f"Archiving {daydir}. (dry run: {dry_run})")
    # Keep only 48 of the jpeg files in the subdirectory, distributed equally across all the existing files.
    keep_only_a_subset_of_jpeg_files(daydir, dry_run=dry_run)


def main(argv):
    del argv  # Unused.

    global cameras_config, global_config, timelapse_config
    _, cameras_config, global_config, _, timelapse_config = config_load(FLAGS.config)
    global_config["pic_dir"] = os.path.join(global_config["work_dir"], "photos")

    log_dir = global_config.get("log_dir")
    setup_logging(log_dir, global_config.get("logging_level"))
    apply_module_levels(global_config.get("logging_levels", {}))

    for cam in cameras_config:
        camera_dir = os.path.join(global_config["pic_dir"], cam)
        sky_area = cameras_config[cam].get("sky_area", None)
        if sky_area is None:
            logger.warning(f"No sky area defined for cam {cam}")
        if not os.path.isdir(camera_dir):
            logger.warning(f"Could not find directory {camera_dir} for camera: {cam}.")
            continue
        for daydir in list_unarchived_dirs(camera_dir):
            archive_daydir(
                daydir,
                global_config,
                cam,
                sky_area,
                FLAGS.dry_run,
                FLAGS.create_daylight_bands,
                FLAGS.create_timelapses,
            )


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_bool("create_timelapses", False, "Create missing timelapses")
    flags.DEFINE_bool("create_daylight_bands", False, "Create missing daylight")
    flags.DEFINE_bool("dry_run", True, "Do not delete the files")
    flags.DEFINE_string("config", None, "path to YAML config file")
    flags.mark_flag_as_required("config")
    app.run(main)
