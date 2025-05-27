import os
import re
import glob
from typing import Tuple
from typing import List
from PIL import Image


from datetime import datetime
from datetime import timedelta
from absl import app
from absl import flags
from absl import logging

import cv2
import numpy as np
import calendar

# --- Configuration ---
# TODO: Set this to the base directory containing all individual camera subdirectories
ALL_CAMERAS_BASE_DIR = "data/photos"

# TODO: Set this to the path of your YAML configuration file
CONFIG_FILE_PATH = "config.yaml" # Assumes config.yaml is in the same dir as the script or ALL_CAMERAS_BASE_DIR

DEFAULT_SKY_COLOR = (10, 10, 20)  # Dark blue-grey for missing minutes or errors
DAILY_BAND_HEIGHT = 1440  # 24 hours * 60 minutes


def get_average_color_of_area(
    image: np.ndarray, area: Tuple[int, int, int, int]
) -> np.ndarray:
    """Gets the average color of an area of a picture.

    Args:
      image: A numpy array representing the image.
      area: A tuple of (x, y, width, height) representing the area of the image to
        get the average color of.

    Returns:
      A numpy array representing the average color of the area.
    """

    x, y, width, height = area
    average_color = np.mean(image[y : y + height, x : x + width], axis=(0, 1))
    return average_color.astype(np.uint8)  # Ensure uint8 for image data


def apply_average_color_to_monthly_directory(directory: str, area: Tuple[int]):
    """Applies the average color of an area of a picture to a monthly directory
    containing many pictures.

    Args:
      directory: The path to the monthly directory containing the pictures.
      area: A tuple of (x, y, width, height) representing the area of the image to
        get the average color of.
    """

    average_colors = {}
    for filename in os.listdir(directory):
        if filename.split(".")[-1] != "jpg":
            continue
        minute = get_minute_of_day_from_filename(filename)
        if minute in average_colors:
            continue
        image = cv2.imread(os.path.join(directory, filename))
        average_colors[minute] = get_average_color_of_area(image, area)

    # Stack the average colors in a vertical picture of 1 by 1440 pixels,
    # representing the average color of the area for every minute of the day.
    average_color_image = np.zeros((1440, 1, 3), dtype=np.uint8)
    last_color = [0, 0, 0]
    for i in range(1440):
        if i in average_colors:
            last_color = average_colors[i]
        average_color_image[i, 0] = last_color

    # Save the average color image.
    cv2.imwrite(os.path.join(directory, "daylight.png"), average_color_image)


def get_minute_of_day_from_filename(filename: str) -> int:
    """Returns the minute of the day (0-1439) from a filename with format %Y-%m-%dT%H-%M-%S%Z.jpg.

    Raises:
        ValueError: If the filename doesn't match the expected format or contains invalid date/time values.
    """
    # Extract the date/time part from the filename using a regex
    match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}).*", filename)
    if not match:
        raise ValueError(
            f"Filename '{filename}' does not contain a valid datetime string."
        )

    datetime_str = match.group(1)

    try:
        dt = datetime.strptime(datetime_str, "%Y-%m-%dT%H-%M")
    except ValueError as e:
        raise ValueError(
            f"Invalid datetime string '{datetime_str}' in filename '{filename}': {e}"
        ) from e

    return dt.hour * 60 + dt.minute


def get_avg_color_of_the_area(pic_file: str, crop_zone: Tuple[int]) -> bytes:
    full_img = Image.open(pic_file, mode="r")
    if full_img.mode != "RGB":
        full_img = full_img.convert("RGB")
    cropped_img = full_img.crop(crop_zone)
    a = cropped_img.resize((1, 1), resample=Image.Resampling.BOX)
    return a.tobytes()


