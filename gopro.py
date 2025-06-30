import requests
import time
from typing import Optional

# TODO: Use Bluetooth to enable wifi and wait for NetworkManager to connect to the wifi and IP connectivity to be available before attempting capture. Gopro tutorial has the code to enable wifi via bluetooth: https://github.com/gopro/OpenGoPro/blob/main/demos/python/tutorial/tutorial_modules/tutorial_6_connect_wifi/enable_wifi_ap.py

def capture_gopro_photo(
    ip_address: str = "10.5.5.9",
    output_file: Optional[str] = None,
    timeout: int = 5,
    root_ca: Optional[str] = None,
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

# TODO: Set the control mode to pro https://gopro.github.io/OpenGoPro/http#tag/settings/operation/GPCAMERA_CHANGE_SETTING::175
# TODO: Set the prese to the correct mode (photo night: 65539) or create a special preset. We may want preset for day, sunset/sunrise and night 

    trigger_url = f"{scheme}://{ip_address}/gopro/camera/shutter/start"
    requests.get(
        trigger_url,
        timeout=timeout,
        verify=verify_path,
    )

    # Small delay to allow the camera to process the capture
    time.sleep(2)

    # Retrieve the media list to find the latest file. The OpenGoPro API returns
    # a list of directories with the files they contain. We support both the
    # older `d`/`fs` fields as well as the newer `directory`/`files` names.
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

    photo_url = f"{scheme}://{ip_address}/videos/DCIM/{latest_dir}/{latest_file}"
    photo_resp = requests.get(photo_url, timeout=timeout, verify=verify_path)
    photo_resp.raise_for_status()

    if output_file:
        with open(output_file, "wb") as f:
            f.write(photo_resp.content)

    if temp_file:
        import os

        os.unlink(temp_file.name)

    return photo_resp.content
