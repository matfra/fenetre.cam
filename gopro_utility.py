""" Utility functions for GoPro 11+

Most of the code here is copied from tutorial modules at https://github.com/gopro/OpenGoPro.git
"""
import sys
import os
import threading
import time
import requests
import socket
import asyncio
import enum
from typing import Dict, Optional, Any, Callable, Awaitable, TypeVar


from absl import logging

from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice as BleakDevice
from bleak.backends.characteristic import BleakGATTCharacteristic
from admin_server import gopro_state_gauge, gopro_setting_gauge
import re

T = TypeVar("T")

GOPRO_BASE_UUID = "b5f9{}-aa8d-11e3-9046-0002a5d5c51b"
noti_handler_T = Callable[[BleakGATTCharacteristic, bytearray], Awaitable[None]]

gopro_status_names = {
    1: "Battery Present",
    2: "Internal Battery Bars",
    6: "Overheating",
    8: "Busy",
    9: "Quick Capture",
    10: "Encoding",
    11: "LCD Lock",
    13: "Video Encoding Duration",
    17: "Wireless Connections Enabled",
    19: "Pairing State",
    20: "Last Pairing Type",
    21: "Last Pairing Success",
    22: "Wifi Scan State",
    23: "Last Wifi Scan Success",
    24: "Wifi Provisioning State",
    26: "Remote Version",
    27: "Remote Connected",
    28: "Pairing State (Legacy)",
    29: "Connected WiFi SSID",
    30: "Access Point SSID",
    31: "Connected Devices",
    32: "Preview Stream",
    33: "Primary Storage",
    34: "Remaining Photos",
    35: "Remaining Video Time",
    38: "Photos",
    39: "Videos",
    41: "OTA",
    42: "Pending FW Update Cancel",
    45: "Locate",
    49: "Timelapse Interval Countdown",
    54: "SD Card Remaining",
    55: "Preview Stream Available",
    56: "Wifi Bars",
    58: "Active Hilights",
    59: "Time Since Last Hilight",
    60: "Minimum Status Poll Period",
    65: "Liveview Exposure Select Mode",
    66: "Liveview Y",
    67: "Liveview X",
    68: "GPS Lock",
    69: "AP Mode",
    70: "Internal Battery Percentage",
    74: "Microphone Accessory",
    75: "Zoom Level",
    76: "Wireless Band",
    77: "Zoom Available",
    78: "Mobile Friendly",
    79: "FTU",
    81: "5GHZ Available",
    82: "Ready",
    83: "OTA Charged",
    85: "Cold",
    86: "Rotation",
    88: "Zoom while Encoding",
    89: "Flatmode",
    93: "Video Preset",
    94: "Photo Preset",
    95: "Timelapse Preset",
    96: "Preset Group",
    97: "Preset",
    98: "Preset Modified",
    99: "Remaining Live Bursts",
    100: "Live Bursts",
    101: "Capture Delay Active",
    102: "Media Mod State",
    103: "Time Warp Speed",
    104: "Linux Core",
    105: "Lens Type",
    106: "Hindsight",
    107: "Scheduled Capture Preset ID",
    108: "Scheduled Capture",
    110: "Display Mod Status",
    111: "SD Card Write Speed Error",
    112: "SD Card Errors",
    113: "Turbo Transfer",
    114: "Camera Control ID",
    115: "USB Connected",
    116: "USB Controlled",
    117: "SD Card Capacity",
    118: "Photo Interval Capture Count",
}