def create_day_band(pic_dir: str, sky_area: Tuple[int, int, int, int]) -> bool:
    """COnstruct a 1440 pixel tall, 1px wide png file with each pixel representing the average color of the sky_area for every minute of the day.

    This implies the filename format is: 2023-09-04T16-42-16PDT
    TODO(feature): Customize image naming format, or read time from metadata or use a sequence of image.
    If there are multiple files for a given minute, only the first file is taken into account.
    """
    logging.debug(f"Creating a daylight band for {pic_dir}")

    minute = 0
    # TODO(feature) Start with the previous day's last pixel
    last_pixel_rgb_bytes = b"\x00\x00\x00"  # Start with an almost black pixel
    dayband = bytearray()
    previous_pic_minute = -1

    for pic_filepath in glob.glob(os.path.join(pic_dir, "*.jpg")):
        pic_minute = get_minute_of_day_from_filename(os.path.basename(pic_filepath))
        if pic_minute is None or pic_minute == -1:
            logging.warning(
                f"Skipping {pic_filepath}. Could not reliably figure out the minute of day."
            )
            continue
        while pic_minute > minute:
            dayband += last_pixel_rgb_bytes
            logging.debug(
                f"{minute}/1439 Filling with previous data {bytes(last_pixel_rgb_bytes)}"
            )
            minute += 1
            if pic_minute >= 1440:
                logging.warning(
                    f"Skipping {pic_filepath} because pic_minute ({pic_minute}) is out of range."
                )
                continue
        if (
            previous_pic_minute == pic_minute
        ):  # Ignore pictures for a minute we've already processed
            logging.debug(
                f"Ignoring {pic_filepath} as we already have data for minute {minute}"
            )
            continue
        previous_pic_minute = minute
        last_pixel_rgb_bytes = get_avg_color_of_the_area(pic_filepath, sky_area)
        dayband += last_pixel_rgb_bytes
        logging.debug(
            f"{minute}/1439 Using {bytes(last_pixel_rgb_bytes)} from {pic_filepath}"
        )
        minute += 1

    # We ran out of pictures but not reached the end of the day yet.
    while minute < 1440:
        dayband += last_pixel_rgb_bytes
        logging.debug(
            f"{minute}/1439 Filling with previous data {bytes(last_pixel_rgb_bytes)}"
        )
        minute += 1

    logging.debug(f"Final image size: {len(dayband)} bytes (expected: {1440 * 3})")
    img = Image.frombytes(size=(1, 1440), data=bytes(dayband), mode="RGB")
    img.save(os.path.join(pic_dir, "daylight.png"))


def concatenate_daily_images_into_monthly_image(
    main_pic_dir: str, yearmonth: Tuple[int]
) -> str:
    """Concatenates daily images of 1 by 1440 pixels into one monthly image with a height of 1440 pixels and a width equal to the number of days in the month, filling with black if there are missing daily images.

    Args:
      main_pic_dir: The path to the directory containing the daily directories.
      yearmonth: Tuple for year and month as int.

    Returns:
      The path to the created png file.
    """

    # Get the number of days in the month.
    year, month = yearmonth
    number_of_days_in_month = calendar.monthrange(year, month)[1]
    # Create a numpy array to store the monthly image.
    monthly_image = None

    # Iterate over the days of the month.
    for day in range(1, number_of_days_in_month + 1):
        # Get the path to the daily image.
        month_string = f"0{month}" if month < 10 else str(month)
        day_string = f"0{day}" if day < 10 else str(day)
        daily_image_path = os.path.join(
            main_pic_dir, f"{year}-{month_string}-{day_string}", "daylight.png"
        )
        daylight_path = os.path.join(main_pic_dir, "daylight")
        if not os.path.exists(daylight_path):
            os.mkdir(daylight_path)
        monthly_image_path = os.path.join(daylight_path, f"{year}-{month_string}.png")

        # If the daily image exists, load it.
        if os.path.exists(daily_image_path):
            daily_image = cv2.imread(daily_image_path)
        else:
            # If the daily image does not exist, fill the corresponding area in the monthly image with black.
            daily_image = np.zeros((1440, 1, 3), dtype=np.uint8)

        # Open the monthly image and concatenate the daily image to it.
        if not os.path.exists(monthly_image_path):
            # Create an empty numpy array for the monthly image.
            logging.info(f"Creating {monthly_image_path}")
            monthly_image = np.zeros((4, 0, 3), dtype=np.uint8)
        else:
            monthly_image = cv2.imread(monthly_image_path)

    monthly_image = np.concatenate((monthly_image, daily_image), axis=1)
    monthly_image_rgb = cv2.cvtColor(monthly_image, cv2.COLOR_BGR2RGB)

    logging.info(f"Writing {monthly_image_path}")

    # Save the monthly image.
    cv2.imwrite(
        monthly_image_path,
        monthly_image_rgb,
    )

    return monthly_image_path


