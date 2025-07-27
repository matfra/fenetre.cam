import os
import sys
import unittest
from unittest import mock
import json


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fenetre import gopro

class TestGoPro(unittest.TestCase):
    """Test suite for GoPro camera functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.gopro = gopro.GoPro()

    @mock.patch("fenetre.gopro.requests.get")
    def test_set_setting_success(self, mock_get):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        self.gopro.settings.video_performance_mode = "Maximum Video Performance"
        mock_get.assert_called_with(
            "http://10.5.5.9/gopro/camera/setting?option=0&setting=173",
            timeout=5,
            verify="",
        )

        self.gopro.settings.max_lens = "On"
        mock_get.assert_called_with(
            "http://10.5.5.9/gopro/camera/setting?option=1&setting=162",
            timeout=5,
            verify="",
        )

    def test_set_invalid_setting(self):
        with self.assertRaises(AttributeError):
            self.gopro.settings.invalid_setting = "some_value"

    def test_set_invalid_value(self):
        with self.assertRaises(ValueError):
            self.gopro.settings.video_performance_mode = "invalid_value"

    @mock.patch("fenetre.gopro.GoPro._get_latest_file")
    @mock.patch("fenetre.gopro.requests.get")
    def test_capture_photo(self, mock_get, mock_get_latest_file):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_response.content = b"test_jpeg_content"
        mock_get.return_value = mock_response

        mock_get_latest_file.side_effect = [
            ("100GOPRO", "GOPR0001.JPG"),
            ("100GOPRO", "GOPR0002.JPG"),
        ]

        content = self.gopro.capture_photo()

        self.assertEqual(content, b"test_jpeg_content")

        expected_calls = [
            mock.call(
                "http://10.5.5.9/gopro/camera/control/set_ui_controller?p=2",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=1&setting=175",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=10&setting=88",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=4&setting=91",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=0&setting=83",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=7&setting=59",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/shutter/start", timeout=5, verify=""
            ),
            mock.call(
                "http://10.5.5.9/videos/DCIM/100GOPRO/GOPR0002.JPG",
                timeout=5,
                verify="",
            ),
            mock.call().raise_for_status(),
            mock.call(
                "http://10.5.5.9/gopro/media/delete/file?path=100GOPRO/GOPR0002.JPG",
                timeout=5,
                verify="",
            ),
        ]
        mock_get.assert_has_calls(expected_calls, any_order=False)

    @mock.patch("fenetre.gopro.requests.get")
    def test_update_state(self, mock_get):
        import json

        gopro_state_path = os.path.join(os.path.dirname(__file__), "goprostate.json")
        with open(gopro_state_path) as f:
            mock_state = json.load(f)

        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_state
        mock_get.return_value = mock_response

        self.gopro.update_state()

        mock_get.assert_called_once_with(
            "http://10.5.5.9/gopro/camera/state", timeout=5, verify=""
        )
        self.assertEqual(self.gopro.state, mock_state)

    @mock.patch("fenetre.gopro.requests.get")
    def test_get_presets(self, mock_get):

        gopro_presets_path = os.path.join(
            os.path.dirname(__file__), "gopro_presets_get.json"
        )
        with open(gopro_presets_path) as f:
            mock_presets = json.load(f)

        gopro_expected_photo_presets_path = os.path.join(
            os.path.dirname(__file__), "goprohero11_photo_presets.json"
        )
        with open(gopro_expected_photo_presets_path) as f:
            expected_photo_presets = json.load(f)

        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_presets
        mock_get.return_value = mock_response

        available_photo_presets = self.gopro.get_presets()

        mock_get.assert_called_once_with(
            "http://10.5.5.9/gopro/camera/presets/get", timeout=5, verify=""
        )
        self.assertEqual(available_photo_presets, expected_photo_presets)


class TestGoProPresetValidation(unittest.TestCase):
    """Test suite for GoPro preset validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_presets = {
            "presetGroupArray": [
                {
                    "id": "PRESET_GROUP_ID_PHOTO",
                    "presetArray": [
                        {"id": 65536, "name": "Standard Photo"},
                        {"id": 65539, "name": "Night Photo"},
                    ],
                }
            ]
        }

    @mock.patch("fenetre.gopro.requests.get")
    @mock.patch("fenetre.gopro.logging")
    def test_validate_presets_success(self, mock_logging, mock_get):
        """Test that validation passes when configured presets are available."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_presets
        mock_get.return_value = mock_response

        gopro_cam = gopro.GoPro(preset_day={"id": 65536}, preset_night={"id": 65539})
        gopro_cam.validate_presets()

        mock_logging.info.assert_called_with(
            "Available presets: ['Standard Photo', 'Night Photo']"
        )
        mock_logging.error.assert_not_called()

    @mock.patch("fenetre.gopro.requests.get")
    @mock.patch("fenetre.gopro.logging")
    def test_validate_presets_failure_invalid_id(self, mock_logging, mock_get):
        """Test that validation fails when a configured preset is not available."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_presets
        mock_get.return_value = mock_response

        gopro_cam = gopro.GoPro(
            preset_day={"id": 12345}, preset_night={"id": 65539}  # Invalid ID
        )
        gopro_cam.validate_presets()

        mock_logging.error.assert_any_call(
            "Configured day preset ID '12345' is not available on the camera."
        )

    @mock.patch("fenetre.gopro.requests.get")
    @mock.patch("fenetre.gopro.logging")
    def test_validate_presets_failure_no_presets_retrieved(
        self, mock_logging, mock_get
    ):
        """Test that validation fails when no presets can be retrieved."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Simulate empty response
        mock_get.return_value = mock_response

        gopro_cam = gopro.GoPro()
        gopro_cam.validate_presets()

        mock_logging.error.assert_called_with(
            "Could not retrieve available presets from the camera."
        )

    @mock.patch("fenetre.gopro.GoPro._get_latest_file")
    @mock.patch("fenetre.gopro.requests.get")
    def test_capture_photo_with_preset_settings(self, mock_get, mock_get_latest_file):
        """Test that capture_photo applies preset and its settings via HTTP calls."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response
        mock_get_latest_file.side_effect = [
            ("100GOPRO", "GOPR0001.JPG"),
            ("100GOPRO", "GOPR0002.JPG"),
        ]

        preset_config = {
            "id": 65536,
            "settings": {
                "photo_output": "SuperPhoto",
            },
        }
        gopro_cam = gopro.GoPro(preset_day=preset_config)
        gopro_cam.capture_photo()

        expected_calls = [
            # Standard setup calls in capture_photo
            mock.call(
                "http://10.5.5.9/gopro/camera/control/set_ui_controller?p=2",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=1&setting=175",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=10&setting=88",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=4&setting=91",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=0&setting=83",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=7&setting=59",
                timeout=5,
                verify="",
            ),
            # Preset and settings calls
            mock.call(
                "http://10.5.5.9/gopro/camera/presets/load?id=65536",
                timeout=5,
                verify="",
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=3&setting=125",
                timeout=5,
                verify="",
            ),
            # Shutter and file operations
            mock.call(
                "http://10.5.5.9/gopro/camera/shutter/start", timeout=5, verify=""
            ),
            mock.call(
                "http://10.5.5.9/videos/DCIM/100GOPRO/GOPR0002.JPG",
                timeout=5,
                verify="",
            ),
            mock.call().raise_for_status(),
            mock.call(
                "http://10.5.5.9/gopro/media/delete/file?path=100GOPRO/GOPR0002.JPG",
                timeout=5,
                verify="",
            ),
        ]
        # We only check the calls made to the mocked 'get' function
        mock_get.assert_has_calls(expected_calls, any_order=False)


if __name__ == "__main__":
    unittest.main()