gopro_status_values = {
    1: {0: "False", 1: "True"},
    2: {0: "Zero", 1: "One", 2: "Two", 3: "Three", 4: "Charging"},
    6: {0: "False", 1: "True"},
    8: {0: "False", 1: "True"},
    9: {0: "False", 1: "True"},
    10: {0: "False", 1: "True"},
    11: {0: "False", 1: "True"},
    17: {0: "False", 1: "True"},
    19: {0: "Never Started", 1: "Started", 2: "Aborted", 3: "Cancelled", 4: "Completed"},
    20: {0: "Not Pairing", 1: "Pairing App", 2: "Pairing Remote Control", 3: "Pairing Bluetooth Device"},
    22: {0: "Never started", 1: "Started", 2: "Aborted", 3: "Canceled", 4: "Completed"},
    24: {0: "Never started", 1: "Started", 2: "Aborted", 3: "Canceled", 4: "Completed"},
    27: {0: "False", 1: "True"},
    32: {0: "False", 1: "True"},
    33: {-1: "Unknown", 0: "OK", 1: "SD Card Full", 2: "SD Card Removed", 3: "SD Card Format Error", 4: "SD Card Busy", 8: "SD Card Swapped"},
    41: {0: "Idle", 1: "Downloading", 2: "Verifying", 3: "Download Failed", 4: "Verify Failed", 5: "Ready", 6: "GoPro App Downloading", 7: "GoPro App Verifying", 8: "GoPro App Download Failed", 9: "GoPro App Verify Failed", 10: "GoPro App Ready"},
    42: {0: "False", 1: "True"},
    45: {0: "False", 1: "True"},
    55: {0: "False", 1: "True"},
    65: {0: "Disabled", 1: "Auto", 2: "ISO Lock", 3: "Hemisphere"},
    68: {0: "False", 1: "True"},
    69: {0: "False", 1: "True"},
    74: {0: "Accessory not connected", 1: "Accessory connected", 2: "Accessory connected and a microphone is plugged into the accessory"},
    76: {0: "2.4 GHz", 1: "5 GHz"},
    77: {0: "False", 1: "True"},
    78: {0: "False", 1: "True"},
    79: {0: "False", 1: "True"},
    81: {0: "False", 1: "True"},
    82: {0: "False", 1: "True"},
    83: {0: "False", 1: "True"},
    85: {0: "False", 1: "True"},
    86: {0: "0 degrees (upright)", 1: "180 degrees (upside down)", 2: "90 degrees (laying on right side)", 3: "270 degrees (laying on left side)"},
    88: {0: "False", 1: "True"},
}

gopro_setting_names = {
    2: "Video Resolution",
    3: "Frames Per Second",
    5: "Video Timelapse Rate",
    30: "Photo Timelapse Rate",
    32: "Nightlapse Rate",
    43: "Webcam Digital Lenses",
    59: "Auto Power Down",
    83: "GPS",
    88: "LCD Brightness",
    91: "LED",
    108: "Video Aspect Ratio",
    121: "Video Lens",
    122: "Photo Lens",
    123: "Time Lapse Digital Lenses",
    125: "Photo Output",
    128: "Media Format",
    134: "Anti-Flicker",
    135: "Hypersmooth",
    150: "Video Horizon Leveling",
    151: "Photo Horizon Leveling",
    156: "Video Duration",
    157: "Multi Shot Duration",
    162: "Max Lens",
    167: "HindSight",
    168: "Scheduled Capture",
    171: "Photo Single Interval",
    172: "Photo Interval Duration",
    173: "Video Performance Mode",
    175: "Control Mode",
    176: "Easy Mode Speed",
    177: "Enable Night Photo",
    178: "Wireless Band",
    179: "Star Trails Length",
    180: "System Video Mode",
    182: "Video Bit Rate",
    183: "Bit Depth",
    184: "Profiles",
    186: "Video Easy Mode",
    187: "Lapse Mode",
    189: "Max Lens Mod",
    190: "Max Lens Mod Enable",
    191: "Easy Night Photo",
    192: "Multi Shot Aspect Ratio",
    193: "Framing",
    216: "Camera Volume",
    219: "Setup Screen Saver",
    223: "Setup Language",
    227: "Photo Mode",
    232: "Video Framing",
    233: "Multi Shot Framing",
    234: "Frame Rate",
}

