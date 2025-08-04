"""Utility functions for GoPro 11+

Most of the code here is copied from tutorial modules at https://github.com/gopro/OpenGoPro.git
"""

import asyncio
import enum
import re
import socket
import threading
import time
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

import requests
from absl import logging
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice as BleakDevice

from fenetre.gopro_state_map import GoProEnums
from fenetre.admin_server import gopro_setting_gauge, gopro_state_gauge

T = TypeVar("T")

GOPRO_BASE_UUID = "b5f9{}-aa8d-11e3-9046-0002a5d5c51b"
noti_handler_T = Callable[[BleakGATTCharacteristic, bytearray], Awaitable[None]]


def get_human_readable_state(state: Dict) -> Dict:
    """
    Converts a numerical GoPro state dictionary to a human-readable one.
    """
    human_readable_state = {}
    # Process statuses
    if "status" in state:
        for key, value in state["status"].items():
            key = int(key)
            status_name = GoProEnums.STATUS_NAMES.get(key, f"Unknown Status ({key})")
            if key in GoProEnums.STATUS_VALUES:
                value_name = GoProEnums.STATUS_VALUES[key].get(
                    value, f"Unknown Value ({value})"
                )
            else:
                value_name = value
            human_readable_state[status_name] = value_name

    # Process settings
    if "settings" in state:
        for key, value in state["settings"].items():
            key = int(key)
            setting_name = GoProEnums.SETTING_NAMES.get(key, f"Unknown Setting ({key})")
            if key in GoProEnums.SETTING_VALUES:
                value_name = GoProEnums.SETTING_VALUES[key].get(
                    value, f"Unknown Value ({value})"
                )
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
    def dict_by_uuid(
        cls, value_creator: Callable[["GoProUuid"], T]
    ) -> dict["GoProUuid", T]:
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


async def connect_ble(
    notification_handler: noti_handler_T, identifier: str | None = None
) -> BleakClient:
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
                for device in await BleakScanner.discover(
                    timeout=5, detection_callback=_scan_callback
                ):
                    if device.name and device.name != "Unknown":
                        devices[device.name] = device
                # Log every device we discovered
                for d in devices:
                    logging.info(f"\tDiscovered: {d}")
                # Now look for our matching device(s)
                token = re.compile(identifier or r"GoPro [A-Z0-9]{4}")
                matched_devices = [
                    device for name, device in devices.items() if token.match(name)
                ]
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

    async def notification_handler(
        characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
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
    def __init__(
        self,
        gopro,
        camera_name: str,
        camera_config: Dict,
        exit_event: threading.Event,
    ):
        from fenetre.gopro import GoPro
        super().__init__(
            name=f"{camera_config.name}_utility_thread", daemon=True
        )
        self.gopro = gopro
        self.camera_name = camera_name
        self.camera_config = camera_config
        self.exit_event = exit_event
        self.gopro_ip = camera_config.gopro_ip
        self.gopro_ble_identifier = camera_config.gopro_ble_identifier
        self.poll_interval_s = camera_config.gopro_utility_poll_interval_s
        self.bluetooth_retry_delay_s = camera_config.get(
            "gopro_bluetooth_retry_delay_s", 180
        )  # Default to 3 minutes
        self._ble_client = None  # To store the BleakClient instance

    def run(self):
        logging.info(f"Starting GoPro utility thread for {self.gopro_ip}")
        self.gopro.validate_presets()
        while not self.exit_event.is_set():
            try:
                # 1. Verify IP connectivity
                if not self._check_ip_connectivity():
                    logging.info(
                        f"No IP connectivity to {self.gopro_ip}. Attempting to enable Wi-Fi AP via Bluetooth..."
                    )
                    asyncio.run(self._enable_wifi_ap())

                    # After attempting to enable Wi-Fi AP, poll for connectivity
                    # for the duration of bluetooth_retry_delay_s
                    start_time = time.time()
                    while (
                        not self.exit_event.is_set()
                        and (time.time() - start_time) < self.bluetooth_retry_delay_s
                    ):
                        if self._check_ip_connectivity():
                            logging.info(
                                f"IP connectivity to {self.gopro_ip} is now OK."
                            )
                            break  # Exit the polling loop if connected
                        logging.debug(
                            f"Still no IP connectivity to {self.gopro_ip}. Retrying check in {self.poll_interval_s}s..."
                        )
                        self.exit_event.wait(self.poll_interval_s)

                    if (
                        not self._check_ip_connectivity()
                    ):  # Final check after the polling loop
                        logging.warning(
                            f"Failed to establish IP connectivity to {self.gopro_ip} after enabling Wi-Fi AP and polling."
                        )
                    else:
                        logging.info(f"IP connectivity to {self.gopro_ip} is now OK.")
                else:
                    logging.debug(f"IP connectivity to {self.gopro_ip} is OK.")

                # 3. Gather the state of the camera and store it
                self.gopro.update_state()
                logging.debug(f"GoPro state for {self.gopro_ip}:\n{self.gopro.state}")

                # Convert to human-readable format and log it
                human_readable_state = get_human_readable_state(self.gopro.state)
                logging.debug(
                    f"Human-readable GoPro state for {self.gopro_ip}:\n{human_readable_state}"
                )

                # Export to Prometheus
                for key, value in human_readable_state.items():
                    if isinstance(value, (int, float)):
                        if key in GoProEnums.STATUS_NAMES.values():
                            gopro_state_gauge.labels(
                                camera_name=self.camera_name, state_name=key
                            ).set(value)
                        elif key in GoProEnums.SETTING_NAMES.values():
                            gopro_setting_gauge.labels(
                                camera_name=self.camera_name, setting_name=key
                            ).set(value)

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
