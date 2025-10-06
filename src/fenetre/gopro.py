from datetime import datetime
import logging
import os
import time
from typing import Optional
import logging.handlers

import pytz
import requests
from astral import LocationInfo
from astral.sun import sun

from fenetre.gopro_state_map import GoProEnums

logger = logging.getLogger(__name__)


class GoProSettings:
    def __init__(self, gopro_instance):
        self._gopro = gopro_instance

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
            return

        setting_name_map = {
            v.lower().replace(" ", "_"): k for k, v in GoProEnums.SETTING_NAMES.items()
        }
        setting_id = setting_name_map.get(name)

        if setting_id is None:
            raise AttributeError(f"'{name}' is not a valid setting.")

        value_map = GoProEnums.SETTING_VALUES.get(setting_id)
        if value_map:
            # Find the key corresponding to the value
            value_id = None
            for k, v in value_map.items():
                if v.lower().replace(" ", "_") == str(value).lower().replace(" ", "_"):
                    value_id = k
                    break
            if value_id is None:
                # if the value is not found, try to see if an int was passed
                if isinstance(value, int) and value in value_map:
                    value_id = value
                else:
                    raise ValueError(
                        f"'{value}' is not a valid option for '{name}'. Valid options are: {list(value_map.values())}"
                    )
        else:
            value_id = value

        self._gopro._make_gopro_request(
            f"/gopro/camera/setting?option={value_id}&setting={setting_id}"
        )