gopro_setting_values = {
    2: {1: "4K", 4: "2.7K", 6: "2.7K 4:3", 7: "1440", 9: "1080", 12: "720", 18: "4K 4:3", 24: "5K", 25: "5K 4:3", 26: "5.3K 8:7", 27: "5.3K 4:3", 28: "4K 8:7", 35: "5.3K 21:9", 36: "4K 21:9", 37: "4K 1:1", 38: "900", 100: "5.3K", 107: "5.3K 8:7 V2", 108: "4K 8:7 V2", 109: "4K 9:16 V2", 110: "1080 9:16 V2", 111: "2.7K 4:3 V2", 112: "4K 4:3 V2", 113: "5.3K 4:3 V2"},
    3: {0: "240.0", 1: "120.0", 2: "100.0", 5: "60.0", 6: "50.0", 8: "30.0", 9: "25.0", 10: "24.0", 13: "200.0", 15: "400.0", 16: "360.0", 17: "300.0"},
    5: {0: "0.5 Seconds", 1: "1 Second", 2: "2 Seconds", 3: "5 Seconds", 4: "10 Seconds", 5: "30 Seconds", 6: "60 Seconds", 7: "2 Minutes", 8: "5 Minutes", 9: "30 Minutes", 10: "60 Minutes", 11: "3 Seconds"},
    30: {11: "3 Seconds", 100: "60 Minutes", 101: "30 Minutes", 102: "5 Minutes", 103: "2 Minutes", 104: "60 Seconds", 105: "30 Seconds", 106: "10 Seconds", 107: "5 Seconds", 108: "2 Seconds", 109: "1 Second", 110: "0.5 Seconds"},
    32: {4: "4 Seconds", 5: "5 Seconds", 10: "10 Seconds", 15: "15 Seconds", 20: "20 Seconds", 30: "30 Seconds", 100: "60 Seconds", 120: "2 Minutes", 300: "5 Minutes", 1800: "30 Minutes", 3600: "60 Minutes", 3601: "Auto"},
    43: {0: "Wide", 2: "Narrow", 3: "Superview", 4: "Linear"},
    59: {0: "Never", 1: "1 Min", 4: "5 Min", 6: "15 Min", 7: "30 Min", 11: "8 Seconds", 12: "30 Seconds"},
    83: {0: "Off", 1: "On"},
    91: {0: "Off", 2: "On", 3: "All On", 4: "All Off", 5: "Front Off Only", 100: "Back Only"},
    108: {0: "4:3", 1: "16:9", 3: "8:7", 4: "9:16", 5: "21:9", 6: "1:1"},
    121: {0: "Wide", 2: "Narrow", 3: "Superview", 4: "Linear", 7: "Max SuperView", 8: "Linear + Horizon Leveling", 9: "HyperView", 10: "Linear + Horizon Lock", 11: "Max HyperView", 12: "Ultra SuperView", 13: "Ultra Wide", 14: "Ultra Linear", 104: "Ultra HyperView"},
    122: {0: "Wide 12 MP", 10: "Linear 12 MP"},
}

def get_human_readable_state(state: Dict) -> Dict:
    """
    Converts a numerical GoPro state dictionary to a human-readable one.
    """
    human_readable_state = {}
    # Process statuses
    if 'status' in state:
        for key, value in state['status'].items():
            key = int(key)
            status_name = gopro_status_names.get(key, f"Unknown Status ({key})")
            if key in gopro_status_values:
                value_name = gopro_status_values[key].get(value, f"Unknown Value ({value})")
            else:
                value_name = value
            human_readable_state[status_name] = value_name

    # Process settings
    if 'settings' in state:
        for key, value in state['settings'].items():
            key = int(key)
            setting_name = gopro_setting_names.get(key, f"Unknown Setting ({key})")
            if key in gopro_setting_values:
                value_name = gopro_setting_values[key].get(value, f"Unknown Value ({value})")
            else:
                value_name = value
            human_readable_state[setting_name] = value_name

    return human_readable_state


