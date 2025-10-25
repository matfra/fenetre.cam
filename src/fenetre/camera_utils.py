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

    if current_mode == "unknown":
        if iso > night_settings.get("trigger_iso", 300): # In any situation, we should be in night mode if we are above 300 ISO
            return "night"
        if exposure_time_s > night_settings.get("trigger_exposure_time_s", 0.5): # Obviously we are already in night mode
            return "night"
        return "day"
            
    if current_mode == "day" and iso > night_settings.get("trigger_iso", 300):
            logger.debug(f"Next shooting mode should be night based on ISO: {iso} > {night_settings['trigger_iso']}")
            return "night"

    if current_mode == "night" and exposure_time_s < day_settings.get("trigger_exposure_time_s", 0.05):
        return "day"

    return current_mode

