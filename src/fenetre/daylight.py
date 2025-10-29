import calendar  # Added for getting days in month
import glob
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# --- Configuration ---
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


def run_end_of_day(camera_name, day_dir_path, sky_area):
    """Runs the end of day processing for a given camera and day directory. Typically it creates the daily band and updates the monthly image, regenerate all HTML files."""
    if sky_area is None:
        sky_area = DEFAULT_SKY_AREA

    # Determine sky_coords once using the first available image
    sky_coords = None
    first_image_path = None
    image_files = sorted(
        [f for f in os.listdir(day_dir_path) if f.lower().endswith(".jpg")]
    )

    if image_files:
        first_image_path = os.path.join(day_dir_path, image_files[0])
        try:
            with Image.open(first_image_path) as img:
                sky_coords = parse_sky_area(sky_area, img.size)
        except Exception as e:
            logger.error(
                f"Failed to open first image {first_image_path} to determine sky_coords: {e}"
            )

    if not sky_coords:
        logger.warning(
            f"Could not determine sky_coords for {day_dir_path}. Using default color for daily band."
        )
        # Create a band with default color if sky_coords can't be determined
        daily_band_image = Image.new("RGB", (1, DAILY_BAND_HEIGHT), DEFAULT_SKY_COLOR)
        band_save_path = os.path.join(day_dir_path, "daylight.png")
        try:
            daily_band_image.save(band_save_path)
            logger.info(f"Saved daily band with default color to {band_save_path}")
        except Exception as e:
            logger.error(f"Error saving default daily band {band_save_path}: {e}")
        return

    create_daily_band(day_dir_path, sky_coords)
    year, month, _ = os.path.split(day_dir_path)[-1].split("-")
    camera_dir = os.path.join(day_dir_path, os.path.pardir)
    create_monthly_image(f"{year}-{month}", camera_dir)
    generate_html(camera_dir=camera_dir)


def get_avg_color(image, crop_box):
    """Crops image to crop_box and returns average RGB color."""
    try:
        sky_region = image.crop(crop_box)
        avg_color_tuple = np.array(sky_region).mean(axis=(0, 1))
        return tuple(int(c) for c in avg_color_tuple)
    except Exception as e:
        print(f"      Error getting average color: {e}")
        return DEFAULT_SKY_COLOR


def create_daily_band(
    day_dir_path: str, sky_coords: Optional[Tuple[int, int, int, int]]
):
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
        year, month = map(int, year_month_str.split("-"))
    except ValueError:
        print(
            f"      Invalid year_month_str format: {year_month_str}. Expected YYYY-MM."
        )
        return None

    num_days_in_month = calendar.monthrange(year, month)[1]
    images_to_stitch = []
    actual_days_with_data = 0

    for day_num in range(1, num_days_in_month + 1):
        day_str = f"{day_num:02d}"  # Format day as DD (e.g., 01, 02, ..., 31)
        day_dir_name = f"{year_month_str}-{day_str}"
        band_path = os.path.join(camera_data_path, day_dir_name, "daylight.png")

        if os.path.exists(band_path):
            try:
                img = Image.open(band_path)
                if img.width == 1 and img.height == DAILY_BAND_HEIGHT:
                    images_to_stitch.append(img)
                    actual_days_with_data += 1
                else:
                    print(
                        f"      Skipping band {band_path} due to incorrect dimensions: {img.size}. Using default color."
                    )
                    default_band = Image.new(
                        "RGB", (1, DAILY_BAND_HEIGHT), DEFAULT_SKY_COLOR
                    )
                    images_to_stitch.append(default_band)
            except Exception as e:
                print(
                    f"      Error opening daily band {band_path}: {e}. Using default color."
                )
                default_band = Image.new(
                    "RGB", (1, DAILY_BAND_HEIGHT), DEFAULT_SKY_COLOR
                )
                images_to_stitch.append(default_band)
        else:
            # print(f"      No daily band found for {day_dir_name}. Using default color.") # Optional: less verbose
            default_band = Image.new("RGB", (1, DAILY_BAND_HEIGHT), DEFAULT_SKY_COLOR)
            images_to_stitch.append(default_band)

    if not images_to_stitch:  # Should not happen if we iterate through all days
        print(
            f"      No daily bands (including defaults) to stitch for {year_month_str}."
        )
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


