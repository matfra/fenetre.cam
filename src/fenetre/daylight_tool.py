import logging
import os

import yaml
from absl import app, flags

from fenetre import daylight

logger = logging.getLogger(__name__)

# Assumes config.yaml is in the same dir as the script
CONFIG_FILE_PATH = "config.yaml"


def main(argv):
    """For ad-hoc execution."""
    del argv  # Unused.

    # Load YAML configuration
    try:
        with open(FLAGS.config_file, "r") as f:
            config_data = yaml.safe_load(f)
        if not config_data or "cameras" not in config_data:
            print(
                f"Error: 'cameras' key not found in {FLAGS.config_file} or file is empty."
            )
            return
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {FLAGS.config_file}")
        return
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration file {FLAGS.config_file}: {e}")
        return

    work_dir = config_data.get("global", {}).get("work_dir")
    if not work_dir:
        logger.error("work_dir not found in config file")
        return

    base_dir_for_cameras = os.path.join(work_dir, "photos")

    if not FLAGS.camera:  # Check if FLAGS.camera is empty list or None
        camera_names = []
        if os.path.exists(base_dir_for_cameras):
            for item in os.listdir(base_dir_for_cameras):
                if os.path.isdir(os.path.join(base_dir_for_cameras, item)):
                    camera_names.append(item)
        if not camera_names:
            logger.warning(
                f"No camera subdirectories found in {base_dir_for_cameras}. Exiting."
            )
            return
    else:
        camera_names = FLAGS.camera

    logger.info(f"Processing camera directories: {camera_names}")
    for camera_name in camera_names:
        camera_config = config_data["cameras"].get(camera_name)
        if not camera_config:
            print(
                f"  No configuration found for camera '{camera_name}' in {FLAGS.config_file}. Skipping."
            )
            continue

        sky_area_str_from_config = camera_config.get(
            "sky_area"
        )  # Renamed to avoid conflict with flag

        # Prioritize flag sky_area if provided, otherwise use config
        sky_area_to_use = FLAGS.sky_area if FLAGS.sky_area else sky_area_str_from_config

        if not sky_area_to_use:
            print(
                f"  'sky_area' not defined for camera '{camera_name}' in config or via flag. Skipping."
            )
            continue

        camera_dir = os.path.join(base_dir_for_cameras, camera_name)
        logger.info(f"Processing camera directory: {camera_dir}")

        if not os.path.exists(camera_dir):
            logger.error(
                f"Camera directory {camera_dir} does not exist. Skipping camera."
            )
            continue

        available_days = daylight.list_valid_days_directories(camera_dir)
        if (
            not available_days and not FLAGS.html_only
        ):  # If no days and not just doing HTML, nothing to process
            logger.warning(
                f"No valid day directories found in {camera_dir}. Skipping band generation."
            )
            # Still generate HTML if requested, as it might show empty state or rely on pre-existing files
            if FLAGS.html_only:
                daylight.generate_html(camera_dir=camera_dir)
            continue

        if not FLAGS.html_only:
            if FLAGS.from_date:
                try:
                    start_day = daylight.iso_day_to_dt(FLAGS.from_date)
                except ValueError:
                    logger.error(
                        f"Invalid from_date format: {FLAGS.from_date}. Expected YYYY-MM-DD."
                    )
                    return
            elif available_days:  # Only if available_days is not empty
                start_day = daylight.iso_day_to_dt(available_days[0])
            else:  # No available days and no from_date specified
                logger.warning(
                    f"No start date specified and no data found for camera {camera_name}. Skipping band generation."
                )
                if (
                    FLAGS.html_only
                ):  # Fall through to generate HTML if that's all that's asked
                    daylight.generate_html(camera_dir=camera_dir)
                continue

            if FLAGS.to_date:
                try:
                    end_day = daylight.iso_day_to_dt(FLAGS.to_date)
                except ValueError:
                    logger.error(
                        f"Invalid to_date format: {FLAGS.to_date}. Expected YYYY-MM-DD."
                    )
                    return
            elif available_days:  # Only if available_days is not empty
                end_day = daylight.iso_day_to_dt(available_days[-1])
            else:  # No available days and no to_date specified
                logger.warning(
                    f"No end date specified and no data found for camera {camera_name}. Skipping band generation."
                )
                if FLAGS.html_only:
                    daylight.generate_html(camera_dir=camera_dir)
                continue

            if start_day > end_day:
                logger.error(
                    f"Start date {start_day.strftime('%Y-%m-%d')} is after end date {end_day.strftime('%Y-%m-%d')}. Skipping."
                )
                continue

            # Cheap integration test for run_end_of_day (only if a single specific day is processed)
            # This logic seems a bit off if generate_bands_for_time_range is the main processor.
            # Consider if run_end_of_day is still needed here or if its logic is covered by generate_bands_for_time_range.
            # For now, keeping it as per original logic but it might be redundant if range includes single day.
            if FLAGS.from_date and FLAGS.to_date and FLAGS.from_date == FLAGS.to_date:
                day_dir_path = os.path.join(camera_dir, start_day.strftime("%Y-%m-%d"))
                if os.path.exists(
                    day_dir_path
                ):  # Check if the specific day directory exists
                    logger.info(
                        f"Running end of day for single specified day: {start_day.strftime('%Y-%m-%d')}"
                    )
                    daylight.run_end_of_day(  # This will create daily and then monthly for that day's month.
                        camera_name,
                        day_dir_path,
                        sky_area_to_use,  # Use the determined sky_area
                    )
                else:
                    logger.warning(
                        f"Directory for single specified day {day_dir_path} does not exist. Skipping run_end_of_day."
                    )
            # Always run generate_bands_for_time_range if not html_only
            # This will create daily bands and then call create_monthly_image for each relevant month.
            daylight.generate_bands_for_time_range(
                start_day, end_day, camera_dir, sky_area_to_use, FLAGS.overwrite
            )

        # Always generate HTML after processing bands or if html_only
        daylight.generate_html(camera_dir=camera_dir)


def run():
    """Entry point for the daylight tool."""
    app.run(main)


FLAGS = flags.FLAGS

flags.DEFINE_string(
    "from_date",
    None,
    "Start date for the range in YYYY-MM-DD format. If not specified, the script will look for the earliest pictures available.",
)
flags.DEFINE_string(
    "to_date",
    None,
    "End date for the range in YYYY-MM-DD format. If not specified, the script will look for the latest pictures available.",
)
flags.DEFINE_bool(
    "overwrite",
    False,
    "Overwrite existing daylight bands. Default to False which skips days with existing bands.",
)
flags.DEFINE_string(
    "sky_area",
    None,  # Default to None, so config is used if this isn't set
    "Crop area of the picture representing the sky. Eg. 0,0,1000,300. Overrides config if set.",
)
flags.DEFINE_bool(
    "html_only",
    False,
    "If true, only generate the HTML files and not the daylight bands.",
)
flags.DEFINE_multi_string(  # 'camera' can be specified multiple times
    "camera",
    [],  # Default to empty list
    "Name of the camera. Used to find pictures in the subdirectory of the --dir argument and to looking the sky_area in the config. If not specified, all cameras in the directory are processed.",
)
# It's good practice to also define a flag for the config file path if it's not hardcoded
flags.DEFINE_string(
    "config_file", CONFIG_FILE_PATH, "Path to the YAML configuration file."
)


if __name__ == "__main__":
    run()
