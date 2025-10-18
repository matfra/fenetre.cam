import logging
from typing import Dict, Optional

import piexif
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# In-memory store for the current mode of each camera
camera_modes = {}


def check_and_switch_day_night_mode(
    camera_name: str,
    camera_config: Dict,
    exif_data: bytes,
    gopro_instance: Optional[object] = None,
):
    """
    Checks the EXIF data of a new picture and switches camera settings between day and night mode if needed.
    """
    if not exif_data:
        logger.debug(f"{camera_name}: No EXIF data, cannot determine day/night mode.")
        return

    try:
        exif_data_dict = piexif.load(exif_data)
    except Exception as e:
        logger.error(f"{camera_name}: Failed to parse EXIF data: {e}")
        return

    day_settings = camera_config.get("day_settings", {})
    night_settings = camera_config.get("night_settings", {})

    if not day_settings and not night_settings:
        return

    current_mode = camera_modes.get(camera_name, "unknown")
    new_mode = current_mode

    # Decide if we need to switch to night mode
    if current_mode != "night" and night_settings.get("trigger_iso"):
        try:
            iso = exif_data_dict["Exif"].get(piexif.ExifIFD.ISOSpeedRatings)
            if iso and iso > night_settings["trigger_iso"]:
                new_mode = "night"
        except Exception as e:
            logger.error(f"{camera_name}: Could not read ISO from EXIF: {e}")

    # Decide if we need to switch to day mode
    if current_mode != "day" and day_settings.get("trigger_exposure_time_ms"):
        try:
            exposure_time = exif_data_dict["Exif"].get(piexif.ExifIFD.ExposureTime)
            if exposure_time:
                exposure_time_ms = exposure_time[0] / exposure_time[1] * 1000
                if exposure_time_ms < day_settings["trigger_exposure_time_ms"]:
                    new_mode = "day"
        except Exception as e:
            logger.error(f"{camera_name}: Could not read ExposureTime from EXIF: {e}")

    if new_mode != current_mode:
        logger.info(f"{camera_name}: Switching from {current_mode} to {new_mode} mode.")
        settings_to_apply = day_settings if new_mode == "day" else night_settings
        url_commands = settings_to_apply.get("url_commands", [])

        if url_commands:
            send_url_commands(camera_name, camera_config, url_commands, gopro_instance)

        camera_modes[camera_name] = new_mode


def send_url_commands(
    camera_name: str,
    camera_config: Dict,
    url_commands: list,
    gopro_instance: Optional[object] = None,
):
    """
    Sends a list of URL commands to a camera.
    """
    if gopro_instance:
        logger.info(f"{camera_name}: Sending commands to GoPro.")
        for command in url_commands:
            try:
                gopro_instance._make_gopro_request(command)
            except Exception as e:
                logger.error(
                    f"{camera_name}: Failed to send command '{command}' to GoPro: {e}"
                )
        return

    base_url = camera_config.get("url")
    if not base_url:
        logger.error(
            f"{camera_name}: Cannot send URL commands, no 'url' configured for camera."
        )
        return

    parsed_url = urlparse(base_url)
    scheme = parsed_url.scheme
    netloc = parsed_url.netloc

    logger.info(f"{camera_name}: Sending commands to {scheme}://{netloc}.")
    for command in url_commands:
        try:
            url = f"{scheme}://{netloc}{command}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            logger.debug(
                f"{camera_name}: Successfully sent command: {command}, status: {response.status_code}"
            )
        except requests.RequestException as e:
            logger.error(f"{camera_name}: Failed to send command '{command}': {e}")