class GoPro:
    def __init__(
        self,
        ip_address="10.5.5.9",
        timeout=5,
        root_ca=None,
        log_dir=None,
        lat=None,
        lon=None,
        timezone=None,
        preset_day=None,
        preset_night=None,
        gopro_usb=False,
    ):
        self.ip_address = ip_address
        self.timeout = timeout
        self.root_ca = root_ca
        self.scheme = "https" if root_ca else "http"
        self.root_ca_filepath = ""
        self.temp_file = None
        self.lat = lat
        self.lon = lon
        self.timezone = timezone
        self.preset_day = preset_day
        self.preset_night = preset_night
        self.gopro_usb = gopro_usb
        self.log_dir = log_dir

        if self.root_ca:
            import tempfile

            self.temp_file = tempfile.NamedTemporaryFile(delete=False)
            self.temp_file.write(self.root_ca.encode())
            self.temp_file.close()
            self.root_ca_filepath = self.temp_file.name

        self.settings = GoProSettings(self)
        self.state = {}

    def __del__(self):
        if self.temp_file:
            os.unlink(self.temp_file.name)

    def _log_request_response(self, url: str, response: requests.Response):
        # Only log if the root logger is in DEBUG mode.
        if logging.getLogger().getEffectiveLevel() > logging.DEBUG:
            return

        gopro_logger = logging.getLogger("gopro")
        if self.log_dir and not gopro_logger.hasHandlers():
            log_file_path = os.path.join(self.log_dir, "gopro.log")
            handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=10000000,  # Default, should be configured from main
                backupCount=5,
            )
            formatter = logging.Formatter(
                "%(levelname).1s%(asctime)s] %(message)s",
                datefmt="%m%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            gopro_logger.addHandler(handler)
            gopro_logger.setLevel(logging.DEBUG)
            gopro_logger.propagate = False

        log_message = (
            f"Request URL: {url}\n"
            f"Response Code: {response.status_code}\n"
            f"Response Text: {response.text}"
        )
        gopro_logger.debug(log_message)

    def update_state(self):
        url = f"{self.scheme}://{self.ip_address}/gopro/camera/state"
        try:
            response = requests.get(
                url, timeout=self.timeout, verify=self.root_ca_filepath
            )
            response.raise_for_status()
            self.state = response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get GoPro state from {self.ip_address}: {e}")
            self.state = {}

    def get_presets(self):
        """Get the available presets from the camera."""
        url = f"{self.scheme}://{self.ip_address}/gopro/camera/presets/get"
        try:
            response = requests.get(
                url, timeout=self.timeout, verify=self.root_ca_filepath
            )
            self._log_request_response(url, response)
            response.raise_for_status()
            preset_group_array = response.json().get("presetGroupArray", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get GoPro presets from {self.ip_address}: {e}")
        if len(preset_group_array) > 0:
            for preset_group in preset_group_array:
                if preset_group.get("id") == "PRESET_GROUP_ID_PHOTO":
                    return preset_group.get("presetArray", [])
        return []

    def _make_gopro_request(
        self,
        url_path: str,
        expected_response_code: int = 200,
        expected_response_text: str = "{}\n",
    ):
        """Helper function to make HTTP requests to GoPro with common parameters."""
        url = f"{self.scheme}://{self.ip_address}{url_path}"
        r = requests.get(url, timeout=self.timeout, verify=self.root_ca_filepath)
        self._log_request_response(url, r)
        if r.status_code != expected_response_code:
            raise RuntimeError(
                f"Expected response code {expected_response_code} but got {r.status_code}. Request URL: {url}"
            )
        if r.text != expected_response_text:
            raise RuntimeError(
                f"Expected response text {expected_response_text} but got {r.text}. Request URL: {url}"
            )
        return r

    def _get_latest_file(self):
        media_list_url = f"{self.scheme}://{self.ip_address}/gopro/media/list"
        resp = requests.get(
            media_list_url, timeout=self.timeout, verify=self.root_ca_filepath
        )
        self._log_request_response(media_list_url, resp)
        resp.raise_for_status()
        data = resp.json()

        media_entries = data.get("media") or data.get("results", {}).get("media")
        if not media_entries:
            logger.info("No media medias found on GoPro.")
            return None, None

        latest_dir_info = media_entries[-1]
        latest_dir = latest_dir_info.get("directory") or latest_dir_info.get("d")

        if "filename" in latest_dir_info:
            latest_file = latest_dir_info["filename"]
        else:
            files = latest_dir_info.get("files") or latest_dir_info.get("fs")
            if not files:
                raise RuntimeError("No files returned by GoPro")
            latest_file_info = files[-1]
            latest_file = latest_file_info.get("filename") or latest_file_info.get("n")
        return latest_dir, latest_file

    def _is_night(self) -> bool:
        """Determines if it is currently night time."""
        if not all([self.lat, self.lon, self.timezone]):
            logger.info("Location not configured for GoPro, assuming daytime.")
            return False

        try:
            tz = pytz.timezone(self.timezone)
            now = datetime.now(tz)
            location = LocationInfo(latitude=self.lat, longitude=self.lon)
            s = sun(location.observer, date=now.date(), tzinfo=tz)

            # It's night if current time is after dusk or before dawn
            is_night_time = now > s["dusk"] or now < s["dawn"]
            logger.debug(f"It is {'night' if is_night_time else 'day'}.")
            return is_night_time
        except Exception as e:
            logger.error(f"Error calculating sunrise/sunset for GoPro: {e}")
            return False  # Default to day

    def validate_presets(self):
        """
        Validates that the configured day and night presets are available on the camera.
        """
        available_presets = self.get_presets()
        if not available_presets:
            logger.error("Could not retrieve available presets from the camera.")
            return

        logger.info(f"Available presets: {[p.get('name') for p in available_presets]}")

        available_preset_ids = [p.get("id") for p in available_presets]

        if self.preset_day and self.preset_day.get("id") not in available_preset_ids:
            logger.error(
                f"Configured day preset ID '{self.preset_day.get('id')}' is not available on the camera."
            )

        if (
            self.preset_night
            and self.preset_night.get("id") not in available_preset_ids
        ):
            logger.error(
                f"Configured night preset ID '{self.preset_night.get('id')}' is not available on the camera."
            )

    def capture_photo(self, output_file: Optional[str] = None) -> bytes:
        latest_dir_before, latest_file_before = self._get_latest_file()

        if self.gopro_usb:
            self._make_gopro_request("/gopro/camera/control/wired_usb?p=1")
        else:
            self._make_gopro_request("/gopro/camera/control/set_ui_controller?p=2")
        self.settings.control_mode = "pro"
        self.settings.lcd_brightness = 10
        self.settings.led = "All Off"
        self.settings.gps = "Off"
        self.settings.auto_power_down = "30 Min"

        preset_config = None
        if self._is_night():
            if self.preset_night:
                preset_config = self.preset_night
        else:
            if self.preset_day:
                preset_config = self.preset_day

        if preset_config:
            if "id" in preset_config:
                self._make_gopro_request(
                    f"/gopro/camera/presets/load?id={preset_config['id']}"
                )
            if "settings" in preset_config and isinstance(
                preset_config["settings"], dict
            ):
                for setting, value in preset_config["settings"].items():
                    try:
                        setattr(self.settings, setting, value)
                        logger.info(f"Applied setting '{setting}' with value '{value}'")
                    except (AttributeError, ValueError) as e:
                        logger.error(
                            f"Failed to apply setting '{setting}' with value '{value}': {e}"
                        )

        trigger_url = f"{self.scheme}://{self.ip_address}/gopro/camera/shutter/start"
        r = requests.get(
            trigger_url, timeout=self.timeout, verify=self.root_ca_filepath
        )
        self._log_request_response(trigger_url, r)

        start_time = time.time()
        timeout_seconds = 60  # Wait up to 60 seconds for the new photo

        while True:
            if time.time() - start_time > timeout_seconds:
                raise RuntimeError("Timeout waiting for new photo to appear on GoPro.")

            try:
                latest_dir_after, latest_file_after = self._get_latest_file()
                if (
                    latest_dir_after != latest_dir_before
                    or latest_file_after != latest_file_before
                ):
                    break
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 503:
                    time.sleep(0.5)
                    continue
                raise
            time.sleep(0.5)

        photo_url = f"{self.scheme}://{self.ip_address}/videos/DCIM/{latest_dir_after}/{latest_file_after}"
        photo_resp = requests.get(
            photo_url, timeout=self.timeout, verify=self.root_ca_filepath
        )
        photo_resp.raise_for_status()

        if output_file:
            with open(output_file, "wb") as f:
                f.write(photo_resp.content)

        delete_path = (
            f"/gopro/media/delete/file?path={latest_dir_after}/{latest_file_after}"
        )
        self._make_gopro_request(delete_path)

        return photo_resp.content
