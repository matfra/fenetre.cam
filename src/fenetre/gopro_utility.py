"""Utility functions for GoPro 11+

Most of the code here is copied from tutorial modules at https://github.com/gopro/OpenGoPro.git
"""

import asyncio
import enum
import logging
import socket
import threading
import time
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

import requests
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice as BleakDevice

from fenetre.gopro_state_map import GoProEnums
from fenetre.admin_server import gopro_setting_gauge, gopro_state_gauge

T = TypeVar("T")

GOPRO_BASE_UUID = "b5f9{}-aa8d-11e3-9046-0002a5d5c51b"
noti_handler_T = Callable[[BleakGATTCharacteristic, bytearray], Awaitable[None]]

logger = logging.getLogger(__name__)


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
    logger.error(f"Caught exception {str(loop)}: {msg}")
    logger.critical("This is unexpected and unrecoverable.")


async def connect_ble(
    notification_handler: noti_handler_T,
    identifier: str | None = None,
    adapter: str | None = None,
) -> BleakClient:
    """Connect to a GoPro, then pair, and enable notifications

    If identifier is None, the first discovered GoPro will be connected to.

    Retry forever

    Args:
        notification_handler (noti_handler_T): callback when notification is received
        identifier (str, optional): Last 4 digits of GoPro serial number. Defaults to None.
        adapter (str, optional): bluetooth adapter to use. Defaults to None.

    Returns:
        BleakClient: connected client
    """

    asyncio.get_event_loop().set_exception_handler(exception_handler)

    retry_count = 0
    while True:
        time.sleep(5)
        retry_count += 1
        try:
            device: BleakDevice | None = None
            # Scan until we find a device
            while device is None:
                devices: dict[str, BleakDevice] = {}
                logger.info("Scanning for bluetooth devices...")
                if adapter:
                    logger.info(f"Using bluetooth adapter: {adapter}")

                # Scan callback to also catch nonconnectable scan responses
                def _scan_callback(scanned_device: BleakDevice, _: Any) -> None:
                    # Add to the dict if not unknown
                    if scanned_device.name and scanned_device.name != "Unknown":
                        devices[scanned_device.name] = scanned_device

                # Discover devices
                await BleakScanner.discover(
                    timeout=5, detection_callback=_scan_callback, adapter=adapter
                )

                # Log every device we discovered
                for d_name in devices:
                    logger.info(f"	Discovered: {d_name}")

                # Look for a matching device
                if identifier:
                    id_str = str(identifier)
                    for name, found_device in devices.items():
                        if id_str in name:
                            device = found_device
                            logger.info(
                                f"Found matching device by identifier '{id_str}': {name}"
                            )
                            break
                else:
                    for name, found_device in devices.items():
                        if name.startswith("GoPro"):
                            device = found_device
                            logger.info(f"Found first available GoPro: {name}")
                            break

                if not device:
                    logger.warning("No matching GoPro found. Retrying scan...")

            logger.info(f"Establishing BLE connection to {device}...")
            client = BleakClient(device, adapter=adapter)
            await client.connect(timeout=15)
            logger.info("BLE Connected!")

            # Try to pair (on some OS's this will expectedly fail)
            logger.info("Attempting to pair...")
            try:
                await client.pair()
            except NotImplementedError:
                # This is expected on Mac
                pass
            logger.info("Pairing complete!")

            # Enable notifications on all notifiable characteristics
            logger.info("Enabling notifications...")
            for service in client.services:
                for char in service.characteristics:
                    if "notify" in char.properties:
                        logger.info(f"Enabling notification on char {char.uuid}")
                        await client.start_notify(char, notification_handler)
            logger.info("Done enabling notifications")
            logger.info("BLE Connection is ready for communication.")

            return client
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error(f"Connection establishment failed: {exc}")
            logger.warning(f"Retrying #{retry_count}")


