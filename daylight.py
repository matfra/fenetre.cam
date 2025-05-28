import os
import re
import glob
from typing import Tuple
from typing import List
from PIL import Image
from collections import defaultdict
from PIL import ImageDraw

from datetime import datetime
from datetime import timedelta
from absl import app
from absl import flags
from absl import logging

import cv2 # Keep for generate_month_html, or remove if not used elsewhere by this function
import numpy as np
import calendar # Added for getting days in month
from zoneinfo import ZoneInfo  # Python 3.9+


# --- Configuration ---
# TODO: Set this to the base directory containing all individual camera subdirectories
ALL_CAMERAS_BASE_DIR = "data/photos"

# TODO: Set this to the path of your YAML configuration file
CONFIG_FILE_PATH = "config.yaml"  # Assumes config.yaml is in the same dir as the script or ALL_CAMERAS_BASE_DIR

DEFAULT_SKY_COLOR = (10, 10, 20)  # Dark blue-grey for missing minutes or errors
DEFAULT_SKY_AREA = (0, 50, 600, 150)  # Default crop area for the sky in the pictures
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


def get_avg_color_of_the_area(pic_file: str, crop_zone: Tuple[int]) -> bytes:
    full_img = Image.open(pic_file, mode="r")
    if full_img.mode != "RGB":
        full_img = full_img.convert("RGB")
    cropped_img = full_img.crop(crop_zone)
    a = cropped_img.resize((1, 1), resample=Image.Resampling.BOX)
    return a.tobytes()


def iso_day_to_dt(d: str) -> datetime:
    return datetime(*list(map(int, d.split("-"))))


def run_end_of_day(camera_name, day_dir_path, sky_area, dry_run=False):
    """Runs the end of day processing for a given camera and day directory. Typically it creates the daily band and updates the monthly image, regenerate all HTML files."""
    if sky_area is None:
        sky_area = DEFAULT_SKY_AREA
    create_daily_band(day_dir_path, parse_sky_area(sky_area))
    year, month, day = os.path.split(day_dir_path)[-1].split("-")
    yearmonth = (int(year), int(month))
    create_monthly_image(f"{year}-{month}", os.path.join(day_dir_path, ".."))
    generate_html(camera_dir=os.path.join(day_dir_path, ".."))



def get_avg_color(image, crop_box):
    """Crops image to crop_box and returns average RGB color."""
    try:
        sky_region = image.crop(crop_box)
        avg_color_tuple = np.array(sky_region).mean(axis=(0, 1))
        return tuple(int(c) for c in avg_color_tuple)
    except Exception as e:
        print(f"      Error getting average color: {e}")
        return DEFAULT_SKY_COLOR


def create_daily_band(day_dir_path, sky_coords):
    """
    Processes images in a daily directory to create a 1x1440 pixel band.
    If no image for a minute, repeats the previous minute's color.
    Saves it as 'daylight.png' in day_dir_path.
    Returns the path to the saved band or None if failed.
    """
    minute_colors_accumulator = defaultdict(list)

    image_files = sorted(
        [f for f in os.listdir(day_dir_path) if f.lower().endswith(".jpg")]
    )

    if not image_files:
        print(f"      No JPG images found in {day_dir_path}.")
        # Create a band with default color if no images
        daily_band_image = Image.new("RGB", (1, DAILY_BAND_HEIGHT), DEFAULT_SKY_COLOR)
        # Fill with default color (no "previous color" logic needed for an empty day)
        band_save_path = os.path.join(day_dir_path, "daylight.png")
        try:
            daily_band_image.save(band_save_path)
            print(f"      Saved empty daily band (no images) to {band_save_path}")
            return band_save_path
        except Exception as e:
            print(f"      Error saving empty daily band {band_save_path}: {e}")
            return None

    time_pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2})T(\d{2}-\d{2}-\d{2})([A-Z]{3})?\.jpg", re.IGNORECASE
    )

    for filename in image_files:
        match = time_pattern.match(filename)
        if match:
            time_str = match.group(2)
            try:
                img_time_obj = datetime.strptime(time_str, "%H-%M-%S").time()
                minute_of_day = img_time_obj.hour * 60 + img_time_obj.minute
                image_path = os.path.join(day_dir_path, filename)
                with Image.open(image_path) as img:
                    img_rgb = img.convert("RGB")
                    avg_color = get_avg_color(img_rgb, sky_coords)
                    if avg_color:
                        minute_colors_accumulator[minute_of_day].append(avg_color)
            except ValueError as ve:
                print(f"      Could not parse time from filename {filename}: {ve}")
            except FileNotFoundError:
                print(f"      Image file not found: {image_path}")
            except Exception as e:
                print(f"      Error processing image {filename}: {e}")
        else:
            print(f"      Filename {filename} does not match expected pattern.")

    final_minute_colors = {}
    for minute, colors_list in minute_colors_accumulator.items():
        if colors_list:
            avg_r = int(sum(c[0] for c in colors_list) / len(colors_list))
            avg_g = int(sum(c[1] for c in colors_list) / len(colors_list))
            avg_b = int(sum(c[2] for c in colors_list) / len(colors_list))
            final_minute_colors[minute] = (avg_r, avg_g, avg_b)

    daily_band_image = Image.new("RGB", (1, DAILY_BAND_HEIGHT))
    draw = ImageDraw.Draw(daily_band_image)
    last_known_color = DEFAULT_SKY_COLOR

    for minute in range(DAILY_BAND_HEIGHT):
        if minute in final_minute_colors:
            current_color = final_minute_colors[minute]
            last_known_color = current_color
        else:
            current_color = last_known_color  # Use previous minute's color
        draw.point((0, minute), fill=current_color)

    band_save_path = os.path.join(day_dir_path, "daylight.png")
    try:
        daily_band_image.save(band_save_path)
        print(f"      Saved daily band to {band_save_path}")
        return band_save_path
    except Exception as e:
        print(f"      Error saving daily band {band_save_path}: {e}")
        return None


