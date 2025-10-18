import unittest
from unittest.mock import patch, MagicMock
import piexif
from fenetre.camera_utils import (
    check_and_switch_day_night_mode,
    send_url_commands,
    camera_modes,
)


class TestCameraUtils(unittest.TestCase):
    def setUp(self):
        # Reset camera_modes before each test
        camera_modes.clear()

    def _create_exif(self, iso=None, exposure_time=None):
        exif_dict = {"Exif": {}}
        if iso:
            exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings] = iso
        if exposure_time:
            # exposure_time is a tuple of (numerator, denominator)
            exif_dict["Exif"][piexif.ExifIFD.ExposureTime] = exposure_time
        return piexif.dump(exif_dict)

    @patch("fenetre.camera_utils.send_url_commands")
    def test_switch_to_night_mode(self, mock_send_url_commands):
        camera_name = "test_cam"
        camera_config = {
            "night_settings": {
                "trigger_iso": 100,
                "url_commands": ["/night_mode"],
            }
        }
        exif_data = self._create_exif(iso=200)

        check_and_switch_day_night_mode(camera_name, camera_config, exif_data)

        mock_send_url_commands.assert_called_once_with(
            camera_name, camera_config, ["/night_mode"], None
        )
        self.assertEqual(camera_modes[camera_name], "night")

    @patch("fenetre.camera_utils.send_url_commands")
    def test_switch_to_day_mode(self, mock_send_url_commands):
        camera_name = "test_cam"
        camera_modes[camera_name] = "night"  # Start in night mode
        camera_config = {
            "day_settings": {
                "trigger_exposure_time_ms": 5,
                "url_commands": ["/day_mode"],
            }
        }
        # Exposure time of 1/250s = 4ms
        exif_data = self._create_exif(exposure_time=(1, 250))

        check_and_switch_day_night_mode(camera_name, camera_config, exif_data)

        mock_send_url_commands.assert_called_once_with(
            camera_name, camera_config, ["/day_mode"], None
        )
        self.assertEqual(camera_modes[camera_name], "day")

    @patch("fenetre.camera_utils.send_url_commands")
    def test_no_switch_needed(self, mock_send_url_commands):
        camera_name = "test_cam"
        camera_modes[camera_name] = "day"
        camera_config = {
            "day_settings": {"trigger_exposure_time_ms": 5},
            "night_settings": {"trigger_iso": 400},
        }
        # ISO is not high enough, exposure is not low enough
        exif_data = self._create_exif(iso=200, exposure_time=(1, 100))

        check_and_switch_day_night_mode(camera_name, camera_config, exif_data)

        mock_send_url_commands.assert_not_called()
        self.assertEqual(camera_modes[camera_name], "day")

    @patch("fenetre.camera_utils.send_url_commands")
    def test_no_exif_data(self, mock_send_url_commands):
        check_and_switch_day_night_mode("test_cam", {}, None)
        mock_send_url_commands.assert_not_called()

    @patch("fenetre.camera_utils.send_url_commands")
    def test_no_settings_configured(self, mock_send_url_commands):
        exif_data = self._create_exif(iso=800)
        check_and_switch_day_night_mode("test_cam", {}, exif_data)
        mock_send_url_commands.assert_not_called()

    @patch("requests.get")
    def test_send_url_commands_generic_camera(self, mock_requests_get):
        camera_name = "generic_cam"
        camera_config = {"url": "http://1.2.3.4/camera"}
        commands = ["/cmd1", "/cmd2"]

        send_url_commands(camera_name, camera_config, commands)

        self.assertEqual(mock_requests_get.call_count, 2)
        mock_requests_get.assert_any_call("http://1.2.3.4/cmd1", timeout=5)
        mock_requests_get.assert_any_call("http://1.2.3.4/cmd2", timeout=5)

    def test_send_url_commands_gopro(self):
        mock_gopro = MagicMock()
        camera_name = "gopro_cam"
        commands = ["/gp/gpControl/command/mode?p=1", "/gp/gpControl/setting/21/1"]

        send_url_commands(camera_name, {}, commands, gopro_instance=mock_gopro)

        self.assertEqual(mock_gopro._make_gopro_request.call_count, 2)
        mock_gopro._make_gopro_request.assert_any_call(
            "/gp/gpControl/command/mode?p=1"
        )
        mock_gopro._make_gopro_request.assert_any_call("/gp/gpControl/setting/21/1")


if __name__ == "__main__":
    unittest.main()
