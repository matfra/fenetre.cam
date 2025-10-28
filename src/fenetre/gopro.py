import logging
import os
import time
from typing import Optional
import logging.handlers

import requests

from fenetre.gopro_state_map import GoProEnums


logger = logging.getLogger(__name__)


def GoPro(gopro_model="hero11", **kwargs):
    model = (gopro_model or "hero11").lower()
    if model == "hero6":
        return GoProHero6(**kwargs)
    elif model == "hero9":
        return GoProHero9(**kwargs)
    elif model in {"hero11", "open_gopro"}:
        if model == "open_gopro":
            logger.warning(
                "GoPro model 'open_gopro' is deprecated, defaulting to 'hero11'."
            )
        return GoProHero11(**kwargs)
    else:
        raise ValueError(f"Unknown GoPro model: {gopro_model}")


class GoProHero6Settings:
    def __init__(self, gopro_instance):
        ip_address = ("10.5.5.9",)
        self._gopro = gopro_instance
        self._setting_map = {
            "photo_resolution": 17,
            "protune": 21,
            "white_balance": 22,
            "color": 23,
            "iso_limit": 24,
            "sharpness": 25,
        }
        self._value_map = {
            17: {
                "12mp_wide": 0,
                "12mp_linear": 10,
                "12mp_medium": 8,
                "12mp_narrow": 9,
            },
            21: {"off": 0, "on": 1},
            22: {
                "auto": 0,
                "3000k": 1,
                "5500k": 2,
                "6500k": 3,
                "native": 4,
                "4000k": 5,
                "4800k": 6,
                "6000k": 7,
                "2300k": 8,
                "2800k": 9,
                "3200k": 10,
                "4500k": 11,
            },
            23: {"gopro": 0, "flat": 1},
            24: {"800": 0, "400": 1, "200": 2, "100": 3},
            25: {"high": 0, "med": 1, "low": 2},
        }

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
            return

        setting_id = self._setting_map.get(name)
        if setting_id is None:
            raise AttributeError(f"'{name}' is not a valid setting.")

        value_map = self._value_map.get(setting_id)
        value_id = None
        if value_map:
            if isinstance(value, str):
                value_id = value_map.get(value.lower().replace(" ", "_"))
            elif isinstance(value, int) and value in value_map.values():
                value_id = value

            if value_id is None:
                raise ValueError(
                    f"'{value}' is not a valid option for '{name}'. Valid options are: {list(value_map.keys())}"
                )
        else:
            value_id = value

        self._gopro._make_gopro_request(
            f"/gp/gpControl/setting/{setting_id}/{value_id}"
        )


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

        self._gopro.set_setting(setting_id, value_id)


