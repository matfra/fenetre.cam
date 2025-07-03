import requests
import time
from typing import Optional


def _set_gopro_settings(
    ip_address: str,
    preset: str,
    timeout: int,
    verify_path: str,
    scheme: str,
):
    """Set the GoPro settings for remote control."""
    # Takeover control of the GoPro camera https://gopro.github.io/OpenGoPro/http#tag/Control/operation/GPCAMERA_SYSTEM_RESET
    camera_control_url = (
        f"{scheme}://{ip_address}/gopro/camera/control/set_ui_controller?p=2"
    )
    requests.get(
        camera_control_url,
        timeout=timeout,
        verify=verify_path,
    )

    # Set the control mode to pro
    pro_mode_url = f"{scheme}://{ip_address}/gopro/camera/setting?option=1&setting=175"
    requests.get(
        pro_mode_url,
        timeout=timeout,
        verify=verify_path,
    )

    # TODO(Enable this based on the GPS coordinates of the camera and expected sunset time)

    night_photo_url = (
        f"{scheme}://{ip_address}/gopro/camera/setting?option=1&setting=177"
    )
    requests.get(
        night_photo_url,
        timeout=timeout,
        verify=verify_path,
    )

    # Set the LCD brightness to minimum to avoid wearing out the LCD
    lcd_brightness_url = f"{scheme}://{ip_address}/gopro/camera/setting?option=10&setting=88"
    requests.get(
        lcd_brightness_url,
        timeout=timeout,
        verify=verify_path,
    )

    # Set photo output to superphoto
    photo_output_url = f"{scheme}://{ip_address}/gopro/camera/setting?option=3&setting=125"
    requests.get(
        photo_output_url,
        timeout=timeout,
        verify=verify_path,
    )

    # Turn off all LEDs:
    led_off_url = f"{scheme}://{ip_address}/gopro/camera/setting?option=4&setting=91"
    requests.get(
        led_off_url,
        timeout=timeout,
        verify=verify_path,
    )

    # Disable GPS in metadata
    gps_off_url = f"{scheme}://{ip_address}/gopro/camera/setting?option=1&setting=83"
    requests.get(
        gps_off_url,
        timeout=timeout,
        verify=verify_path,
    )

    # Set up auto power down to 30 minutes (option 7)
    auto_power_down_url = f"{scheme}://{ip_address}/gopro/camera/setting?option=1&setting=59"
    requests.get(
        auto_power_down_url,
        timeout=timeout,
        verify=verify_path,
    )


    """Set the GoPro preset."""
    if preset:
        preset_url = f"{scheme}://{ip_address}/gopro/camera/presets/load?p1={preset}"
        requests.get(
            preset_url,
            timeout=timeout,
            verify=verify_path,
        )


def _get_latest_file(
    ip_address: str,
    timeout: int,
    verify_path: str,
    scheme: str,
):
    media_list_url = f"{scheme}://{ip_address}/gopro/media/list"
    resp = requests.get(media_list_url, timeout=timeout, verify=verify_path)
    resp.raise_for_status()
    data = resp.json()

    media_entries = data.get("media") or data.get("results", {}).get("media")
    if not media_entries:
        raise RuntimeError("No media information returned from GoPro")

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
) -> bytes:
    """Capture a photo from a GoPro over WiFi.

    This function triggers the shutter on a GoPro camera and downloads the
    most recent photo using the camera's built-in HTTP API.

    Args:
        ip_address: IP address of the GoPro (default is 10.5.5.9).
        output_file: Optional path to save the downloaded image.
        timeout: Timeout in seconds for the HTTP requests.

    Returns:
        The raw bytes of the captured JPEG image.

    Raises:
        requests.RequestException: If any of the network calls fail.
    """

    scheme = "https" if root_ca else "http"
    verify_path = True
    temp_file = None
    if root_ca:
        import tempfile, os

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(root_ca.encode())
        temp_file.close()
        verify_path = temp_file.name

    # DONE: Implement the logic to get the last file name, capture, loop until the new file appears, download it
    # Get the last captured file before taking a new one
    latest_dir_before, latest_file_before = _get_latest_file(
        ip_address, timeout, verify_path, scheme
    )

    
    _set_gopro_settings(ip_address, preset, timeout, verify_path, scheme)

    # Trigger the shutter to capture a new photo
    trigger_url = f"{scheme}://{ip_address}/gopro/camera/shutter/start"
    requests.get(
        trigger_url,
        timeout=timeout,
        verify=verify_path,
    )

    # Poll for the last captured file until it changes
    while True:
        try:
            latest_dir_after, latest_file_after = _get_latest_file(
                ip_address, timeout, verify_path, scheme
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
    photo_resp = requests.get(photo_url, timeout=timeout, verify=verify_path)
    photo_resp.raise_for_status()

    if output_file:
        with open(output_file, "wb") as f:
            f.write(photo_resp.content)

    delete_url = f"{scheme}://{ip_address}/gopro/media/delete/file?path={latest_dir_after}/{latest_file_after}"
    requests.get(
        delete_url,
        timeout=timeout,
        verify=verify_path,
    )

    if temp_file:
        import os

        os.unlink(temp_file.name)

    return photo_resp.content
