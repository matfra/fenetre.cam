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

    @mock.patch('gopro.GoPro._make_gopro_request')
    def test_set_setting_success(self, mock_make_gopro_request):
        self.gopro.settings.video_performance_mode = "Maximum Video Performance"
        mock_make_gopro_request.assert_called_with(
            "/gopro/camera/setting?option=0&setting=173"
        )

        self.gopro.settings.max_lens = "On"
        mock_make_gopro_request.assert_called_with(
            "/gopro/camera/setting?option=1&setting=162"
        )

    def test_set_invalid_setting(self):
        with self.assertRaises(AttributeError):
            self.gopro.settings.invalid_setting = "some_value"

    def test_set_invalid_value(self):
        with self.assertRaises(ValueError):
            self.gopro.settings.video_performance_mode = "invalid_value"

    @mock.patch('gopro.GoPro._get_latest_file')
    @mock.patch('gopro.GoPro._make_gopro_request')
    @mock.patch('gopro.requests.get')
    def test_capture_photo(self, mock_requests_get, mock_make_gopro_request, mock_get_latest_file):
        mock_photo_response = mock.Mock()
        mock_photo_response.status_code = 200
        mock_photo_response.content = b"test_jpeg_content"
        mock_requests_get.return_value = mock_photo_response

        mock_get_latest_file.side_effect = [
            ("100GOPRO", "GOPR0001.JPG"),
            ("100GOPRO", "GOPR0002.JPG"),
        ]

        content = self.gopro.capture_photo()

        self.assertEqual(content, b"test_jpeg_content")

        expected_calls = [
            mock.call("/gopro/camera/control/set_ui_controller?p=2"),
            mock.call('/gopro/camera/setting?option=1&setting=175'),
            mock.call('/gopro/camera/setting?option=10&setting=88'),
            mock.call('/gopro/camera/setting?option=4&setting=91'),
            mock.call('/gopro/camera/setting?option=0&setting=83'),
            mock.call('/gopro/camera/setting?option=7&setting=59'),
        ]
        mock_make_gopro_request.assert_has_calls(expected_calls, any_order=False)

        mock_requests_get.assert_any_call(
            "http://10.5.5.9/videos/DCIM/100GOPRO/GOPR0002.JPG",
            timeout=5,
            verify=""
        )
        mock_requests_get.assert_any_call(
            "http://10.5.5.9/gopro/camera/shutter/start",
            timeout=5,
            verify=""
        )
        
        mock_make_gopro_request.assert_called_with("/gopro/media/delete/file?path=100GOPRO/GOPR0002.JPG")


if __name__ == '__main__':
    unittest.main()
