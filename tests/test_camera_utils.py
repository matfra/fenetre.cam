import unittest
from unittest.mock import patch, MagicMock
import piexif
from fenetre.camera_utils import (  # type: ignore
    check_and_switch_day_night_mode,
    get_day_night_from_exif,
    set_camera_mode,
    send_url_commands,
    camera_modes,
)


class TestCameraUtils(unittest.TestCase):
    def setUp(self):
        # Reset camera_modes before each test
        camera_modes.clear()

    @patch("fenetre.camera_utils.get_exif_dict")
    @patch("fenetre.camera_utils.set_camera_mode")
    def test_switch_to_night_mode(self, mock_send_url_commands):
        # This is now an integration test for check_and_switch_day_night_mode
        camera_name = "test_cam"
        camera_config = {
            "night_settings": {
                "trigger_iso": 100,
                "url_commands": ["/night_mode"],
            }
        }
        exif_data = b"dummy_exif_data"
        mock_send_url_commands.return_value = {"iso": 200}

        check_and_switch_day_night_mode(camera_name, camera_config, exif_data)

        mock_send_url_commands.assert_called_once_with(
            camera_name, camera_config, "night", None
        )

    # New unit tests for the refactored functions

    @patch("fenetre.camera_utils.send_url_commands") # type: ignore
    def test_switch_to_day_mode(self, mock_send_url_commands):
        camera_name = "test_cam"
        camera_modes[camera_name] = "night"  # Start in night mode
        camera_config = {
            "day_settings": {
                "trigger_exposure_time_s": 0.005,
                "url_commands": ["/day_mode"],
            }
        }
        # Exposure time of 1/250s = 4ms
        exif_dict = {"exposure_time": 1 / 250}

        new_mode = get_day_night_from_exif(exif_dict, camera_config, "night")
        self.assertEqual(new_mode, "day")

        set_camera_mode(camera_name, camera_config, new_mode, gopro_instance=None)
        mock_send_url_commands.assert_called_once_with(camera_name, camera_config, ["/day_mode"])
        self.assertEqual(camera_modes[camera_name], "day")

    @patch("fenetre.camera_utils.send_url_commands") # type: ignore
    def test_no_switch_needed(self, mock_send_url_commands):
        camera_name = "test_cam"
        camera_modes[camera_name] = "day"
        camera_config = {
            "day_settings": {"trigger_exposure_time_s": 0.005},
            "night_settings": {"trigger_iso": 400},
        }
        # ISO is not high enough, exposure is not low enough
        exif_dict = {"iso": 200, "exposure_time": 1 / 100}

        new_mode = get_day_night_from_exif(exif_dict, camera_config, "day")
        self.assertEqual(new_mode, "day")

        set_camera_mode(camera_name, camera_config, new_mode)
        mock_send_url_commands.assert_not_called()

    @patch("fenetre.camera_utils.send_url_commands") # type: ignore
    def test_no_exif_data(self, mock_send_url_commands):
        check_and_switch_day_night_mode("test_cam", {}, None)
        mock_send_url_commands.assert_not_called()

    @patch("fenetre.camera_utils.get_exif_dict")
    def test_no_settings_configured(self, mock_get_exif_dict):
        mock_get_exif_dict.return_value = {"iso": 800}
        check_and_switch_day_night_mode("test_cam", {}, b"dummy_exif")
        # No assertion needed, just checking it doesn't crash and returns early.

    @patch("requests.get") # type: ignore
    def test_send_url_commands_generic_camera(self, mock_requests_get):
        camera_name = "generic_cam"
        camera_config = {"url": "http://1.2.3.4/camera"}
        commands = ["/cmd1", "/cmd2"]

        send_url_commands(camera_name, camera_config, commands)

        self.assertEqual(mock_requests_get.call_count, 2)
        mock_requests_get.assert_any_call("http://1.2.3.4/cmd1", timeout=5)
        mock_requests_get.assert_any_call("http://1.2.3.4/cmd2", timeout=5)


if __name__ == "__main__":
    unittest.main()
