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
    day_settings = camera_config.get("day_settings", {})
    night_settings = camera_config.get("night_settings", {})

    exposure_time_s = exif_dict.get("exposure_time")
    iso = exif_dict.get("iso")

    if not exposure_time_s and iso:
        logger.warning("Could not detect day/night mode based on EXIF data.")
        return "unknown"

    exposure_composite_value = iso * exposure_time_s

    if current_mode != "night":
        night_value = night_settings.get("trigger_exposure_composite_value", 30)
        if exposure_composite_value > night_value:
            logger.debug(
                f"Switching to night mode because {iso}ISO * {exposure_time_s}s > {night_value}. You can customize this settings in the config: camera.night_settings.trigger_exposure_composite_value"
            )
            return "night"

    if current_mode != "day":
        day_value = day_settings.get("trigger_exposure_composite_value", 2)
        if exposure_composite_value < day_value:
            logger.debug(
                f"Switching to night mode because {iso}ISO * {exposure_time_s}s < {day_value}. You can customize this settings in the config: camera.day_settings.trigger_exposure_composite_value"
            )
            return "day"

    logger.debug(f"Keeping the current shooting mode: {current_mode}")
    return current_mode
