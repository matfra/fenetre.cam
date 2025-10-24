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
    new_mode = current_mode

    # Decide if we need to switch to night mode
    if current_mode != "night" and night_settings.get("trigger_iso"):
        iso = exif_dict.get("iso")
        if iso is not None and iso > night_settings["trigger_iso"]:
            logger.debug(f"Switching to night mode based on ISO: {iso} > {night_settings['trigger_iso']}")
            new_mode = "night"

    # Decide if we need to switch to day mode
    if current_mode != "day" and day_settings.get("trigger_exposure_time_s"):
        exposure_time_s = exif_dict.get("exposure_time")
        if (
            exposure_time_s is not None
            and exposure_time_s < day_settings["trigger_exposure_time_s"]
        ):
            new_mode = "day"
            logger.debug(f"Switching to day mode based on exposure time: {exposure_time_s} < {day_settings['trigger_exposure_time_s']}")


    return new_mode


def set_camera_mode(
    camera_name: str,
    camera_config: Dict,
    new_mode: str,
    gopro_instance: Optional[object] = None,
):
    if gopro_instance and hasattr(gopro_instance, "set_mode"):
        gopro_instance.set_mode(new_mode)
        return

    settings_to_apply = camera_config.get(f"{new_mode}_settings", {})
    if url_commands := settings_to_apply.get("url_commands"):
        send_url_commands(camera_name, camera_config, url_commands)


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
        exif_dict = get_exif_dict(exif_data)
    except Exception as e:
        logger.error(f"{camera_name}: Failed to parse EXIF data with pyexiv2: {e}")
        return

    if not camera_config.get("day_settings") and not camera_config.get(
        "night_settings"
    ):
        return

    current_mode = "unknown"  # This function is now state-less from a caller perspective
    new_mode = get_day_night_from_exif(exif_dict, camera_config, current_mode)

    if new_mode != current_mode:
        logger.info(f"{camera_name}: Switching from {current_mode} to {new_mode} mode.")
        try:
            set_camera_mode(camera_name, camera_config, new_mode, gopro_instance)
        except Exception as e:
            logger.error(f"{camera_name}: Failed to set camera mode to {new_mode}: {e}")


def send_url_commands(
    camera_name: str,
    camera_config: Dict,
    url_commands: list,
):
    """
    Sends a list of URL commands to a camera.
    """
    # GoPro commands are now handled directly via apply_settings in the gopro class.
    # This function is now only for generic URL-based cameras.

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