def parse_sky_area(
    sky_area_str: str, image_size: Tuple[int, int]
) -> Optional[Tuple[int, int, int, int]]:
    """Parses 'left,top,right,bottom' string into an absolute pixel tuple."""
    if not sky_area_str:
        return None
    try:
        parts = [float(p.strip()) for p in sky_area_str.split(",")]
        if len(parts) == 4:
            # If all values are <= 1.0, treat them as ratios
            if all(v <= 1.0 for v in parts):
                img_width, img_height = image_size
                x1 = int(img_width * parts[0])
                y1 = int(img_height * parts[1])
                x2 = int(img_width * parts[2])
                y2 = int(img_height * parts[3])
                return (x1, y1, x2, y2)
            else:  # Otherwise, treat as absolute pixel values (legacy)
                return tuple(int(p) for p in parts)
        else:
            logger.warning(f"sky_area string '{sky_area_str}' must have 4 parts.")
            return None
    except ValueError:
        logger.warning(f"Could not parse sky_area string '{sky_area_str}'.")
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
    current_day = start_day
    created_daybands_for_yearmonths = set()

    # Determine sky_coords once using the first available image in the range
    sky_coords = None
    day_to_check = start_day
    while day_to_check <= end_day:
        pic_dir = os.path.join(camera_dir, day_to_check.strftime("%Y-%m-%d"))
        if os.path.exists(pic_dir):
            image_files = sorted(
                [f for f in os.listdir(pic_dir) if f.lower().endswith(".jpg")]
            )
            if image_files:
                first_image_path = os.path.join(pic_dir, image_files[0])
                try:
                    with Image.open(first_image_path) as img:
                        sky_coords = parse_sky_area(sky_area_str, img.size)
                        break  # Found an image, got coords, exit loop
                except Exception as e:
                    logger.error(
                        f"Failed to open first image {first_image_path} to determine sky_coords: {e}"
                    )
                    # Continue to next day if this one fails
        day_to_check += timedelta(days=1)

    if not sky_coords:
        logger.warning(
            f"Could not determine sky_coords for the date range in {camera_dir}. No images found. Skipping band generation."
        )
        return

    while current_day <= end_day:
        current_yearmonth = current_day.strftime("%Y-%m")
        pic_dir = os.path.join(camera_dir, current_day.strftime("%Y-%m-%d"))
        if not os.path.exists(pic_dir):
            logger.warning(
                f"{current_day.strftime('%Y-%m-%d')}: Skipping non-existent directory: {pic_dir}."
            )
            current_day += timedelta(days=1)
            created_daybands_for_yearmonths.add(
                current_yearmonth
            )  # Add so month image is still attempted
            continue
        if (
            not os.path.exists(os.path.join(pic_dir, "daylight.png"))
            or overwrite is True
        ):
            logger.info(f"{current_day.strftime('%Y-%m-%d')}: Creating dayband.")
            create_daily_band(pic_dir, sky_coords)
        else:
            logger.info(f"Not overwriting " + os.path.join(pic_dir, "daylight.png"))

        created_daybands_for_yearmonths.add(current_yearmonth)
        current_day += timedelta(days=1)

    for yearmonth in sorted(
        list(created_daybands_for_yearmonths)
    ):  # Sort for consistent processing order
        logger.info(f"Creating monthly band for {yearmonth}.")
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
            logger.warning(
                f"Skipping {yearmonth_file} as it does not match the expected format."
            )
            continue
        # yearmonth = yearmonth_re_matches.group(0) # This would be "YYYY-MM.png"
        yearmonth_str = yearmonth_re_matches.group(1)  # This is "YYYY-MM"
        logger.info(f"{yearmonth_str}: Creating monthband HTML.")  # Corrected logging
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
    print(
        f"Found {len(daylight_monthly_bands)} monthly bands in {camera_dir} for HTML browser"
    )

    # Generate the HTML
    HTML_FILE = os.path.join(camera_dir, "daylight.html")
    with open(HTML_FILE, "w") as f:
        f.write(
            dump_html_header(
                title=f"{camera_name} daylight browser",  # f-string for title
                additional_headers="""
            <style>
            </style>""",
            )
            + """
    <body>
        <div class="right">
            """
        )

        # Generate time labels (0 AM to 11 PM)
        # Corrected loop for AM/PM display
        for hour in range(24):
            display_hour = hour % 12
            if display_hour == 0:  # Midnight and Noon
                display_hour = 12
            am_pm = "AM" if hour < 12 else "PM"
            f.write(
                f'<div class="timebox{(hour % 2) + 1}">{display_hour} {am_pm}</div>'
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
                print(
                    f"Could not read width for {month_band} using Pillow: {e}. Skipping in HTML."
                )
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

    logger.info(f"Generating HTML page for {monthband_path} -> {html_outfile}")

    # Get the width of the month image using Pillow for consistency
    try:
        with Image.open(monthband_path) as img_for_width:
            width = img_for_width.width
    except Exception as e:
        logger.error(
            f"Could not read width for {monthband_path} using Pillow: {e}. Cannot generate month HTML."
        )
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
        """  # Referenced image locally
        )

        # Iterate over the days in the month and generate an area tag for each day
        # The width of the image now directly corresponds to the number of days in the month
        # due to the changes in create_monthly_image
        num_days_in_image = width
        current_year, current_month = map(int, year_month.split("-"))

        for day_index in range(num_days_in_image):  # day_index is 0 to (width-1)
            day_of_month = day_index + 1  # Day is 1 to num_days_in_image

            # Ensure day is formatted with leading zero if needed for isodate
            day_str_for_isodate = f"{day_of_month:02d}"
            isodate = f"{year_month}-{day_str_for_isodate}"
            # TODO Track the source of .. and get rid of it
            if camera_name == "..":
                dirlink = f"{camera_name}/{isodate}/"
            else:
                dirlink = (
                    f"/photos/{camera_name}/{isodate}/"  # Assumes this path structure
                )

            # Define the coordinates for the clickable area for this day's band
            # x1 = current x-offset, y1 = 0
            # x2 = current x-offset + width of the band (which is 1 pixel)
            # y2 = height of the band
            x1 = day_index
            x2 = day_index + 1  # Each band is 1 pixel wide

            x2 = day_index + 1  # Each band is 1 pixel wide

            f.write(
                f'<area shape="rect" coords="{x1},0,{x2},{DAILY_BAND_HEIGHT - 1}" alt="{isodate}" href="{dirlink}" title="{isodate}">'
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
    if not os.path.isdir(d):  # Check if base directory exists
        logger.warning(f"Base directory for listing days does not exist: {d}")
        return valid_days
    for subdir in os.listdir(d):
        full_dir = os.path.join(d, subdir)
        if not os.path.isdir(full_dir):
            continue
        if re.match(r"\d{4}-\d{2}-\d{2}", subdir):
            valid_days.append(subdir)
    return sorted(valid_days)
