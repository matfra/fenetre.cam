import os
import re
import subprocess
import glob
from typing import Dict
from typing import Tuple
from PIL import Image


from datetime import datetime
from datetime import timedelta
from absl import app
from absl import flags
from absl import logging

import cv2
import numpy as np
import calendar


def get_average_color_of_area(image: np.ndarray, area: Tuple[int]) -> np.ndarray:
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
    return average_color.astype(int)


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
    """This is pretty bad. I'm so sorry. It will return the minute of the day, from 0 to 1439 based on the filename assuming the hour is the 7 and 8 digit and the minute is 9 and 10th."""
    a = re.match(r"\d{4}[^\d]*\d{2}[^\d]*\d{2}[^\d]*(\d{2})[^\d]*(\d{2})", filename)
    try:
        hours, minutes = map(int, a.groups())
    except AttributeError:
        logging.warning(f"Could not figure out the time for file {filename}. Skipping")
        return False
    return hours * 60 + minutes


def get_avg_color_of_the_area(pic_file: str, crop_zone: Tuple[int]) -> bytes:
    full_img = Image.open(pic_file, mode="r")
    cropped_img = full_img.crop(crop_zone)
    a = cropped_img.resize((1, 1), resample=Image.Resampling.BILINEAR)
    return a.tobytes()


def create_day_band(pic_dir: str, sky_area: Tuple[int]) -> bool:
    """COnstruct a 1440 pixel tall, 1px wide png file with each pixel representing the average color of the sky_area for every minute of the day.

    This implies the filename format is: 2023-09-04T16-42-16PDT
    TODO(feature): Customize image naming format, or read time from metadata or use a sequence of image.
    If there are multiple files for a given minute, only the first file is taken into account.
    """
    logging.debug(f"Creating a daylight band for {pic_dir}")

    minute = 0
    # TODO(feature) Start with the previous day's last pixel
    last_pixel_rgb_bytes = b"\xff\x00\x00"  # Start with an almost black pixel
    dayband = bytearray()
    previous_pic_minute = -1

    for pic_filepath in glob.glob(os.path.join(pic_dir, "*.jpg")):
        pic_minute = get_minute_of_day_from_filename(os.path.basename(pic_filepath))
        if pic_minute is False:
            continue
        while pic_minute > minute:
            dayband += last_pixel_rgb_bytes
            logging.debug(
                f"{minute}/1439 Filling with previous data {bytes(last_pixel_rgb_bytes)}"
            )
            minute += 1
            if minute >= 1440:
                break
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

    # Iterate over the days in the month.
    for day in range(1, number_of_days_in_month + 1):
        # Get the path to the daily image.
        month_string = f"0{month}" if month < 10 else str(month)
        day_string = f"0{day}" if day < 10 else str(day)
        daily_image_path = os.path.join(
            main_pic_dir, f"{year}-{month_string}-{day_string}", "daylight.png"
        )

        # If the daily image exists, load it.
        if os.path.exists(daily_image_path):
            daily_image = cv2.imread(daily_image_path)
        else:
            # If the daily image does not exist, fill the corresponding area in the monthly image with black.
            daily_image = np.zeros((1440, 1, 3), dtype=np.uint8)

        if monthly_image is None:
            monthly_image = daily_image

        # Concatenate the daily image to the monthly image.
        monthly_image = np.concatenate((monthly_image, daily_image), axis=1)

    
    daylight_path=os.path.join(main_pic_dir, "daylight")
    if not os.path.exists(daylight_path):
        os.mkdir(daylight_path)
                          
    output_path=os.path.join(daylight_path, f"{year}-{month_string}.png")

    logging.info(f"Writing {output_path}")

    # Save the monthly image.
    cv2.imwrite(
        output_path,
        monthly_image,
    )

    return output_path


def iso_day_to_dt(d: str) -> datetime:
    return datetime(*list(map(int, d.split("-"))))


def run_end_of_day(camera_name, pic_dir, sky_area):
    create_day_band(pic_dir, tuple(map(int, sky_area.split(","))))
    year, month, day = os.path.split(pic_dir)[-1].split("-")
    yearmonth = (int(year), int(month))
    return concatenate_daily_images_into_monthly_image(os.path.join(pic_dir, ".."), yearmonth)

def main(argv):
    del argv  # Unused.
    start_day, end_day = map(iso_day_to_dt, FLAGS.range_days.split(","))
    generate_bands_for_time_range(start_day, end_day, FLAGS.dir, FLAGS.sky_area, FLAGS.overwrite)