def iso_day_to_dt(d: str) -> datetime:
    return datetime(*list(map(int, d.split("-"))))


def run_end_of_day(camera_name, pic_dir, sky_area, dry_run=False):
    if sky_area is None:
        sky_area = "0,50,600,150"  # take a 600x150 rectangle starting offset by 50px to avoid any timestamp mark
    create_day_band(pic_dir, tuple(map(int, sky_area.split(","))), dry_run=dry_run)
    year, month, day = os.path.split(pic_dir)[-1].split("-")
    yearmonth = (int(year), int(month))
    return concatenate_daily_images_into_monthly_image(
        os.path.join(pic_dir, ".."), yearmonth
    )


def generate_bands_for_time_range(
    start_day: datetime,
    end_day: datetime,
    camera_dir: str,
    sky_area_str: str,
    overwrite: bool,
):
    """This is for ad-hoc generation of daybands and monthbands for a given time range.
    Args:
        start_day: The start date of the range.
        end_day: The end date of the range.
        camera_dir: The directory containing the camera pictures.
        sky_area_str: A string representing the crop area (left, upper, right lower) of the picture representing the sky.
        overwrite: Whether to overwrite existing daybands.
    """
    current_day = start_day
    created_daybands_for_yearmonths = []
    while current_day <= end_day:
        current_yearmonth = (current_day.year, current_day.month)
        pic_dir = os.path.join(camera_dir, current_day.strftime("%Y-%m-%d"))
        if not os.path.exists(pic_dir):
            logging.warning(
                f"{current_day}: Skipping non-existent directory: {pic_dir}."
            )
            current_day += timedelta(days=1)
            continue
        if (
            not os.path.exists(os.path.join(pic_dir, "daylight.png"))
            or overwrite is True
        ):
            logging.info(f"{current_day}: Creating dayband.")
            left, top, right, bottom = map(int, sky_area_str.split(","))
            logging.debug(f"Crop zone of ({left},{top}),({right},{bottom})")
            sky_area = (left, top, right, bottom)
            create_day_band(pic_dir, sky_area)
        else:
            logging.info(f"Not overwriting " + os.path.join(pic_dir, "daylight.png"))
        current_day += timedelta(days=1)
        if not current_yearmonth in created_daybands_for_yearmonths:
            created_daybands_for_yearmonths.append(current_yearmonth)
        current_yearmonth = (current_day.year, current_day.month)


def dump_html_header(title, additional_headers=""):
    """Dumps the header of an HTML page.

    Args:
      title: The title of the page.
      additional_headers: Additional headers to be included in the page head.

    Returns:
      A string containing the HTML header.
    """

    html_header = """<!DOCTYPE html>
<html>
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=0.8, user-scalable=no">
    <title>{title}</title>
    <link rel="stylesheet" href="/lib/daylight.css">
    {additional_headers}
  </head>
""".format(
        title=title, additional_headers=additional_headers
    )

    return html_header