def create_monthly_image(year_month_str: str, camera_data_path: str):
    """
    Combines 'daylight.png' bands for a month from camera_data_path.
    Inserts bands of DEFAULT_SKY_COLOR for missing days.
    Saves composite as 'YYYY-MM.png' in camera_data_path/daylight/.
    """
    print(
        f"    Creating/Updating monthly image for {year_month_str} in {camera_data_path}"
    )
    try:
        year, month = map(int, year_month_str.split('-'))
    except ValueError:
        print(f"      Invalid year_month_str format: {year_month_str}. Expected YYYY-MM.")
        return None

    num_days_in_month = calendar.monthrange(year, month)[1]
    images_to_stitch = []
    actual_days_with_data = 0

    for day_num in range(1, num_days_in_month + 1):
        day_str = f"{day_num:02d}" # Format day as DD (e.g., 01, 02, ..., 31)
        day_dir_name = f"{year_month_str}-{day_str}"
        band_path = os.path.join(camera_data_path, day_dir_name, "daylight.png")

        if os.path.exists(band_path):
            try:
                img = Image.open(band_path)
                if img.width == 1 and img.height == DAILY_BAND_HEIGHT:
                    images_to_stitch.append(img)
                    actual_days_with_data +=1
                else:
                    print(
                        f"      Skipping band {band_path} due to incorrect dimensions: {img.size}. Using default color."
                    )
                    default_band = Image.new("RGB", (1, DAILY_BAND_HEIGHT), DEFAULT_SKY_COLOR)
                    images_to_stitch.append(default_band)
            except Exception as e:
                print(f"      Error opening daily band {band_path}: {e}. Using default color.")
                default_band = Image.new("RGB", (1, DAILY_BAND_HEIGHT), DEFAULT_SKY_COLOR)
                images_to_stitch.append(default_band)
        else:
            # print(f"      No daily band found for {day_dir_name}. Using default color.") # Optional: less verbose
            default_band = Image.new("RGB", (1, DAILY_BAND_HEIGHT), DEFAULT_SKY_COLOR)
            images_to_stitch.append(default_band)

    if not images_to_stitch: # Should not happen if we iterate through all days
        print(f"      No daily bands (including defaults) to stitch for {year_month_str}.")
        return None

    # The total width will now always be the number of days in the month
    total_width = num_days_in_month
    monthly_image = Image.new("RGB", (total_width, DAILY_BAND_HEIGHT))
    x_offset = 0
    for img in images_to_stitch:
        monthly_image.paste(img, (x_offset, 0))
        x_offset += img.width
        # img.close() # Consider closing if many images are opened and memory is an issue

    monthly_output_dir = os.path.join(camera_data_path, "daylight")
    os.makedirs(monthly_output_dir, exist_ok=True)

    monthly_image_filename = f"{year_month_str}.png"
    monthly_image_save_path = os.path.join(monthly_output_dir, monthly_image_filename)

    try:
        monthly_image.save(monthly_image_save_path)
        print(
            f"      Saved monthly image to {monthly_image_save_path} ({total_width} days, {actual_days_with_data} with data)"
        )
        return monthly_image_save_path
    except Exception as e:
        print(f"      Error saving monthly image {monthly_image_save_path}: {e}")
        return None


