import unittest
import os
import yaml
import tempfile
from unittest.mock import patch, MagicMock

# Add project root to allow importing fenetre
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the functions/classes to be tested
from fenetre import config_load, load_and_apply_configuration

# Mock absl.flags and absl.logging for standalone testing
# as fenetre.py relies on them being initialized.

# No longer need to mock absl.flags globally for FLAGS.config access in load_and_apply_configuration

# Mock only absl.logging at a high level if fenetre.py calls it at module import
mock_absl_logging_module = MagicMock()
sys.modules['absl.logging'] = mock_absl_logging_module

# Minimal stub for GoProUtilityThread if fenetre.py imports it and it causes issues
class MockGoProUtilityThread:
    def __init__(self, config, event):
        pass
    def start(self):
        pass
    def stop(self):
        pass
    def join(self, timeout=None):
        pass
    def is_alive(self):
        return False
sys.modules['gopro_utility'] = MagicMock(GoProUtilityThread=MockGoProUtilityThread)


class FenetreConfigTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_work_dir = self.temp_dir.name

        # Reset fenetre's global config state before each test if necessary
        # We will re-initialize them in tests that call load_and_apply_configuration
        if 'fenetre' in sys.modules:
            fenetre_module = sys.modules['fenetre']
            fenetre_module.server_config = {}
            fenetre_module.cameras_config = {}
            fenetre_module.global_config = {}
            fenetre_module.sleep_intervals = {}
            fenetre_module.active_camera_threads = {}
            fenetre_module.http_server_thread_global = None
            fenetre_module.http_server_instance = None
            if fenetre_module.exit_event: # If it was set by a previous test
                fenetre_module.exit_event.clear()


    def tearDown(self):
        self.temp_dir.cleanup()
        # Clean up any created PID file by fenetre during tests
        pid_file_path = os.environ.get("FENETRE_PID_FILE", "fenetre.pid")
        if os.path.exists(pid_file_path):
            try:
                os.remove(pid_file_path)
            except OSError:
                pass # Ignore if it's already gone or permissions issue in test env


    def _create_temp_config_file(self, data):
        fd, path = tempfile.mkstemp(suffix=".yaml", dir=self.temp_dir.name)
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f)
        return path

    def test_config_load_success(self):
        test_data = {
            "global": {"setting": "global_val", "work_dir": self.mock_work_dir},
            "http_server": {"port": 8080},
            "cameras": {"cam1": {"url": "http://cam1"}}
        }
        config_path = self._create_temp_config_file(test_data)

        server_conf, cameras_conf, global_conf, admin_server_conf = config_load(config_path)

        self.assertEqual(global_conf, test_data["global"])
        self.assertEqual(server_conf, test_data["http_server"])
        self.assertEqual(cameras_conf, test_data["cameras"])
        self.assertEqual(admin_server_conf, {})

    def test_config_load_missing_sections(self):
        test_data = {
            "global": {"setting": "global_val"}
            # http_server and cameras are missing
        }
        config_path = self._create_temp_config_file(test_data)

        server_conf, cameras_conf, global_conf, admin_server_conf = config_load(config_path)

        self.assertEqual(global_conf, test_data["global"])
        self.assertEqual(server_conf, {}) # Should default to empty dict
        self.assertEqual(cameras_conf, {}) # Should default to empty dict
        self.assertEqual(admin_server_conf, {})

    @patch('fenetre.logging') # Patch fenetre's imported logging object
    def test_config_load_file_not_found(self, mock_fenetre_logging):
        server_conf, cameras_conf, global_conf, admin_server_conf = config_load("non_existent_config.yaml")

        self.assertEqual(global_conf, {})
        self.assertEqual(server_conf, {})
        self.assertEqual(cameras_conf, {})
        mock_fenetre_logging.error.assert_called_with("Configuration file non_existent_config.yaml not found.")

    @patch('fenetre.logging') # Patch fenetre's imported logging object
    def test_config_load_invalid_yaml(self, mock_fenetre_logging):
        fd, path = tempfile.mkstemp(suffix=".yaml", dir=self.temp_dir.name)
        with os.fdopen(fd, "w") as f:
            f.write("global: setting: value\n  nested_setting: [1,2") # Invalid YAML

        server_conf, cameras_conf, global_conf, admin_server_conf = config_load(path)

        self.assertEqual(global_conf, {})
        self.assertEqual(server_conf, {})
        self.assertEqual(cameras_conf, {})
        # The exact error message from yaml.YAMLError can be complex and vary.
        # Checking that an error was logged and it contains key parts might be more robust.
        self.assertTrue(mock_fenetre_logging.error.called)
        args, _ = mock_fenetre_logging.error.call_args
        self.assertIn(f"Error parsing YAML configuration file {path}", args[0])
        self.assertIn("mapping values are not allowed here", args[0]) # Updated error string


    @patch('fenetre.copy_public_html_files')
    @patch('fenetre.update_cameras_metadata')
    @patch('fenetre.Thread') # Mock threads so they don't actually start
    @patch('fenetre.GoProUtilityThread') # Mock GoPro threads
    @patch('fenetre.server_run') # Mock server_run
    @patch('fenetre.stop_http_server')
    def test_load_and_apply_configuration_initial_load(self, mock_stop_http, mock_server_run, MockGoProThread, MockThread, mock_update_meta, mock_copy_files):
        # This test is more of an integration test for the config application logic,
        # focusing on variable updates and mock calls rather than actual thread behavior.
        fenetre_module = sys.modules['fenetre']

        # Set up FLAGS.config for fenetre.py
        test_data = {
            "global": {"work_dir": self.mock_work_dir, "timezone": "UTC"},
            "http_server": {"enabled": True, "port": 8080, "host": "0.0.0.0"},
            "cameras": {
                "cam1": {"url": "http://cam1", "snap_interval_s": 30},
                "cam2": {"gopro_ip": "10.5.5.9", "gopro_ble_identifier": "XXXX"}
            }
        }
        config_path = self._create_temp_config_file(test_data)
        # mock_flags_instance.config = config_path # No longer needed to set on mock

        # Initialize exit_event as it's used by GoProUtilityThread
        fenetre_module.exit_event = MagicMock()
        fenetre_module.exit_event.is_set.return_value = False

        # Call with config_file_override
        load_and_apply_configuration(initial_load=True, config_file_override=config_path)

        self.assertEqual(fenetre_module.global_config["work_dir"], self.mock_work_dir)
        self.assertEqual(fenetre_module.server_config["port"], 8080)
        self.assertIn("cam1", fenetre_module.cameras_config)
        self.assertIn("cam2", fenetre_module.cameras_config)

        mock_copy_files.assert_called_with(self.mock_work_dir, fenetre_module.global_config)
        mock_update_meta.assert_called_with(fenetre_module.cameras_config, self.mock_work_dir)

        # Check that sleep_intervals are initialized
        self.assertEqual(fenetre_module.sleep_intervals["cam1"], 30)
        self.assertEqual(fenetre_module.sleep_intervals["cam2"], 60.0) # Default if snap_interval_s not set

        # Check that threads were "started" (mocked)
        # Two camera watchdog manager threads + one HTTP server thread
        # MockThread is used for camera watchdogs and the http_server
        # MockGoProThread is used for GoPro utility

        # Expected calls to MockThread:
        # 1. cam1_watchdog (target=create_and_start_and_watch_thread)
        # 2. cam2_watchdog (target=create_and_start_and_watch_thread)
        # 3. http_server (target=server_run)
        self.assertEqual(MockThread.call_count, 3)

        # Check calls for GoProUtilityThread
        self.assertEqual(MockGoProThread.call_count, 1)
        MockGoProThread.assert_any_call(test_data["cameras"]["cam2"], fenetre_module.exit_event)

        # Check http server start
        mock_server_run_found = False
        for call_args in MockThread.call_args_list:
            if call_args[1].get('target') == mock_server_run:
                mock_server_run_found = True
                break
        self.assertTrue(mock_server_run_found, "server_run should have been a target for a Thread")


    @patch('fenetre.copy_public_html_files')
    @patch('fenetre.update_cameras_metadata')
    @patch('fenetre.Thread')
    @patch('fenetre.GoProUtilityThread')
    @patch('fenetre.server_run')
    @patch('fenetre.stop_http_server')
    def test_load_and_apply_configuration_reload_disable_server_remove_camera(self, mock_stop_http, mock_server_run, MockGoProThread, MockThread, mock_update_meta, mock_copy_files):
        fenetre_module = sys.modules['fenetre']

        # Initial config
        initial_data = {
            "global": {"work_dir": self.mock_work_dir, "timezone": "UTC"},
            "http_server": {"enabled": True, "port": 8080, "host": "0.0.0.0"},
            "cameras": {
                "cam1": {"url": "http://cam1", "snap_interval_s": 30},
                "cam_to_remove": {"url": "http://toberemoved"}
            }
        }
        config_path = self._create_temp_config_file(initial_data)
        # mock_flags_instance.config = config_path # No longer needed
        fenetre_module.exit_event = MagicMock()
        fenetre_module.exit_event.is_set.return_value = False

        # Mock initial state of threads
        mock_cam1_watchdog_manager = MagicMock(spec=sys.modules['threading'].Thread)
        mock_cam1_watchdog_manager.is_alive.return_value = True
        mock_cam_to_remove_watchdog_manager = MagicMock(spec=sys.modules['threading'].Thread)
        mock_cam_to_remove_watchdog_manager.is_alive.return_value = True

        fenetre_module.active_camera_threads = {
            "cam1": {"watchdog_manager_thread": mock_cam1_watchdog_manager, "watchdog_thread": MagicMock(is_alive=MagicMock(return_value=True))},
            "cam_to_remove": {"watchdog_manager_thread": mock_cam_to_remove_watchdog_manager, "watchdog_thread": MagicMock(is_alive=MagicMock(return_value=True))}
        }
        fenetre_module.sleep_intervals = {"cam1": 30, "cam_to_remove": 60}

        mock_http_thread = MagicMock(spec=sys.modules['threading'].Thread)
        mock_http_thread.is_alive.return_value = True
        fenetre_module.http_server_thread_global = mock_http_thread

        load_and_apply_configuration(initial_load=True, config_file_override=config_path) # Apply initial

        # Reset mocks for the reload part
        MockThread.reset_mock()
        MockGoProThread.reset_mock()
        mock_stop_http.reset_mock()
        mock_server_run.reset_mock() # server_run is a target for Thread, not called directly

        # New config: disable server, remove cam_to_remove
        reloaded_data = {
            "global": {"work_dir": self.mock_work_dir, "timezone": "UTC"},
            "http_server": {"enabled": False, "port": 8080, "host": "0.0.0.0"}, # Disabled
            "cameras": {
                "cam1": {"url": "http://cam1", "snap_interval_s": 20} # Interval changed
            }
        }
        config_path_reloaded = self._create_temp_config_file(reloaded_data)
        # mock_flags_instance.config = config_path_reloaded # No longer needed

        load_and_apply_configuration(initial_load=False, config_file_override=config_path_reloaded) # Apply reloaded config

        self.assertNotIn("cam_to_remove", fenetre_module.cameras_config)
        self.assertNotIn("cam_to_remove", fenetre_module.active_camera_threads)
        self.assertNotIn("cam_to_remove", fenetre_module.sleep_intervals)

        self.assertEqual(fenetre_module.server_config["enabled"], False)
        mock_stop_http.assert_called_once() # HTTP server should be stopped

        # Check if cam1's sleep interval was updated
        self.assertEqual(fenetre_module.sleep_intervals["cam1"], 20)

        # Cam1 thread should ideally be managed by its watchdog.
        # The test for create_and_start_and_watch_thread would cover camera thread lifecycle.
        # Here, we check that no new thread was started for cam1 if its watchdog manager was alive.
        # This part is tricky as load_and_apply_configuration starts *managers* for watchdogs.
        # If the manager for cam1 was already running, it shouldn't start a new one.

        # Assert that no new server thread was started
        server_run_targeted = any(call_args[1].get('target') == mock_server_run for call_args in MockThread.call_args_list)
        self.assertFalse(server_run_targeted, "server_run should not have been targeted by a new Thread on reload when server is disabled.")

        # Cam_to_remove's original watchdog manager thread should have been joined
        # This requires the mock thread to have a join method.
        mock_cam_to_remove_watchdog_manager.join.assert_called_with(timeout=5)


if __name__ == '__main__':
    # Need to setup absl flags before running tests if fenetre.py uses app.run() or defines its own flags
    # For this setup, we are mocking FLAGS directly.
    unittest.main()
