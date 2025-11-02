import os
import sys
import unittest
from unittest import mock
import json


from fenetre import gopro


class TestGoProHero11(unittest.TestCase):
    """Test suite for GoPro Hero 11 camera functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.gopro = gopro.GoProHero11()

    @mock.patch("fenetre.gopro.requests.get")
    def test_set_setting_success(self, mock_get):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        self.gopro.settings.video_performance_mode = "Maximum Video Performance"
        mock_get.assert_called_with(
            "http://10.5.5.9/gopro/camera/setting?option=0&setting=173",
            timeout=self.gopro.timeout,
            verify=self.gopro.root_ca_filepath,
        )

        self.gopro.settings.max_lens = "On"
        mock_get.assert_called_with(
            "http://10.5.5.9/gopro/camera/setting?option=1&setting=162",
            timeout=self.gopro.timeout,
            verify=self.gopro.root_ca_filepath,
        )

    def test_set_invalid_setting(self):
        with self.assertRaises(AttributeError):
            self.gopro.settings.invalid_setting = "some_value"

    def test_set_invalid_value(self):
        with self.assertRaises(ValueError):
            self.gopro.settings.video_performance_mode = "invalid_value"

    @mock.patch("fenetre.gopro.GoProHero11._get_latest_file")
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
                timeout=self.gopro.timeout,
                verify=self.gopro.root_ca_filepath,
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=10&setting=88",
                timeout=self.gopro.timeout,
                verify=self.gopro.root_ca_filepath,
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=4&setting=91",
                timeout=self.gopro.timeout,
                verify=self.gopro.root_ca_filepath,
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=0&setting=83",
                timeout=self.gopro.timeout,
                verify=self.gopro.root_ca_filepath,
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/setting?option=7&setting=59",
                timeout=self.gopro.timeout,
                verify=self.gopro.root_ca_filepath,
            ),
            mock.call(
                "http://10.5.5.9/gopro/camera/shutter/start",
                timeout=self.gopro.timeout,
                verify=self.gopro.root_ca_filepath,
            ),
            mock.call(
                "http://10.5.5.9/videos/DCIM/100GOPRO/GOPR0002.JPG",
                timeout=self.gopro.timeout,
                verify=self.gopro.root_ca_filepath,
            ),
            mock.call().raise_for_status(),
            mock.call(
                "http://10.5.5.9/gopro/media/delete/file?path=100GOPRO/GOPR0002.JPG",
                timeout=self.gopro.timeout,
                verify=self.gopro.root_ca_filepath,
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
            "http://10.5.5.9/gopro/camera/state",
            timeout=self.gopro.timeout,
            verify=self.gopro.root_ca_filepath,
        )
        self.assertEqual(self.gopro.state, mock_state)

    @mock.patch("fenetre.gopro.GoProHero11._make_gopro_request")
    def test_apply_settings(self, mock_request):
        settings_payload = {"photo_mode": "Night Photo", "lcd_brightness": 10}
        self.gopro.apply_settings(settings_payload)

        expected_calls = [
            mock.call("/gopro/camera/setting?option=1&setting=227"),
            mock.call("/gopro/camera/setting?option=10&setting=88"),
        ]
        mock_request.assert_has_calls(expected_calls, any_order=False)


class TestGoProHero9(unittest.TestCase):
    def setUp(self):
        self.gopro = gopro.GoProHero9()

    @mock.patch("fenetre.gopro.GoProHero9._make_gopro_request")
    def test_set_setting_routes_to_legacy_endpoint(self, mock_request):
        self.gopro.set_setting(144, 17)
        mock_request.assert_called_once_with(
            "/gp/gpControl/setting/144/17", expected_response_text=None
        )


if __name__ == "__main__":
    unittest.main()
