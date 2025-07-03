import sys
import os
import threading
import time
import requests
import socket
import asyncio
from typing import Dict, Optional
from absl import logging


from resources.OpenGoPro.demos.python.tutorial.tutorial_modules import enable_wifi


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