def parse_sky_area(sky_area_str):
    """Parses 'left,top,right,bottom' string into (int, int, int, int) tuple."""
    if not sky_area_str:
        return None
    try:
        parts = [int(p.strip()) for p in sky_area_str.split(",")]
        if len(parts) == 4:
            # Ensure left < right and top < bottom if necessary, though Pillow handles it
            # For simplicity, assume valid coordinates are provided
            return tuple(parts)  # (left, upper, right, lower)
        else:
            print(
                f"      Warning: sky_area string '{sky_area_str}' must have 4 parts (left,top,right,bottom)."
            )
            return None
    except ValueError:
        print(
            f"      Warning: Could not parse sky_area string '{sky_area_str}' into integers."
        )
        return None


# TODO: Fix this
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
    current_day = start_day  # .replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    end_day = end_day  # .replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    # Localize the current_day using the timezone in the config file
    created_daybands_for_yearmonths = set() # Use set for unique yearmonths
    while current_day <= end_day:
        current_yearmonth = current_day.strftime("%Y-%m")
        pic_dir = os.path.join(camera_dir, current_day.strftime("%Y-%m-%d"))
        if not os.path.exists(pic_dir):
            logging.warning(
                f"{current_day.strftime('%Y-%m-%d')}: Skipping non-existent directory: {pic_dir}."
            )
            current_day += timedelta(days=1)
            created_daybands_for_yearmonths.add(current_yearmonth) # Add so month image is still attempted
            continue
        if (
            not os.path.exists(os.path.join(pic_dir, "daylight.png"))
            or overwrite is True
        ):
            logging.info(f"{current_day.strftime('%Y-%m-%d')}: Creating dayband.")
            create_daily_band(pic_dir, parse_sky_area(sky_area_str))
        else:
            logging.info(f"Not overwriting " + os.path.join(pic_dir, "daylight.png"))
        
        created_daybands_for_yearmonths.add(current_yearmonth)
        current_day += timedelta(days=1)

    for yearmonth in sorted(list(created_daybands_for_yearmonths)): # Sort for consistent processing order
        logging.info(f"Creating monthly band for {yearmonth}.")
        create_monthly_image(yearmonth, camera_dir)


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
        # yearmonth = yearmonth_re_matches.group(0) # This would be "YYYY-MM.png"
        yearmonth_str = yearmonth_re_matches.group(1) # This is "YYYY-MM"
        logging.info(f"{yearmonth_str}: Creating monthband HTML.") # Corrected logging
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
    print(f"Found {len(daylight_monthly_bands)} monthly bands in {camera_dir} for HTML browser")

    # Generate the HTML
    HTML_FILE = os.path.join(camera_dir, "daylight.html")
    with open(HTML_FILE, "w") as f:
        f.write(
            dump_html_header(
                title=f"{camera_name} daylight browser", # f-string for title
                additional_headers="""
                <style>
                </style>""",
            )
            + f"""
        <body>
            <div class="right">
                """
        )

        # Generate time labels (0 AM to 11 PM)
        # Corrected loop for AM/PM display
        for hour in range(24):
            display_hour = hour % 12
            if display_hour == 0: # Midnight and Noon
                display_hour = 12
            am_pm = "AM" if hour < 12 else "PM"
            f.write(
                f"""
                <div class="timebox{(hour % 2) + 1}">{display_hour} {am_pm}</div>
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
            try:
                # Use Pillow to get image width to avoid issues if cv2 is not fully available
                # or if the image is somehow corrupted in a way cv2 can't handle but Pillow can open.
                with Image.open(month_band) as img_for_width:
                    width = img_for_width.width
            except Exception as e:
                print(f"Could not read width for {month_band} using Pillow: {e}. Skipping in HTML.")
                continue

            year_month = month_band_nopath.split(".")[0]
            month_pretty_name = get_month_pretty_name_html(year_month)

            f.write(
                f"""
                <div class="band">
                    <div class="band_img_and_link">
                        <a class="month_link" href="daylight/{year_month}.html">
                            <img class="month_band" height="{DAILY_BAND_HEIGHT}px" width="{width}px" src="daylight/{month_band_nopath}" alt="{month_band_nopath}">
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

    logging.info(f"Generating HTML page for {monthband_path} -> {html_outfile}")

    # Get the width of the month image using Pillow for consistency
    try:
        with Image.open(monthband_path) as img_for_width:
            width = img_for_width.width
    except Exception as e:
        logging.error(f"Could not read width for {monthband_path} using Pillow: {e}. Cannot generate month HTML.")
        return


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
            <img src="{os.path.basename(monthband_path)}" usemap="#daylight" width="{width}" height="{DAILY_BAND_HEIGHT}">
            <map name="daylight">
        """ # Referenced image locally
        )

        # Iterate over the days in the month and generate an area tag for each day
        # The width of the image now directly corresponds to the number of days in the month
        # due to the changes in create_monthly_image
        num_days_in_image = width
        current_year, current_month = map(int, year_month.split('-'))

        for day_index in range(num_days_in_image): # day_index is 0 to (width-1)
            day_of_month = day_index + 1 # Day is 1 to num_days_in_image

            # Ensure day is formatted with leading zero if needed for isodate
            day_str_for_isodate = f"{day_of_month:02d}"
            isodate = f"{year_month}-{day_str_for_isodate}"
            dirlink = f"/photos/{camera_name}/{isodate}/" # Assumes this path structure

            # Define the coordinates for the clickable area for this day's band
            # x1 = current x-offset, y1 = 0
            # x2 = current x-offset + width of the band (which is 1 pixel)
            # y2 = height of the band
            x1 = day_index
            x2 = day_index + 1 # Each band is 1 pixel wide

            f.write(
                f"""
                <area shape="rect" coords="{x1},0,{x2},{DAILY_BAND_HEIGHT-1}" alt="{isodate}" href="{dirlink}" title="{isodate}">
            """
            )

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
    if not os.path.isdir(d): # Check if base directory exists
        logging.warning(f"Base directory for listing days does not exist: {d}")
        return valid_days
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
    
    # Ensure CONFIG_FILE_PATH is defined. If not using absl flags for this, define it here or ensure it's globally defined.
    # global CONFIG_FILE_PATH # If it's truly global
    # If FLAGS.config_file is defined:
    # config_file_to_use = FLAGS.config_file if hasattr(FLAGS, 'config_file') and FLAGS.config_file else CONFIG_FILE_PATH
    
    # For simplicity, assuming CONFIG_FILE_PATH is correctly set globally or via FLAGS
    # If you add a flag for config file:
    # config_file_path = FLAGS.config_file if FLAGS.config_file else CONFIG_FILE_PATH

    # Load YAML configuration
    import yaml  # For reading YAML config

    try:
        with open(CONFIG_FILE_PATH, "r") as f: # Use the globally defined CONFIG_FILE_PATH
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

    if not FLAGS.camera: # Check if FLAGS.camera is empty list or None
        camera_names = []
        base_dir_for_cameras = FLAGS.dir if FLAGS.dir else ALL_CAMERAS_BASE_DIR
        if os.path.exists(base_dir_for_cameras):
            for item in os.listdir(base_dir_for_cameras):
                if os.path.isdir(os.path.join(base_dir_for_cameras, item)):
                    camera_names.append(item)
        if not camera_names:
            logging.warning(f"No camera subdirectories found in {base_dir_for_cameras}. Exiting.")
            return
    else:
        camera_names = FLAGS.camera

    logging.info(f"Processing camera directories: {camera_names}")
    for camera_name in camera_names:
        camera_config = config_data["cameras"].get(camera_name)
        if not camera_config:
            print(
                f"  No configuration found for camera '{camera_name}' in {CONFIG_FILE_PATH}. Skipping."
            )
            continue

        sky_area_str_from_config = camera_config.get("sky_area") # Renamed to avoid conflict with flag
        
        # Prioritize flag sky_area if provided, otherwise use config
        sky_area_to_use = FLAGS.sky_area if FLAGS.sky_area else sky_area_str_from_config

        if not sky_area_to_use:
            print(
                f"  'sky_area' not defined for camera '{camera_name}' in config or via flag. Skipping."
            )
            continue

        base_dir_for_cameras = FLAGS.dir if FLAGS.dir else ALL_CAMERAS_BASE_DIR
        camera_dir = os.path.join(base_dir_for_cameras, camera_name)
        logging.info(f"Processing camera directory: {camera_dir}")

        if not os.path.exists(camera_dir):
            logging.error(f"Camera directory {camera_dir} does not exist. Skipping camera.")
            continue
            
        available_days = list_valid_days_directories(camera_dir)
        if not available_days and not FLAGS.html_only : # If no days and not just doing HTML, nothing to process
             logging.warning(f"No valid day directories found in {camera_dir}. Skipping band generation.")
             # Still generate HTML if requested, as it might show empty state or rely on pre-existing files
             if FLAGS.html_only:
                 generate_html(camera_dir=camera_dir)
             continue


        if not FLAGS.html_only:
            if FLAGS.from_date:
                try:
                    start_day = iso_day_to_dt(FLAGS.from_date)
                except ValueError:
                    logging.error(f"Invalid from_date format: {FLAGS.from_date}. Expected YYYY-MM-DD.")
                    return
            elif available_days : # Only if available_days is not empty
                start_day = iso_day_to_dt(available_days[0])
            else: # No available days and no from_date specified
                logging.warning(f"No start date specified and no data found for camera {camera_name}. Skipping band generation.")
                if FLAGS.html_only: # Fall through to generate HTML if that's all that's asked
                    generate_html(camera_dir=camera_dir)
                continue


            if FLAGS.to_date:
                try:
                    end_day = iso_day_to_dt(FLAGS.to_date)
                except ValueError:
                    logging.error(f"Invalid to_date format: {FLAGS.to_date}. Expected YYYY-MM-DD.")
                    return
            elif available_days: # Only if available_days is not empty
                end_day = iso_day_to_dt(available_days[-1])
            else: # No available days and no to_date specified
                logging.warning(f"No end date specified and no data found for camera {camera_name}. Skipping band generation.")
                if FLAGS.html_only:
                     generate_html(camera_dir=camera_dir)
                continue
            
            if start_day > end_day:
                logging.error(f"Start date {start_day.strftime('%Y-%m-%d')} is after end date {end_day.strftime('%Y-%m-%d')}. Skipping.")
                continue


            # Cheap integration test for run_end_of_day (only if a single specific day is processed)
            # This logic seems a bit off if generate_bands_for_time_range is the main processor.
            # Consider if run_end_of_day is still needed here or if its logic is covered by generate_bands_for_time_range.
            # For now, keeping it as per original logic but it might be redundant if range includes single day.
            if FLAGS.from_date and FLAGS.to_date and FLAGS.from_date == FLAGS.to_date:
                 day_dir_path = os.path.join(camera_dir, start_day.strftime("%Y-%m-%d"))
                 if os.path.exists(day_dir_path): # Check if the specific day directory exists
                    logging.info(f"Running end of day for single specified day: {start_day.strftime('%Y-%m-%d')}")
                    run_end_of_day( # This will create daily and then monthly for that day's month.
                        camera_name,
                        day_dir_path,
                        sky_area_to_use, # Use the determined sky_area
                    )
                 else:
                     logging.warning(f"Directory for single specified day {day_dir_path} does not exist. Skipping run_end_of_day.")
            # Always run generate_bands_for_time_range if not html_only
            # This will create daily bands and then call create_monthly_image for each relevant month.
            generate_bands_for_time_range(
                start_day, end_day, camera_dir, sky_area_to_use, FLAGS.overwrite
            )
        
        # Always generate HTML after processing bands or if html_only
        generate_html(camera_dir=camera_dir)


if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string(
        "dir", ALL_CAMERAS_BASE_DIR, "Directory containing all per camera directories."
    )
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
        None, # Default to None, so config is used if this isn't set
        "Crop area of the picture representing the sky. Eg. 0,0,1000,300. Overrides config if set.",
    )
    flags.DEFINE_bool(
        "html_only",
        False,
        "If true, only generate the HTML files and not the daylight bands.",
    )
    flags.DEFINE_multi_string( # 'camera' can be specified multiple times
        "camera",
        [], # Default to empty list
        "Name of the camera. Used to find pictures in the subdirectory of the --dir argument and to looking the sky_area in the config. If not specified, all cameras in the directory are processed.",
    )
    # It's good practice to also define a flag for the config file path if it's not hardcoded
    flags.DEFINE_string("config_file", CONFIG_FILE_PATH, "Path to the YAML configuration file.")

    # Update CONFIG_FILE_PATH based on flag if you want it to be overrideable
    # This needs to happen before main if main directly uses the global.
    # Or, pass FLAGS.config_file to main and use it there.
    # For now, main() will use the global CONFIG_FILE_PATH which can be updated by the flag before app.run()
    
    def _main_wrapper(argv):
        # Update global CONFIG_FILE_PATH if flag is used
        global CONFIG_FILE_PATH
        if FLAGS.config_file:
             CONFIG_FILE_PATH = FLAGS.config_file
        main(argv)

    app.run(_main_wrapper)