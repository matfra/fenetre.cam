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


def get_minute_of_day_from_filename(filename: str) -> int:
    """This is pretty bad. I'm so sorry. It will return the minute of the day, from 0 to 1439 based on the filename assuming the hour is the 7 and 8 digit and the minute is 9 and 10th."""
    a = re.match("\d{4}[^\d]*\d{2}[^\d]*\d{2}[^\d]*(\d{2})[^\d]*(\d{2})", filename)
    hours, minutes = map(int, a.groups())
    return hours * 60 + minutes


def get_avg_color_of_the_area(pic_file: str, crop_zone: Tuple[int]) -> bytes:
    full_img = Image.open(pic_file, mode="r")
    cropped_img = full_img.crop(crop_zone)
    return cropped_img.resize((1, 1)).tobytes()


def create_day_band(pic_dir: str, sky_area: str) -> bool:
    """COnstruct a 1440 pixel tall, 1px wide png file with each pixel representing the average color of the sky_area for every minute of the day.

    This implies the filename format is: 2023-09-04T16-42-16PDT
    TODO(feature): Customize image naming format, or read time from metadata or use a sequence of image.
    If there are multiple files for a given minute, only the first file is taken into account.
    """
    logging.debug(f"Creating a daylight band for {pic_dir}")
    left, top, right, bottom = map(int, sky_area.split(","))
    logging.debug(f"Crop zone of ({left},{top}),({right},{bottom})")

    minute = 0
    # TODO(feature) Start with the previous day's last pixel
    last_pixel_rgb_bytes = b"\x00\x00\x00"  # Start with an almost black pixel
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
        last_pixel_rgb_bytes = get_avg_color_of_the_area(
            pic_filepath, (left, top, right, bottom)
        )
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


def create_month_band(main_pic_dir: str, yearmonth: Tuple[int]) -> str:
    """Aggregates all the day bands from a given month"""
    day = 1
    year, month = yearmonth
    date_tracker = datetime(year=year, month=month, day=day)
    month_string = date_tracker.strftime("%m")
    monthband = bytearray()
    last_day_rgb_bytes = Image.new(
        size=(1, 1440), color=(0, 0, 0), mode="RGB"
    ).tobytes()
    for dayband_path in glob.glob(
        os.path.join(main_pic_dir, f"{year}-{month_string}-*", "daylight.png")
    ):
        logging.info(f"Aggregating: {dayband_path}")
        pic_day = int(os.path.dirname(dayband_path).split("-")[-1])
        while pic_day > day:
            monthband += last_day_rgb_bytes
            logging.debug(
                f"Day {day} of {yearmonth}: Missing data, Filling with previous data {bytes(last_day_rgb_bytes)}"
            )
            day += 1
            date_tracker += timedelta(days=1)
            if date_tracker.month > month:
                break
        # We found a data for the month
        monthband += Image.open(dayband_path).tobytes()

    img = Image.frombytes(size=(1440, day), data=bytes(monthband), mode="RGB")

    if not os.path.exists(os.path.join(main_pic_dir, "daylight")):
        os.makedirs(os.path.join(main_pic_dir, "daylight"), exist_ok=True)
    a = img.rotate(90, expand=True)
    a.save(os.path.join(main_pic_dir, "daylight", f"{year}-{month_string}.png"))


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
            and FLAGS.overwrite is False
        ):
            logging.info(f"{current_day}: Creating dayband.")
            create_day_band(pic_dir, FLAGS.sky_area)
        else:
            logging.info(f"Not overwriting " + os.path.join(pic_dir, "daylight.png"))
        current_day += timedelta(days=1)
        if not current_yearmonth in created_daybands_for_yearmonths:
            created_daybands_for_yearmonths.append(current_yearmonth)
        current_yearmonth = (current_day.year, current_day.month)

    for yearmonth in created_daybands_for_yearmonths:
        logging.info(f"{yearmonth}: Creating monthband.")
        create_month_band(FLAGS.dir, yearmonth)


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