class _GoProModernBase:
    def __init__(
        self,
        ip_address="10.5.5.9",
        timeout=20,
        root_ca=None,
        log_dir=None,
        lat=None,
        lon=None,
        timezone=None,
        gopro_usb=False,
        camera_config={},
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
        self.gopro_usb = gopro_usb
        self.log_dir = log_dir
        self.camera_config = camera_config

        if self.root_ca:
            import tempfile

            self.temp_file = tempfile.NamedTemporaryFile(delete=False)
            self.temp_file.write(self.root_ca.encode())
            self.temp_file.close()
            self.root_ca_filepath = self.temp_file.name

        self.settings = GoProSettings(self)
        self.state = {}

        if self.gopro_usb:
            logger.info("GoPro is in USB mode, waiting for it to be ready...")
            start_time = time.time()
            while time.time() - start_time < 30:
                try:
                    self.update_state()
                    if self.state:
                        logger.info("GoPro is ready.")
                        self._make_gopro_request("/gopro/camera/control/wired_usb?p=1")
                        break
                except requests.RequestException:
                    time.sleep(1)
            else:
                logger.error("GoPro did not become ready in 30 seconds.")

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

    def apply_settings(self, settings: Optional[dict]):
        if not settings:
            return
        if not isinstance(settings, dict):
            logger.error("GoPro settings payload must be a dict, got %r", settings)
            return
        for setting, value in settings.items():
            try:
                setattr(self.settings, setting, value)
                logger.info(
                    "Applied GoPro setting '%s' with value '%s'", setting, value
                )
            except (AttributeError, ValueError) as exc:
                logger.error(
                    "Failed to apply GoPro setting '%s' with value '%s': %s",
                    setting,
                    value,
                    exc,
                )

    def set_setting(self, setting_id: int, value_id: int):
        raise NotImplementedError

    def _make_gopro_request(
        self,
        url_path: str,
        expected_response_code: int = 200,
    ):
        """Helper function to make HTTP requests to GoPro with common parameters."""
        url = f"{self.scheme}://{self.ip_address}{url_path}"
        r = requests.get(url, timeout=self.timeout, verify=self.root_ca_filepath)
        self._log_request_response(url, r)
        if r.status_code != expected_response_code:
            raise RuntimeError(
                f"Expected response code {expected_response_code} but got {r.status_code}. Request URL: {url}"
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

    def set_mode(self, mode: str):
        settings_to_apply = self.camera_config.get(f"{mode}_settings", {}).get("urlpaths_commands", [])
        logger.debug(f"Will apply settings for mode '{mode}': {settings_to_apply}")
        for urlpath in settings_to_apply:
            self._make_gopro_request(urlpath)

    def capture_photo(
        self, output_file: Optional[str] = None
    ) -> bytes:
        latest_dir_before, latest_file_before = self._get_latest_file()

        self._make_gopro_request(
            "/gopro/camera/control/set_ui_controller?p=2"
        )  # Only for gopro 10+
        # self.settings.control_mode = "pro" # Only for gopro 11+
        self.settings.lcd_brightness = 10
        self.settings.led = "All Off"
        self.settings.gps = "Off"
        self.settings.auto_power_down = "30 Min"

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


class GoProHero11(_GoProModernBase):
    def set_setting(self, setting_id: int, value_id: int):
        self._make_gopro_request(
            f"/gopro/camera/setting?option={value_id}&setting={setting_id}"
        )


class GoProHero9(_GoProModernBase):
    def set_setting(self, setting_id: int, value_id: int):
        self._make_gopro_request(
            f"/gp/gpControl/setting/{setting_id}/{value_id}",
            expected_response_text=None,
        )


class GoProHero6:
    def __init__(
        self,
        ip_address="10.5.5.9",
        timeout=20,
        log_dir=None,
        lat=None,
        lon=None,
        timezone=None,
        gopro_usb=False,  # Not supported on Hero6
        root_ca=None,  # Not supported on Hero6
        camera_config={},
    ):
        self.ip_address = ip_address
        self.timeout = timeout
        self.scheme = "http"
        self.lat = lat
        self.lon = lon
        self.timezone = timezone
        self.log_dir = log_dir
        self.state = {}
        self.settings = GoProHero6Settings(self)
        self.camera_config = camera_config


    def apply_settings(
        self, settings: Optional[dict], camera_config: Optional[dict] = None
    ):
        if not settings:
            return
        if not isinstance(settings, dict):
            logger.error(
                "GoPro Hero6 settings payload must be a dict, got %r", settings
            )
            return
        for setting, value in settings.items():
            try:
                setattr(self.settings, setting, value)
                logger.info(
                    "Applied GoPro Hero6 setting '%s' with value '%s'", setting, value
                )
            except (AttributeError, ValueError) as exc:
                logger.error(
                    "Failed to apply GoPro Hero6 setting '%s' with value '%s': %s",
                    setting,
                    value,
                    exc,
                )

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
            f"Response Code: {response.status_code}"
#            f"Response Text: {response.text}"
        )
        gopro_logger.debug(log_message)

    def _make_gopro_request(
        self,
        url_path: str,
        expected_response_code: int = 200,
    ):
        """Helper function to make HTTP requests to GoPro with common parameters."""
        url = f"{self.scheme}://{self.ip_address}{url_path}"
        r = requests.get(url, timeout=self.timeout)
        # self._log_request_response(url, r) # TODO
        if r.status_code != expected_response_code:
            raise RuntimeError(
                f"Expected response code {expected_response_code} but got {r.status_code}. Request URL: {url}"
            )
        return r

    def _get_latest_file(self):
        media_list_url = f"{self.scheme}://{self.ip_address}/gp/gpMediaList"
        resp = requests.get(media_list_url, timeout=self.timeout)
        self._log_request_response(media_list_url, resp)
        resp.raise_for_status()
        data = resp.json()

        media_entries = data.get("media")
        if not media_entries:
            logger.info("No media medias found on GoPro.")
            return None, None

        latest_dir_info = media_entries[-1]
        latest_dir = latest_dir_info.get("d")

        files = latest_dir_info.get("fs")
        if not files:
            raise RuntimeError("No files returned by GoPro")
        latest_file_info = files[-1]
        latest_file = latest_file_info.get("n")
        return latest_dir, latest_file

    def update_state(self):
        url = f"{self.scheme}://{self.ip_address}/status"
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            self.state = response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get GoPro state from {self.ip_address}: {e}")
            self.state = {}

    def set_mode(self, mode: str):
        # Set photo mode
        logger.debug("Setting GoPro 6 mode to photo")
        self._make_gopro_request("/gp/gpControl/command/mode?p=1")
        settings_to_apply = self.camera_config.get(f"{mode}_settings", {}).get("urlpaths_commands", [])
        logger.debug(f"Will apply settings for mode '{mode}': {settings_to_apply}")
        for urlpath in settings_to_apply:
            self._make_gopro_request(urlpath)

    def capture_photo(
        self, output_file: Optional[str] = None
    ) -> bytes:
        latest_dir_before, latest_file_before = self._get_latest_file()

        # Trigger shutter
        self._make_gopro_request("/gp/gpControl/command/shutter?p=1")

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
        photo_resp = requests.get(photo_url, timeout=self.timeout)
        photo_resp.raise_for_status()

        if output_file:
            with open(output_file, "wb") as f:
                f.write(photo_resp.content)

        delete_path = f"/gp/gpControl/command/storage/delete?p={latest_dir_after}/{latest_file_after}"
        self._make_gopro_request(delete_path)

        return photo_resp.content


# Backward compatibility alias
GoProOpenGoPro = GoProHero11
