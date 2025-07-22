import requests
import time
from typing import Optional
import os
import datetime
from absl import logging
from gopro_utility import GoProEnums

log_dir_global = None

def _set_log_dir(log_dir: str):
    global log_dir_global
    log_dir_global = log_dir

def _log_request_response(url: str, response: requests.Response):
    if log_dir_global:
        os.makedirs(log_dir_global, exist_ok=True)
        log_file_path = os.path.join(log_dir_global, "gopro.log")
        with open(log_file_path, "a") as f:
            f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Request URL: {url}\n")
            f.write(f"Response Code: {response.status_code}\n")
            f.write(f"Response Text: {response.text}\n")
            f.write("-" * 20 + "\n")


class GoProSettings:
    def __init__(self, gopro_instance):
        self._gopro = gopro_instance

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super().__setattr__(name, value)
            return

        setting_name_map = {v.lower().replace(" ", "_"): k for k, v in GoProEnums.SETTING_NAMES.items()}
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
                    raise ValueError(f"'{value}' is not a valid option for '{name}'. Valid options are: {list(value_map.values())}")
        else:
            value_id = value

        self._gopro._make_gopro_request(
            f"/gopro/camera/setting?option={value_id}&setting={setting_id}"
        )

class GoPro:
    def __init__(self, ip_address="10.5.5.9", timeout=5, root_ca=None, log_dir=None):
        self.ip_address = ip_address
        self.timeout = timeout
        self.root_ca = root_ca
        self.scheme = "https" if root_ca else "http"
        self.root_ca_filepath = ""
        self.temp_file = None

        if log_dir:
            _set_log_dir(log_dir)

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

    def update_state(self):
        url = f"{self.scheme}://{self.ip_address}/gopro/camera/state"
        try:
            response = requests.get(url, timeout=self.timeout, verify=self.root_ca_filepath)
            response.raise_for_status()
            self.state = response.json()
        except requests.RequestException as e:
            logging.error(f"Failed to get GoPro state from {self.ip_address}: {e}")
            self.state = {}

    def _make_gopro_request(self, url_path: str, expected_response_code: int = 200, expected_response_text: str = "{}\n"):
        """Helper function to make HTTP requests to GoPro with common parameters."""
        url = f"{self.scheme}://{self.ip_address}{url_path}"
        r = requests.get(url, timeout=self.timeout, verify=self.root_ca_filepath)
        _log_request_response(url, r)
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
        resp = requests.get(media_list_url, timeout=self.timeout, verify=self.root_ca_filepath)
        _log_request_response(media_list_url, resp)
        resp.raise_for_status()
        data = resp.json()

        media_entries = data.get("media") or data.get("results", {}).get("media")
        if not media_entries:
            logging.debug("No media medias found on GoPro.")
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

    def capture_photo(self, output_file: Optional[str] = None) -> bytes:
        latest_dir_before, latest_file_before = self._get_latest_file()

        self._make_gopro_request("/gopro/camera/control/set_ui_controller?p=2")
        self.settings.control_mode = "pro"
        self.settings.lcd_brightness = 10
        self.settings.led = "All Off"
        self.settings.gps = "Off"
        self.settings.auto_power_down = "30 Min"

        trigger_url = f"{self.scheme}://{self.ip_address}/gopro/camera/shutter/start"
        r = requests.get(trigger_url, timeout=self.timeout, verify=self.root_ca_filepath)
        _log_request_response(trigger_url, r)

        while True:
            try:
                latest_dir_after, latest_file_after = self._get_latest_file()
                if (latest_dir_after != latest_dir_before or latest_file_after != latest_file_before):
                    break
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 503:
                    time.sleep(0.5)
                    continue
                raise
            time.sleep(0.5)

        photo_url = f"{self.scheme}://{self.ip_address}/videos/DCIM/{latest_dir_after}/{latest_file_after}"
        photo_resp = requests.get(photo_url, timeout=self.timeout, verify=self.root_ca_filepath)
        photo_resp.raise_for_status()

        if output_file:
            with open(output_file, "wb") as f:
                f.write(photo_resp.content)

        delete_path = f"/gopro/media/delete/file?path={latest_dir_after}/{latest_file_after}"
        self._make_gopro_request(delete_path)

        return photo_resp.content
