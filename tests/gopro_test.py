import unittest
from unittest import mock

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gopro


class TestGoPro(unittest.TestCase):
    """Test suite for GoPro camera functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.gopro = gopro.GoPro()

    @mock.patch('gopro.requests.get')
    def test_set_setting_success(self, mock_get):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        self.gopro.settings.video_performance_mode = "Maximum Video Performance"
        mock_get.assert_called_with(
            "http://10.5.5.9/gopro/camera/setting?option=0&setting=173",
            timeout=5,
            verify=""
        )

        self.gopro.settings.max_lens = "On"
        mock_get.assert_called_with(
            "http://10.5.5.9/gopro/camera/setting?option=1&setting=162",
            timeout=5,
            verify=""
        )

    def test_set_invalid_setting(self):
        with self.assertRaises(AttributeError):
            self.gopro.settings.invalid_setting = "some_value"

    def test_set_invalid_value(self):
        with self.assertRaises(ValueError):
            self.gopro.settings.video_performance_mode = "invalid_value"

    @mock.patch('gopro.GoPro._get_latest_file')
    @mock.patch('gopro.requests.get')
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
            mock.call('http://10.5.5.9/gopro/camera/control/set_ui_controller?p=2', timeout=5, verify=''),
            mock.call('http://10.5.5.9/gopro/camera/setting?option=1&setting=175', timeout=5, verify=''),
            mock.call('http://10.5.5.9/gopro/camera/setting?option=10&setting=88', timeout=5, verify=''),
            mock.call('http://10.5.5.9/gopro/camera/setting?option=4&setting=91', timeout=5, verify=''),
            mock.call('http://10.5.5.9/gopro/camera/setting?option=0&setting=83', timeout=5, verify=''),
            mock.call('http://10.5.5.9/gopro/camera/setting?option=7&setting=59', timeout=5, verify=''),
            mock.call('http://10.5.5.9/gopro/camera/shutter/start', timeout=5, verify=''),
            mock.call('http://10.5.5.9/videos/DCIM/100GOPRO/GOPR0002.JPG', timeout=5, verify=''),
            mock.call().raise_for_status(),
            mock.call('http://10.5.5.9/gopro/media/delete/file?path=100GOPRO/GOPR0002.JPG', timeout=5, verify=''),
        ]
        mock_get.assert_has_calls(expected_calls, any_order=False)

    @mock.patch('gopro.requests.get')
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
            timeout=5,
            verify=""
        )
        self.assertEqual(self.gopro.state, mock_state)

    @mock.patch('gopro.requests.get')
    def test_get_presets(self, mock_get):
        import json
        gopro_presets_path = os.path.join(os.path.dirname(__file__), "gopro_presets_get.json")
        with open(gopro_presets_path) as f:
            mock_presets = json.load(f)

        gopro_expected_photo_presets_path = os.path.join(os.path.dirname(__file__), "goprohero11_photo_presets.json")
        with open(gopro_expected_photo_presets_path) as f:
            expected_photo_presets = json.load(f)

        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_presets
        mock_get.return_value = mock_response

        available_photo_presets = self.gopro.get_presets()

        mock_get.assert_called_once_with(
            "http://10.5.5.9/gopro/camera/presets/get",
            timeout=5,
            verify=""
        )
        self.assertEqual(available_photo_presets, expected_photo_presets)


if __name__ == '__main__':
    unittest.main()
