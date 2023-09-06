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
    a = re.match("\d{4}[^\d]*\d{2}[^\d]*\d{2}[^\d]*(\d{2})[^\d]*(\d{2})", filename)
    hours, minutes = map(int, a.groups())
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
):
    """Concatenates daily images of 1 by 1440 pixels into one monthly image with a height of 1440 pixels and a width equal to the number of days in the month, filling with black if there are missing daily images.

    Args:
      main_pic_dir: The path to the directory containing the daily directories.
      yearmonth: Tuple for year and month as int.
    """

    # Get the number of days in the month.
    year, month = yearmonth
    number_of_days_in_month = calendar.monthrange(year, month)[1]
    # Create a numpy array to store the monthly image.
    monthly_image = None

    # Iterate over the days in the month.
    for day in range(1, number_of_days_in_month +1):
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
            monthly_image=daily_image
        
        # Concatenate the daily image to the monthly image.
        monthly_image = np.concatenate((monthly_image, daily_image), axis=1)

    # Save the monthly image.
    cv2.imwrite(
        os.path.join(main_pic_dir, "daylight", f"{year}-{month_string}.png"),
        monthly_image,
    )


def iso_day_to_dt(d: str) -> datetime:
    return datetime(*list(map(int, d.split("-"))))


def main(argv):
    del argv  # Unused.
    current_day, end_day = map(iso_day_to_dt, FLAGS.range_days.split(","))
    created_daybands_for_yearmonths = []
    while current_day <= end_day:
        current_yearmonth = (current_day.year, current_day.month)
        pic_dir = os.path.join(FLAGS.dir, current_day.strftime("%Y-%m-%d"))
        if not os.path.exists(pic_dir):
            logging.warning(
                f"{current_day}: Skipping non-existent directory: {pic_dir}."
            )
            current_day += timedelta(days=1)
            continue
        if (
            not os.path.exists(os.path.join(pic_dir, "daylight.png"))
            or FLAGS.overwrite is True
        ):
            logging.info(f"{current_day}: Creating dayband.")
            left, top, right, bottom = map(int, FLAGS.sky_area.split(","))
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
        concatenate_daily_images_into_monthly_image(FLAGS.dir, yearmonth)


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
