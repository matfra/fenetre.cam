import os
import sys
import unittest
from unittest import mock
import json

from fenetre import gopro


class TestGoProHero6(unittest.TestCase):
    """Test suite for GoPro Hero 6 camera functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.gopro = gopro.GoPro(gopro_model="hero6")

    @mock.patch("fenetre.gopro.requests.get")
    def test_update_state(self, mock_get):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_response

        self.gopro.update_state()

        mock_get.assert_called_once_with(
            "http://10.5.5.9/status", timeout=self.gopro.timeout
        )
        self.assertEqual(self.gopro.state, {"status": "ok"})

    @mock.patch("fenetre.gopro.GoProHero6._get_latest_file")
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
                "http://10.5.5.9/gp/gpControl/command/shutter?p=1",
                timeout=self.gopro.timeout,
            ),
            mock.call(
                "http://10.5.5.9/videos/DCIM/100GOPRO/GOPR0002.JPG",
                timeout=self.gopro.timeout,
            ),
            mock.call().raise_for_status(),
            mock.call(
                "http://10.5.5.9/gp/gpControl/command/storage/delete?p=100GOPRO/GOPR0002.JPG",
                timeout=self.gopro.timeout,
            ),
        ]
        # We can't check the calls to raise_for_status, so we filter them out
        calls = [c for c in mock_get.mock_calls if "_mock_name" not in c[0]]
        self.assertEqual(calls, expected_calls)

    @mock.patch("fenetre.gopro.requests.get")
    def test_set_setting_success(self, mock_get):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        self.gopro.settings.photo_resolution = "12mp_wide"
        mock_get.assert_called_with(
            "http://10.5.5.9/gp/gpControl/setting/17/0",
            timeout=self.gopro.timeout,
        )

        self.gopro.settings.protune = "on"
        mock_get.assert_called_with(
            "http://10.5.5.9/gp/gpControl/setting/21/1",
            timeout=self.gopro.timeout,
        )

    def test_set_invalid_setting(self):
        with self.assertRaises(AttributeError):
            self.gopro.settings.invalid_setting = "some_value"

    def test_set_invalid_value(self):
        with self.assertRaises(ValueError):
            self.gopro.settings.photo_resolution = "invalid_value"


if __name__ == "__main__":
    unittest.main()