class GoProUuid(str, enum.Enum):
    """UUIDs to write to and receive responses from"""

    COMMAND_REQ_UUID = GOPRO_BASE_UUID.format("0072")
    COMMAND_RSP_UUID = GOPRO_BASE_UUID.format("0073")
    SETTINGS_REQ_UUID = GOPRO_BASE_UUID.format("0074")
    SETTINGS_RSP_UUID = GOPRO_BASE_UUID.format("0075")
    CONTROL_QUERY_SERVICE_UUID = "0000fea6-0000-1000-8000-00805f9b34fb"
    INTERNAL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    QUERY_REQ_UUID = GOPRO_BASE_UUID.format("0076")
    QUERY_RSP_UUID = GOPRO_BASE_UUID.format("0077")
    WIFI_AP_SSID_UUID = GOPRO_BASE_UUID.format("0002")
    WIFI_AP_PASSWORD_UUID = GOPRO_BASE_UUID.format("0003")
    NETWORK_MANAGEMENT_REQ_UUID = GOPRO_BASE_UUID.format("0091")
    NETWORK_MANAGEMENT_RSP_UUID = GOPRO_BASE_UUID.format("0092")

    @classmethod
    def dict_by_uuid(cls, value_creator: Callable[["GoProUuid"], T]) -> dict["GoProUuid", T]:
        """Build a dict where the keys are each UUID defined here and the values are built from the input value_creator.

        Args:
            value_creator (Callable[[GoProUuid], T]): callable to create the values from each UUID

        Returns:
            dict[GoProUuid, T]: uuid-to-value mapping.
        """
        return {uuid: value_creator(uuid) for uuid in cls}


def exception_handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    """Catch exceptions from non-main thread

    Args:
        loop (asyncio.AbstractEventLoop): loop to catch exceptions in
        context (Dict[str, Any]): exception context
    """
    msg = context.get("exception", context["message"])
    logging.error(f"Caught exception {str(loop)}: {msg}")
    logging.critical("This is unexpected and unrecoverable.")


async def connect_ble(notification_handler: noti_handler_T, identifier: str | None = None) -> BleakClient:
    """Connect to a GoPro, then pair, and enable notifications

    If identifier is None, the first discovered GoPro will be connected to.

    Retry 10 times

    Args:
        notification_handler (noti_handler_T): callback when notification is received
        identifier (str, optional): Last 4 digits of GoPro serial number. Defaults to None.

    Raises:
        Exception: couldn't establish connection after retrying 10 times

    Returns:
        BleakClient: connected client
    """

    asyncio.get_event_loop().set_exception_handler(exception_handler)

    RETRIES = 10
    for retry in range(RETRIES):
        try:
            # Map of discovered devices indexed by name
            devices: dict[str, BleakDevice] = {}

            # Scan for devices
            logging.info("Scanning for bluetooth devices...")

            # Scan callback to also catch nonconnectable scan responses
            # pylint: disable=cell-var-from-loop
            def _scan_callback(device: BleakDevice, _: Any) -> None:
                # Add to the dict if not unknown
                if device.name and device.name != "Unknown":
                    devices[device.name] = device

            # Scan until we find devices
            matched_devices: list[BleakDevice] = []
            while len(matched_devices) == 0:
                # Now get list of connectable advertisements
                for device in await BleakScanner.discover(timeout=5, detection_callback=_scan_callback):
                    if device.name and device.name != "Unknown":
                        devices[device.name] = device
                # Log every device we discovered
                for d in devices:
                    logging.info(f"\tDiscovered: {d}")
                # Now look for our matching device(s)
                token = re.compile(identifier or r"GoPro [A-Z0-9]{4}")
                matched_devices = [device for name, device in devices.items() if token.match(name)]
                logging.info(f"Found {len(matched_devices)} matching devices.")

            # Connect to first matching Bluetooth device
            device = matched_devices[0]

            logging.info(f"Establishing BLE connection to {device}...")
            client = BleakClient(device)
            await client.connect(timeout=15)
            logging.info("BLE Connected!")

            # Try to pair (on some OS's this will expectedly fail)
            logging.info("Attempting to pair...")
            try:
                await client.pair()
            except NotImplementedError:
                # This is expected on Mac
                pass
            logging.info("Pairing complete!")

            # Enable notifications on all notifiable characteristics
            logging.info("Enabling notifications...")
            for service in client.services:
                for char in service.characteristics:
                    if "notify" in char.properties:
                        logging.info(f"Enabling notification on char {char.uuid}")
                        await client.start_notify(char, notification_handler)
            logging.info("Done enabling notifications")
            logging.info("BLE Connection is ready for communication.")

            return client
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(f"Connection establishment failed: {exc}")
            logging.warning(f"Retrying #{retry}")

    raise RuntimeError(f"Couldn't establish BLE connection after {RETRIES} retries")


