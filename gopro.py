import requests
import time
from typing import Optional

# TODO(maybe): Use Bluetooth to enable wifi and wait for NetworkManager to connect to the wifi and IP connectivity to be available before attempting capture. Gopro tutorial has the code to enable wifi via bluetooth: https://github.com/gopro/OpenGoPro/blob/main/demos/python/tutorial/tutorial_modules/tutorial_6_connect_wifi/enable_wifi_ap.py

def set_gopro_preset(
    ip_address: str,
    preset: str,
    timeout: int,
    verify_path: str,
    scheme: str,
):
    """Set the GoPro preset."""
    preset_url = f"{scheme}://{ip_address}/gopro/camera/presets/load?p1={preset}"
    requests.get(
        preset_url,
        timeout=timeout,
        verify=verify_path,
    )


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

# DONE: Reverted to previous method of listing all medias and looking at the last item.
    if preset:
        set_gopro_preset(ip_address, preset, timeout, verify_path, scheme)

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

    delete_url = f"{scheme}://{ip_address}/gopro/media/delete/file?path={latest_dir}/{latest_file}"
    requests.get(
        delete_url,
        timeout=timeout,
        verify=verify_path,
    )

    
    if temp_file:
        import os

        os.unlink(temp_file.name)

    # Set the control mode to pro
    pro_mode_url = f"{scheme}://{ip_address}/gopro/camera/setting?p1=175&p2=1"
    requests.get(
        pro_mode_url,
        timeout=timeout,
        verify=verify_path,
    )

    return photo_resp.content


def get_gopro_state(
    ip_address: str = "10.5.5.9",
    timeout: int = 5,
    root_ca: Optional[str] = None,
) -> str:
    """Get the GoPro state and format it in Prometheus format."""
    from open_gopro.communication_client import GoProHttp

    gopro = GoProHttp(ip_address, root_ca)
    state = gopro.get_camera_state()
    return "\n".join(
        f'gopro_{key}{{camera="{ip_address}"}} {value}'
        for key, value in state.items()
    )

