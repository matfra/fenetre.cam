import sys
import os
import threading
import time
import requests
import asyncio
from typing import Dict, Optional
from absl import logging

from gopro import get_gopro_state

sys.path.append(os.path.join(os.path.dirname(__file__), "resources", "OpenGoPro", "demos", "python", "tutorial", "tutorial_modules"))
from enable_wifi_ap import enable_wifi

class GoProUtilityThread(threading.Thread):
    def __init__(self, camera_config: Dict, exit_event: threading.Event):
        super().__init__(name=f"{camera_config.get('name', 'gopro')}_utility_thread", daemon=True)
        self.camera_config = camera_config
        self.exit_event = exit_event
        self.gopro_ip = camera_config.get("gopro_ip")
        self.gopro_root_ca = camera_config.get("gopro_root_ca")
        self.gopro_ble_identifier = camera_config.get("gopro_ble_identifier")
        self.poll_interval_s = camera_config.get("gopro_utility_poll_interval_s", 10)
        self.camera_state = {} # Global variable to store camera state
        self._ble_client = None # To store the BleakClient instance

    def run(self):
        logging.info(f"Starting GoPro utility thread for {self.gopro_ip}")
        while not self.exit_event.is_set():
            try:
                # 1. Verify IP connectivity
                if not self._check_ip_connectivity():
                    logging.info(f"No IP connectivity to {self.gopro_ip}. Attempting to enable Wi-Fi AP via Bluetooth...")
                    # 2. Bluetooth commands to enable wifi AP mode
                    # This part needs to run in an asyncio event loop
                    asyncio.run(self._enable_wifi_ap())
                    # After enabling, re-check IP connectivity
                    if not self._check_ip_connectivity():
                        logging.warning(f"Failed to establish IP connectivity to {self.gopro_ip} after enabling Wi-Fi AP.")
                        self.exit_event.wait(self.poll_interval_s)
                        continue
                    logging.info(f"IP connectivity to {self.gopro_ip} is now OK.")
                else:
                    logging.info(f"IP connectivity to {self.gopro_ip} is OK.")

                # 3. Gather the state of the camera and store it
                state = get_gopro_state(
                    ip_address=self.gopro_ip,
                    root_ca=self.gopro_root_ca
                )
                self.camera_state = state
                logging.debug(f"GoPro state for {self.gopro_ip}:\n{self.camera_state}")

            except Exception as e:
                logging.error(f"Error in GoPro utility thread for {self.gopro_ip}: {e}")

            self.exit_event.wait(self.poll_interval_s)
        logging.info(f"GoPro utility thread for {self.gopro_ip} exited.")

    async def _enable_wifi_ap(self):
        try:
            ssid, password, client = await enable_wifi(self.gopro_ble_identifier)
            self._ble_client = client # Store client for potential later disconnect
            logging.info(f"GoPro Wi-Fi AP enabled. SSID: {ssid}, Password: {password}")
        except Exception as e:
            logging.error(f"Failed to enable GoPro Wi-Fi AP via Bluetooth: {e}")

    def _check_ip_connectivity(self) -> bool:
        try:
            # Attempt to connect to a known GoPro endpoint
            response = requests.get(f"http://{self.gopro_ip}/gopro/camera/state", timeout=2)
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False
        except Exception as e:
            logging.error(f"Error checking IP connectivity to {self.gopro_ip}: {e}")
            return False