def generate_bands_for_time_range(start_day:datetime, end_day:datetime, camera_dir: str, sky_area_str:str , overwrite: bool):
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
            left, top, right, bottom = map(int, sky_area_str.split(','))
            logging.debug(f"Crop zone of ({left},{top}),({right},{bottom})")
            sky_area = (left, top, right, bottom)
            create_day_band(pic_dir, sky_area)
        else:
            logging.info(f"Not overwriting " + os.path.join(pic_dir, "daylight.png"))
        current_day += timedelta(days=1)
        if not current_yearmonth in created_daybands_for_yearmonths:
            created_daybands_for_yearmonths.append(current_yearmonth)
        current_yearmonth = (current_day.year, current_day.month)

    for yearmonth in created_daybands_for_yearmonths:
        logging.info(f"{yearmonth}: Creating monthband.")
        month_png_path = concatenate_daily_images_into_monthly_image(camera_dir, yearmonth)
        generate_month_html(monthband_path=month_png_path , camera_name=os.path.basename(camera_dir))
        generate_html_browser(camera_dir=camera_dir)


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
    <link rel="stylesheet" href="daylight.css">
    {additional_headers}
  </head>
""".format(
        title=title, additional_headers=additional_headers
    )

    return html_header


def generate_html_browser(camera_dir: str):
    """Generates an HTML browser for the daylight images.

    Returns:
        None
    """

    # Camera name should be the name of the directory
    camera_name= os.path.basename(camera_dir)

    # Build the list of all daylight monthly files
    daylight_monthly_bands = glob.glob(os.path.join(camera_dir, "*.png"))

    # Generate the HTML
    HTML_FILE = os.path.join(camera_dir, "daylight.html")
    with open(HTML_FILE, "w") as f:
        f.write("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Daylight browser</title>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                }

                .right {
                    float: right;
                    width: 200px;
                }

                .timebox {
                    height: 60px;
                    width: 20px;
                    background-color: #ccc;
                    text-align: center;
                }

                .timeboxeven {
                    background-color: #eee;
                }

                .bands {
                    display: flex;
                    flex-wrap: wrap;
                }

                .band {
                    flex-grow: 1;
                    margin: 10px;
                }

                .band_img_and_link {
                    display: flex;
                    align-items: center;
                }

                .month_link {
                    text-decoration: none;
                    color: black;
                }

                .month_band {
                    width: 100%;
                    height: 100%;
                }

                .month {
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <div class="right">
                """)

        for i in range(24):
            f.write(f"""
                <div class="timebox{(i % 2) + 1}">{i % 12} AM</div>
                """)

        f.write("""
            </div>
            <div class="bands">
            """)

        for month_band in daylight_monthly_bands:
            month_band_nopath=os.path.basename(month_band)
            width = cv2.imread(month_band).shape[0]
            year_month = month_band.split(".")[0]
            month_pretty_name = get_month_pretty_name_html(year_month)

            f.write(f"""
                <div class="band" style="flex-grow:{width};">
                    <div class="band_img_and_link">
                        <a class="month_link" href="{year_month}.html">
                            <img class="month_band" width="{width}px" height="1440px" src="{month_band_nopath}">
                        </a>
                    </div>
                    <div class="month"><p>{month_pretty_name}</p></div>
                </div>
                """)

        f.write("""
            </div>
        </body>
        </html>
        """)


def get_month_pretty_name_html(year_month:str) -> str:
    datetime.strptime(
                year_month , "%Y-%m"
            ).strftime("%b<br>%Y")

def generate_month_html(monthband_path:str, camera_name:str):
    """Generates an HTML page for the specified month.

    Stretch the month band to the whole screen and create clickable zones for each day.

    Args:
        month: The month to generate the HTML page for.

    Returns:
        None
    """
    # Grab the filename without the extension
    year_month=os.path.basename(monthband_path).split('.')[0] 

    # Grab the path where to generate the HTML file
    html_outfile=os.path.join(
        os.path.dirname(monthband_path),
        f"{year_month}.html"
        )
   
    logging.info(f"Generating HTML page for {monthband_path} ")

    # Get the width of the month image
    width = cv2.imread(monthband_path).shape[1]

    # Write the HTML header
    with open(html_outfile, "w") as f:
        f.write(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{camera_name} - {year_month}</title>
        </head>
        """)

    # Write the body of the HTML file
    with open(html_outfile, "a") as f:
        f.write(f"""
        <body>
            <img src="{year_month}.png" usemap="#daylight" width="{width}" height="1440">
            <map name="daylight">
        """)

        # Iterate over the days in the month and generate an area tag for each day
        x = 0
        for day in range(1, width + 1):
            if day < 10:
                day = f"0{day}"

            isodate = f"{year_month}-{day}"
            dirlink = f"/photos/{camera_name}/{isodate}/"
            
            f.write(f"""
                <area shape="rect" coords="{x},0,{x + 1},1439" alt="{isodate}" href="{dirlink}">
            """)

            x += 1

        # Write the rest of the HTML file
        f.write("""
            </map>
            <script src="/lib/jquery.min.js"></script>
            <script src="/lib/jquery.rwdImageMaps.min.js"></script>
            <script>$(document).ready(function(e) { $("img[usemap]").rwdImageMaps();});</script>
        </body>
        </html>
        """)




if __name__ == "__main__":
    FLAGS = flags.FLAGS

    flags.DEFINE_string("dir", None, "Directory containing all per day directories.")
    flags.DEFINE_string(
        "range_days", None, "Days to build daylight for. Eg. 2022-11-02,2022-12-31"
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
    flags.mark_flags_as_required(["dir", "range_days", "sky_area"])
    app.run(main)
