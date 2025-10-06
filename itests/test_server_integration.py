import os
import sys
import tempfile
import unittest
import time
import requests
import yaml
import socket
from contextlib import closing
from prometheus_client import REGISTRY

# Add project root to allow importing fenetre
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.fenetre.fenetre import load_and_apply_configuration, shutdown_application, exit_event

class ServerIntegrationTest(unittest.TestCase):

    def setUp(self):
        # Reset Prometheus registry
        collectors = list(REGISTRY._collector_to_names.keys())
        for collector in collectors:
            REGISTRY.unregister(collector)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = self.temp_dir.name
        self.config_path = os.path.join(self.work_dir, "config.yaml")
        self.test_content = "<html><body>Hello, test!</body></html>"
        self.test_page_path = os.path.join(self.work_dir, "test.html")

        with open(self.test_page_path, "w") as f:
            f.write(self.test_content)

        # Find a free port
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.port = s.getsockname()[1]

        self.config_data = {
            "global": {"work_dir": self.work_dir},
            "http_server": {
                "enabled": True,
                "listen": f"127.0.0.1:{self.port}",
            },
            "cameras": {},
            "admin_server": { "enabled": False },
            "timelapse": { "enabled": False },
        }

        with open(self.config_path, "w") as f:
            yaml.dump(self.config_data, f)

        # Reset fenetre's global state before each test
        if "fenetre.fenetre" in sys.modules:
            fenetre_module = sys.modules["src.fenetre.fenetre"]
            fenetre_module.server_config = {}
            fenetre_module.cameras_config = {}
            fenetre_module.global_config = {}
            fenetre_module.sleep_intervals = {}
            fenetre_module.active_camera_threads = {}
            fenetre_module.http_server_thread_global = None
            fenetre_module.http_server_instance = None
            # Initialize all global thread variables that shutdown_application touches
            fenetre_module.timelapse_thread_global = None
            fenetre_module.daylight_thread_global = None
            fenetre_module.archive_thread_global = None
            fenetre_module.frequent_timelapse_loop_thread_global = None
            fenetre_module.admin_server_thread_global = None
            if hasattr(fenetre_module, "exit_event") and fenetre_module.exit_event:
                fenetre_module.exit_event.clear()


    def tearDown(self):
        shutdown_application()
        self.temp_dir.cleanup()
        pid_file_path = os.environ.get("FENETRE_PID_FILE", "fenetre.pid")
        if os.path.exists(pid_file_path):
            try:
                os.remove(pid_file_path)
            except OSError:
                pass

    def test_http_server_serves_content(self):
        load_and_apply_configuration(initial_load=True, config_file_override=self.config_path)

        # Give the server a moment to start up
        time.sleep(1)

        try:
            response = requests.get(f"http://127.0.0.1:{self.port}/test.html", timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, self.test_content)
        except requests.exceptions.ConnectionError as e:
            self.fail(f"HTTP server did not start or is not listening. Connection error: {e}")


if __name__ == "__main__":
    unittest.main()
