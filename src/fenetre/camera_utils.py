import logging
from typing import Dict, Optional
from urllib.parse import urlparse
import pyexiv2

import piexif
import requests
from .postprocess import get_exif_dict

logger = logging.getLogger(__name__)


def get_day_night_from_exif(
    exif_dict: Dict, camera_config: Dict, current_mode: str
) -> str:
    """
    Determines the desired camera mode ('day' or 'night') based on EXIF data.

    :param exif_dict: A dictionary of parsed EXIF values.
    :param camera_config: The camera's configuration dictionary.
    :param current_mode: The current mode of the camera ('day', 'night', 'unknown').
    :return: The desired mode as a string ('day' or 'night').
    """

    day_settings = camera_config.get("day_settings")
    night_settings = camera_config.get("night_settings")

    if not night_settings:
        if not day_settings:
            return current_mode
        else:
            logger.error(
                f"If you specify day settings, you must also specify night settings."
            )
            return current_mode

    if not day_settings:
        logger.error(
            f"If you specify night settings, you must also specify day settings."
        )
        return current_mode

    # TODO: Review the logic to ensure we disable astro and night modes if these aren't set in the config
    exposure_time_s = exif_dict.get("exposure_time")
    iso = exif_dict.get("iso")

    if not exposure_time_s and iso:
        logger.warning("Could not detect day/night mode based on EXIF data.")
        return "unknown"

    exposure_composite_value = iso * exposure_time_s

    astro_settings = camera_config.get("astro_settings")

    night_value = night_settings.get("trigger_exposure_composite_value", 3)
    day_value = day_settings.get("trigger_exposure_composite_value", 2)

    logger.debug(f"We are in {current_mode}")
    logger.debug(
        f"Last picture's ISO: {iso}, exposure time: {exposure_time_s}, composite value: {exposure_composite_value}"
    )

    astro_value: Optional[int] = None

    # Optional astro logic section
    if astro_settings:
        astro_value = astro_settings.get("trigger_exposure_composite_value", 2000)
        logger.debug(f"Astro mode is configured with the threshold of {astro_value}")
        if current_mode == "astro" and astro_settings:
            if exposure_composite_value <= astro_value:
                logger.debug(
                    f"Switching back to night mode because {iso}ISO * {exposure_time_s}s <= {astro_value}"
                )
                return "night"
            return current_mode
        elif current_mode == "night" and astro_settings:
            if exposure_composite_value > astro_value:
                logger.debug(
                    f"Switching to astro mode because {iso}ISO * {exposure_time_s}s > {astro_value}. You can customize this settings in the config: camera.astro_settings.trigger_exposure_composite_value"
                )
                return "astro"
        # We never want to go from unknown to astro because we could stay stuck in there due to the fixed exposure time.
    logger.debug(
        "Current composite value thresholds: day: %s, night: %s, astro: %s",
        day_value,
        night_value,
        astro_value,
    )

    if current_mode != "night":
        if exposure_composite_value > night_value:
            logger.debug(
                f"Switching to night mode because {iso}ISO * {exposure_time_s}s = {exposure_composite_value} > {night_value}. You can customize this settings in the config: camera.night_settings.trigger_exposure_composite_value"
            )
            return "night"

    if current_mode != "day":
        if exposure_composite_value < day_value:
            logger.debug(
                f"Switching to day mode because {iso}ISO * {exposure_time_s}s = {exposure_composite_value} < {day_value}. You can customize this settings in the config: camera.day_settings.trigger_exposure_composite_value"
            )
            return "day"

    logger.debug(f"Keeping the current shooting mode: {current_mode}")
    return current_mode
