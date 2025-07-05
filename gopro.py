import requests
import time
from typing import Optional
import os
import datetime
from absl import logging

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


def _make_gopro_request(

    url_path: str,
    expected_response_code: int = 200,
    expected_response_text: str = "{}\n",
    ip_address: str = "10.5.5.9",
    timeout: int = 5,
    root_ca_filepath: str = "",
    scheme: str = "http",
):
    """Helper function to make HTTP requests to GoPro with common parameters."""
    url = f"{scheme}://{ip_address}{url_path}"
    r = requests.get(url, timeout=timeout, verify=root_ca_filepath)
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


def _get_latest_file(
    ip_address: str,
    timeout: int,
    root_ca_filepath: str,
    scheme: str,
):
    media_list_url = f"{scheme}://{ip_address}/gopro/media/list"
    resp = requests.get(media_list_url, timeout=timeout, verify=root_ca_filepath)
    _log_request_response(media_list_url, resp)
    resp.raise_for_status()
    data = resp.json()

    media_entries = data.get("media") or data.get("results", {}).get("media")
    if not media_entries:
        logging.warning("No media medias found on GoPro.")
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


def capture_gopro_photo(
    ip_address: str = "10.5.5.9",
    output_file: Optional[str] = None,
    timeout: int = 5,
    root_ca: Optional[str] = None,
    preset: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> bytes:
    """Capture a photo from a GoPro over WiFi.

    This function triggers the shutter on a GoPro camera and downloads the
    most recent photo using the camera's built-in HTTP API.

    Args:
        ip_address: IP address of the GoPro (default is 10.5.5.9).
        output_file: Optional path to save the downloaded image.
        timeout: Timeout in seconds for the HTTP requests.
        log_dir: Directory to store gopro.log

    Returns:
        The raw bytes of the captured JPEG image.

    Raises:
        requests.RequestException: If any of the network calls fail.
    """
    if log_dir:
        _set_log_dir(log_dir)

    scheme = "https" if root_ca else "http"
    root_ca_filepath = ""
    temp_file = None
    if root_ca:
        import tempfile, os

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(root_ca.encode())
        temp_file.close()
        root_ca_filepath = temp_file.name

    # DONE: Implement the logic to get the last file name, capture, loop until the new file appears, download it
    # Get the last captured file before taking a new one
    latest_dir_before, latest_file_before = _get_latest_file(
        ip_address, timeout, root_ca_filepath, scheme
    )

    """Set the GoPro settings for remote control."""
    # Takeover control of the GoPro camera https://gopro.github.io/OpenGoPro/http#tag/Control/operation/GPCAMERA_SYSTEM_RESET
    _make_gopro_request(
        "/gopro/camera/control/set_ui_controller?p=2",
    )

    # Set the control mode to pro
    _make_gopro_request(
        "/gopro/camera/setting?option=1&setting=175",
    )

    # Set the LCD brightness to minimum to avoid wearing out the LCD
    _make_gopro_request(
        "/gopro/camera/setting?option=10&setting=88",
    )

    # Set photo output to superphoto
#    _make_gopro_request(
#        "/gopro/camera/setting?option=3&setting=125",
#    )

    # Turn off all LEDs:
    _make_gopro_request(
        "/gopro/camera/setting?option=4&setting=91",
    )

    # Disable GPS in metadata
    _make_gopro_request(
        "/gopro/camera/setting?option=1&setting=83",
    )

    # Set up auto power down to 30 minutes (option 7)
    _make_gopro_request(
        "/gopro/camera/setting?option=7&setting=59",
    )


    # Set the GoPro HERO 11 preset for night photography
#    if preset:
#        _make_gopro_request(
#            f"/gopro/camera/presets/load?p1={preset}",
#        )

    # Trigger the shutter to capture a new photo
    trigger_url = f"{scheme}://{ip_address}/gopro/camera/shutter/start"
    r = requests.get(
        trigger_url,
        timeout=timeout,
        verify=root_ca_filepath,
    )
    _log_request_response(trigger_url, r)

    # Poll for the last captured file until it changes
    while True:
        try:
            latest_dir_after, latest_file_after = _get_latest_file(
                ip_address, timeout, root_ca_filepath, scheme
            )
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

    photo_url = (
        f"{scheme}://{ip_address}/videos/DCIM/{latest_dir_after}/{latest_file_after}"
    )
    photo_resp = requests.get(photo_url, timeout=timeout, verify=root_ca_filepath)
    photo_resp.raise_for_status()

    if output_file:
        with open(output_file, "wb") as f:
            f.write(photo_resp.content)

    delete_url = f"{scheme}://{ip_address}/gopro/media/delete/file?path={latest_dir_after}/{latest_file_after}"
    r = requests.get(
        delete_url,
        timeout=timeout,
        verify=root_ca_filepath,
    )
    _log_request_response(delete_url, r)

    if temp_file:
        import os

        os.unlink(temp_file.name)

    return photo_resp.content