def generate_html(camera_dir: str):
    """Generates HTML files for the daylight bands in the specified camera directory.
    Args:
        camera_dir: The directory containing the camera pictures.
    """
    yearmonth_bands_files = glob.glob(os.path.join(camera_dir, "daylight", "*.png"))

    for yearmonth_file in yearmonth_bands_files:
        yearmonth_re_matches = re.match(
            r"(\d{4}-\d{2})\.png", os.path.basename(yearmonth_file)
        )
        if not yearmonth_re_matches:
            logging.warning(
                f"Skipping {yearmonth_file} as it does not match the expected format."
            )
            continue
        yearmonth = yearmonth_re_matches.group(0)
        logging.info(f"{yearmonth}: Creating monthband.")
        generate_month_html(
            monthband_path=yearmonth_file, camera_name=os.path.basename(camera_dir)
        )
    generate_html_browser(camera_dir=camera_dir)


def generate_html_browser(camera_dir: str):
    """Generates an HTML browser for the daylight images.

    Returns:
        None
    """

    # Camera name should be the name of the directory
    camera_name = os.path.basename(camera_dir)

    # Build the list of all daylight monthly files
    daylight_monthly_bands = glob.glob(os.path.join(camera_dir, "daylight", "*.png"))
    print(f"Found {len(daylight_monthly_bands)} monthly bands in {camera_dir}")

    # Generate the HTML
    HTML_FILE = os.path.join(camera_dir, "daylight.html")
    with open(HTML_FILE, "w") as f:
        f.write(
            dump_html_header(
                title="{camera_name} daylight browser",
                additional_headers="""
            <style>
            </style>""",
            )
            + f"""
                                 
        <body>
            <div class="right">
                """
        )

        for i in range(24):
            f.write(
                f"""
                <div class="timebox{(i % 2) + 1}">{i % 12} AM</div>
                """
            )

        f.write(
            """
            </div>
            <div class="bands">
            """
        )

        for month_band in sorted(daylight_monthly_bands, reverse=True):
            month_band_nopath = os.path.basename(month_band)
            width = cv2.imread(month_band).shape[1]
            year_month = month_band_nopath.split(".")[0]
            month_pretty_name = get_month_pretty_name_html(year_month)

            f.write(
                f"""
                <div class="band">
                    <div class="band_img_and_link">
                        <a class="month_link" href="daylight/{year_month}.html">                            <img class="month_band" height="1440px" width="{width}px" src="daylight/{month_band_nopath}" alt="{month_band_nopath}">
                        </a>
                    </div>
                    <div class="month"><p>{month_pretty_name}</p></div>
                </div>
                """
            )

        f.write(
            """
            </div>
        </body>
        </html>
        """
        )


def get_month_pretty_name_html(year_month: str) -> str:
    return datetime.strptime(year_month, "%Y-%m").strftime("%b<br>%Y")