async def enable_wifi(identifier: str | None = None) -> tuple[str, str, BleakClient]:
    """Connect to a GoPro via BLE, find its WiFi AP SSID and password, and enable its WiFI AP

    If identifier is None, the first discovered GoPro will be connected to.

    Args:
        identifier (str, optional): Last 4 digits of GoPro serial number. Defaults to None.

    Returns:
        Tuple[str, str]: ssid, password
    """
    # Synchronization event to wait until notification response is received
    event = asyncio.Event()
    client: BleakClient

    async def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        uuid = GoProUuid(client.services.characteristics[characteristic.handle].uuid)
        logging.info(f'Received response at {uuid}: {data.hex(":")}')

        # If this is the correct handle and the status is success, the command was a success
        if uuid is GoProUuid.COMMAND_RSP_UUID and data[2] == 0x00:
            logging.info("Command sent successfully")
        # Anything else is unexpected. This shouldn't happen
        else:
            logging.error("Unexpected response")

        # Notify the writer
        event.set()

    client = await connect_ble(notification_handler, identifier)

    # Read from WiFi AP SSID BleUUID
    ssid_uuid = GoProUuid.WIFI_AP_SSID_UUID
    logging.info(f"Reading the WiFi AP SSID at {ssid_uuid}")
    ssid = (await client.read_gatt_char(ssid_uuid.value)).decode()
    logging.info(f"SSID is {ssid}")

    # Read from WiFi AP Password BleUUID
    password_uuid = GoProUuid.WIFI_AP_PASSWORD_UUID
    logging.info(f"Reading the WiFi AP password at {password_uuid}")
    password = (await client.read_gatt_char(password_uuid.value)).decode()
    logging.info(f"Password is {password}")

    # Write to the Command Request BleUUID to enable WiFi
    logging.info("Enabling the WiFi AP")
    event.clear()
    request = bytes([0x03, 0x17, 0x01, 0x01])
    command_request_uuid = GoProUuid.COMMAND_REQ_UUID
    logging.debug(f"Writing to {command_request_uuid}: {request.hex(':')}")
    await client.write_gatt_char(command_request_uuid.value, request, response=True)
    await event.wait()  # Wait to receive the notification response
    logging.info("WiFi AP is enabled")

    return ssid, password, client


def format_gopro_sd_card(ip_address: str):
    """
    Deletes all files on the GoPro SD Card.
    """
    url = f"http://{ip_address}/gp/gpControl/command/storage/delete/all"
    requests.get(url)

def _get_gopro_state(ip_address: str, root_ca: Optional[str] = None) -> Dict:
    """
    Get the current state of the GoPro camera.
    This function retrieves the camera's state via HTTP GET request.
    """
    scheme = "https" if root_ca else "http"
    url = f"{scheme}://{ip_address}/gopro/camera/state"

    try:
        response = requests.get(url, timeout=5, verify=root_ca or False)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Failed to get GoPro state from {ip_address}: {e}")
        return {}