async def enable_wifi(
    identifier: str | None = None,
    adapter: str | None = None,
) -> tuple[str, str, BleakClient]:
    """Connect to a GoPro via BLE, find its WiFi AP SSID and password, and enable its WiFI AP

    If identifier is None, the first discovered GoPro will be connected to.

    Args:
        identifier (str, optional): Last 4 digits of GoPro serial number. Defaults to None.
        adapter (str, optional): bluetooth adapter to use. Defaults to None.

    Returns:
        Tuple[str, str]: ssid, password
    """
    # Synchronization event to wait until notification response is received
    event = asyncio.Event()
    client: BleakClient

    async def notification_handler(
        characteristic: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        uuid = GoProUuid(client.services.characteristics[characteristic.handle].uuid)
        logger.info(f'Received response at {uuid}: {data.hex(":")}')

        # If this is the correct handle and the status is success, the command was a success
        if uuid is GoProUuid.COMMAND_RSP_UUID and data[2] == 0x00:
            logger.info("Command sent successfully")
        # Anything else is unexpected. This shouldn't happen
        else:
            logger.error("Unexpected response")

        # Notify the writer
        event.set()

    client = await connect_ble(notification_handler, identifier, adapter)

    # Read from WiFi AP SSID BleUUID
    ssid_uuid = GoProUuid.WIFI_AP_SSID_UUID
    logger.info(f"Reading the WiFi AP SSID at {ssid_uuid}")
    ssid = (await client.read_gatt_char(ssid_uuid.value)).decode()
    logger.info(f"SSID is {ssid}")

    # Read from WiFi AP Password BleUUID
    password_uuid = GoProUuid.WIFI_AP_PASSWORD_UUID
    logger.info(f"Reading the WiFi AP password at {password_uuid}")
    password = (await client.read_gatt_char(password_uuid.value)).decode()
    logger.info(f"Password is {password}")

    # Write to the Command Request BleUUID to enable WiFi
    logger.info("Enabling the WiFi AP")
    event.clear()
    request = bytes([0x03, 0x17, 0x01, 0x01])
    command_request_uuid = GoProUuid.COMMAND_REQ_UUID
    logger.debug(f"Writing to {command_request_uuid}: {request.hex(':')}")
    await client.write_gatt_char(command_request_uuid.value, request, response=True)
    await event.wait()  # Wait to receive the notification response
    logger.info("WiFi AP is enabled")

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
        logger.error(f"Failed to get GoPro state from {ip_address}: {e}")
        return {{}}


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
            name=f"{camera_config.get('name', 'gopro')}_utility_thread", daemon=True
        )
        self.gopro = gopro
        self.camera_name = camera_name
        self.camera_config = camera_config
        self.exit_event = exit_event
        self.gopro_ip = camera_config.get("gopro_ip")
        self.gopro_ble_identifier = camera_config.get("gopro_ble_identifier")
        self.bluetooth_adapter = camera_config.get("bluetooth_adapter")
        self.poll_interval_s = camera_config.get("gopro_utility_poll_interval_s", 10)
        self.bluetooth_retry_delay_s = camera_config.get(
            "gopro_bluetooth_retry_delay_s", 180
        )  # Default to 3 minutes
        self._ble_client = None  # To store the BleakClient instance
        self.usb_control = camera_config.get("usb_control", False)

    def run(self):
        logger.info(f"Starting GoPro utility thread for {self.gopro_ip}")
        # TODO: Move this further down: self.gopro.validate_presets()
        while not self.exit_event.is_set():
            try:
                # 1. Verify IP connectivity
                if not self._check_ip_connectivity():
                    if self.usb_control:
                        logger.info(
                            "No IP connectivity. USB control is enabled. Sending BLE keepalive to wake up camera..."
                        )
                        asyncio.run(self._send_ble_keepalive())
                    else:
                        logger.info(
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
                            logger.info(
                                f"IP connectivity to {self.gopro_ip} is now OK."
                            )
                            break  # Exit the polling loop if connected
                        logger.debug(
                            f"Still no IP connectivity to {self.gopro_ip}. Retrying check in {self.poll_interval_s}s..."
                        )
                        self.exit_event.wait(self.poll_interval_s)

                    if (
                        not self._check_ip_connectivity()
                    ):  # Final check after the polling loop
                        logger.warning(
                            f"Failed to establish IP connectivity to {self.gopro_ip} after enabling Wi-Fi AP and polling."
                        )
                    else:
                        logger.info(f"IP connectivity to {self.gopro_ip} is now OK.")
                else:
                    logger.debug(f"IP connectivity to {self.gopro_ip} is OK.")

                # 3. Gather the state of the camera and store it
                self.gopro.update_state()
                logger.debug(f"GoPro state for {self.gopro_ip}:\n{self.gopro.state}")

                # Convert to human-readable format and log it
                human_readable_state = get_human_readable_state(self.gopro.state)
                logger.debug(
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
                logger.error(f"Error in GoPro utility thread for {self.gopro_ip}: {e}")

            self.exit_event.wait(self.poll_interval_s)
        logger.info(f"GoPro utility thread for {self.gopro_ip} exited.")

    async def _enable_wifi_ap(self):
        try:
            ssid, password, client = await enable_wifi(
                identifier=self.gopro_ble_identifier, adapter=self.bluetooth_adapter
            )
            self._ble_client = client  # Store client for potential later disconnect
            logger.info(f"GoPro Wi-Fi AP enabled. SSID: {ssid}, Password: {password}")
        except Exception as e:
            logger.error(f"Failed to enable GoPro Wi-Fi AP via Bluetooth: {e}")


    async def _send_ble_keepalive(self):
        try:
            # Synchronization event to wait until notification response is received
            event = asyncio.Event()
            client: BleakClient

            async def notification_handler(
                characteristic: BleakGATTCharacteristic,
                data: bytearray,
            ) -> None:
                uuid = GoProUuid(
                    client.services.characteristics[characteristic.handle].uuid
                )
                logger.info(f'Received response at {uuid}: {data.hex(":")}')

                # If this is the correct handle and the status is success, the command was a success
                if uuid is GoProUuid.COMMAND_RSP_UUID and data[2] == 0x00:
                    logger.info("Command sent successfully")
                # Anything else is unexpected. This shouldn't happen
                else:
                    logger.error("Unexpected response")

                # Notify the writer
                event.set()

            client = await connect_ble(
                notification_handler, self.gopro_ble_identifier, self.bluetooth_adapter
            )
            self._ble_client = client  # Store client for potential later disconnect

            # Write to the Command Request BleUUID to send keepalive
            logger.info("Sending BLE keepalive")
            event.clear()
            request = bytes([0x03, 0x5B, 0x01, 0x42])
            command_request_uuid = GoProUuid.COMMAND_REQ_UUID
            logger.debug(f"Writing to {command_request_uuid}: {request.hex(':')}")
            await client.write_gatt_char(
                command_request_uuid.value, request, response=True
            )
            await event.wait()  # Wait to receive the notification response
            logger.info("BLE keepalive sent.")
        except Exception as e:
            logger.error(f"Failed to send BLE keepalive: {e}")

    def _check_ip_connectivity(self) -> bool:
        try:
            # Attempt to connect to the GoPro's HTTP port (default 80)
            with socket.create_connection((self.gopro_ip, 80), timeout=2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            logger.debug(f"TCP connection to {self.gopro_ip}:80 failed: {e}")
            return False
        except Exception as e:
            logger.error(
                f"Error checking IP connectivity to {self.gopro_ip} with TCP: {e}"
            )
            return False