def generate_month_html(monthband_path: str, camera_name: str):
    """Generates an HTML page for the specified month.

    Stretch the month band to the whole screen and create clickable zones for each day.

    Args:
        monthband_path: The path to the month band image file.
        camera_name: The name of the camera.

    Returns:
        None
    """
    # Grab the filename without the extension
    year_month = os.path.basename(monthband_path).split(".")[0]

    # Grab the path where to generate the HTML file
    html_outfile = os.path.join(os.path.dirname(monthband_path), f"{year_month}.html")

    logging.info(f"Generating HTML page for {monthband_path} ")

    # Get the width of the month image
    width = cv2.imread(monthband_path).shape[1]

    # Write the HTML header
    with open(html_outfile, "w") as f:
        f.write(
            f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{camera_name} - {year_month}</title>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=0.8, user-scalable=no">
            <link rel="stylesheet" href="/lib/daylight.css">
        </head>
        """
        )

    # Write the body of the HTML file
    with open(html_outfile, "a") as f:
        f.write(
            f"""
        <body>
            <img src="{year_month}.png" usemap="#daylight" width="{width}" height="1440">
            <map name="daylight">
        """
        )

        # Iterate over the days in the month and generate an area tag for each day
        x = 0
        for day in range(1, width + 1):
            if day < 10:
                day = f"0{day}"

            isodate = f"{year_month}-{day}"
            dirlink = f"/photos/{camera_name}/{isodate}/"

            f.write(
                f"""
                <area shape="rect" coords="{x},0,{x + 1},1439" alt="{isodate}" href="{dirlink}">
            """
            )

            x += 1

        # Write the rest of the HTML file
        f.write(
            """
            </map>
            <script src="/lib/jquery.min.js"></script>
            <script src="/lib/jquery.rwdImageMaps.min.js"></script>
            <script>$(document).ready(function(e) { $("img[usemap]").rwdImageMaps();});</script>
        </body>
        </html>
        """
        )


def list_valid_days_directories(d: str) -> List[str]:
    """Lists all valid day directories in the given directory.

    Args:
        d: The directory to list the day directories from.

    Returns:
        A list of valid day directories in the format YYYY-MM-DD.
    """
    valid_days = []
    for subdir in os.listdir(d):
        full_dir = os.path.join(d, subdir)
        if not os.path.isdir(full_dir):
            continue
        if re.match(r"\d{4}-\d{2}-\d{2}", subdir):
            valid_days.append(subdir)
    return sorted(valid_days)


def main(argv):
    """For ad-hoc execution."""
    del argv  # Unused.
    CONFIG_FILE_PATH = (
        "config.yaml"  # Assumes config.yaml is in the same dir as the script or
    )
    # Load YAML configuration
    import yaml  # For reading YAML config

    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config_data = yaml.safe_load(f)
        if not config_data or "cameras" not in config_data:
            print(
                f"Error: 'cameras' key not found in {CONFIG_FILE_PATH} or file is empty."
            )
            return
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {CONFIG_FILE_PATH}")
        return
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration file {CONFIG_FILE_PATH}: {e}")
        return

    if len(FLAGS.camera) == 0:
        # If no cameras are specified, do all them.
        camera_names = []
        for item in os.listdir(FLAGS.dir):
            if os.path.isdir(os.path.join(FLAGS.dir, item)):
                camera_names.append(item)
    else:
        camera_names = FLAGS.camera

    logging.info(f"Processing camera directories: {camera_names}")
    for camera_name in camera_names:

        # Get sky area
        camera_config = config_data["cameras"].get(camera_name)
        if not camera_config:
            print(
                f"  No configuration found for camera '{camera_name}' in {CONFIG_FILE_PATH}. Skipping."
            )
            continue

        sky_area_str = camera_config.get("sky_area")
        if not sky_area_str:
            print(
                f"  'sky_area' not defined for camera '{camera_name}' in config. Skipping."
            )
            continue

        camera_dir = os.path.join(FLAGS.dir, camera_name)
        logging.info(f"Processing camera directory: {camera_dir}")
        if not os.path.exists(camera_dir):
            logging.error(f"Camera directory {camera_dir} does not exist.")
            return
        # Date range handling
        available_days = list_valid_days_directories(camera_dir)
        if FLAGS.html_only is False:
            if FLAGS.from_date is not None:
                start_day = iso_day_to_dt(FLAGS.from_date)
            else:
                start_day = iso_day_to_dt(available_days[0])
            if FLAGS.to_date is not None:
                end_day = iso_day_to_dt(FLAGS.to_date)
            else:
                end_day = iso_day_to_dt(available_days[-1])

            generate_bands_for_time_range(
                start_day, end_day, camera_dir, sky_area_str, FLAGS.overwrite
            )
        generate_html(camera_dir=camera_dir)


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string("dir", ALL_CAMERAS_BASE_DIR, "Directory containing all per camera directories.")
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
        None,
        "Crop area of the picture representing the sky. Eg. 0,0,1000,300 for a 1000px wide, 300px tall rectangle from the top left corner of the picture.",
    )
    flags.DEFINE_bool(
        "html_only",
        False,
        "If true, only generate the HTML files and not the daylight bands.",
    )
    flags.DEFINE_multi_string(
        "camera",
        None,
        "Name of the camera. Used to find pictures in the subdirectory of the --dir argument and to looking the sky_area in the config. If not specified, all cameras in the directory are processed.",
    )
    flags.mark_flags_as_required(["dir"])
    app.run(main)