class GoProUtilityThread(threading.Thread):
    def __init__(self, camera_config: Dict, exit_event: threading.Event):
        super().__init__(
            name=f"{camera_config.get('name', 'gopro')}_utility_thread", daemon=True
        )
        self.camera_config = camera_config
        self.exit_event = exit_event
        self.gopro_ip = camera_config.get("gopro_ip")
        self.gopro_root_ca = camera_config.get("gopro_root_ca")
        self.gopro_ble_identifier = camera_config.get("gopro_ble_identifier")
        self.poll_interval_s = camera_config.get("gopro_utility_poll_interval_s", 10)
        self.bluetooth_retry_delay_s = camera_config.get("gopro_bluetooth_retry_delay_s", 180) # Default to 3 minutes
        self.camera_state = {} # Global variable to store camera state
        self._ble_client = None  # To store the BleakClient instance

    def run(self):
        logging.info(f"Starting GoPro utility thread for {self.gopro_ip}")
        while not self.exit_event.is_set():
            try:
                # 1. Verify IP connectivity
                if not self._check_ip_connectivity():
                    logging.info(f"No IP connectivity to {self.gopro_ip}. Attempting to enable Wi-Fi AP via Bluetooth...")
                    asyncio.run(self._enable_wifi_ap())

                    # After attempting to enable Wi-Fi AP, poll for connectivity
                    # for the duration of bluetooth_retry_delay_s
                    start_time = time.time()
                    while not self.exit_event.is_set() and (time.time() - start_time) < self.bluetooth_retry_delay_s:
                        if self._check_ip_connectivity():
                            logging.info(f"IP connectivity to {self.gopro_ip} is now OK.")
                            break # Exit the polling loop if connected
                        logging.debug(f"Still no IP connectivity to {self.gopro_ip}. Retrying check in {self.poll_interval_s}s...")
                        self.exit_event.wait(self.poll_interval_s)

                    if not self._check_ip_connectivity(): # Final check after the polling loop
                        logging.warning(f"Failed to establish IP connectivity to {self.gopro_ip} after enabling Wi-Fi AP and polling.")
                    else:
                        logging.info(f"IP connectivity to {self.gopro_ip} is now OK.")
                else:
                    logging.debug(f"IP connectivity to {self.gopro_ip} is OK.")

                # 3. Gather the state of the camera and store it
                state = _get_gopro_state(
                    ip_address=self.gopro_ip, root_ca=self.gopro_root_ca
                )
                self.camera_state = state
                logging.debug(f"GoPro state for {self.gopro_ip}:\n{self.camera_state}")
                
                # Convert to human-readable format and log it
                human_readable_state = get_human_readable_state(self.camera_state)
                logging.info(f"Human-readable GoPro state for {self.gopro_ip}:\n{human_readable_state}")

                # Export to Prometheus
                for key, value in human_readable_state.items():
                    if isinstance(value, (int, float)):
                        if key in gopro_status_names.values():
                            gopro_state_gauge.labels(camera_name=self.camera_config.get('name', 'gopro'), state_name=key).set(value)
                        elif key in gopro_setting_names.values():
                            gopro_setting_gauge.labels(camera_name=self.camera_config.get('name', 'gopro'), setting_name=key).set(value)


            except Exception as e:
                logging.error(f"Error in GoPro utility thread for {self.gopro_ip}: {e}")

            self.exit_event.wait(self.poll_interval_s)
        logging.info(f"GoPro utility thread for {self.gopro_ip} exited.")

    async def _enable_wifi_ap(self):
        try:
            ssid, password, client = await enable_wifi()
            self._ble_client = client  # Store client for potential later disconnect
            logging.info(f"GoPro Wi-Fi AP enabled. SSID: {ssid}, Password: {password}")
        except Exception as e:
            logging.error(f"Failed to enable GoPro Wi-Fi AP via Bluetooth: {e}")

    def _check_ip_connectivity(self) -> bool:
        try:
            # Attempt to connect to the GoPro's HTTP port (default 80)
            with socket.create_connection((self.gopro_ip, 80), timeout=2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            logging.debug(f"TCP connection to {self.gopro_ip}:80 failed: {e}")
            return False
        except Exception as e:
            logging.error(
                f"Error checking IP connectivity to {self.gopro_ip} with TCP: {e}"
            )
            return False