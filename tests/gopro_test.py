import unittest
from unittest import mock

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gopro


class TestCaptureGoProPhoto(unittest.TestCase):
    @mock.patch("os.unlink")
    @mock.patch("tempfile.NamedTemporaryFile")
    @mock.patch("gopro.time.sleep")
    @mock.patch("gopro.requests.get")
    @mock.patch("gopro.requests.post")
    def test_capture_photo(self, mock_post, mock_get, mock_sleep, mock_tempfile, mock_unlink):
        mock_sleep.return_value = None
        list_resp = mock.Mock()
        list_resp.json.return_value = {
            "id": "1554375628411872255",
            "media": [
                {
                    "d": "100GOPRO",
                    "fs": [
                        {
                            "cre": 1696600109,
                            "glrv": 817767,
                            "ls": -1,
                            "mod": 1696600109,
                            "n": "GOPR0001.JPG",
                            "raw": 1,
                            "s": 2806303,
                        }
                    ],
                }
            ],
        }
        list_resp.raise_for_status.return_value = None
        photo_resp = mock.Mock()
        photo_resp.content = b"data"
        photo_resp.raise_for_status.return_value = None
        mock_get.side_effect = [mock.Mock(json=lambda: {"media": [{"d": "100GOPRO", "fs": [{"n": "GOPR0000.JPG"}]}]}), mock.Mock(json=lambda: {"media": [{"d": "100GOPRO", "fs": [{"n": "GOPR0001.JPG"}]}]}), photo_resp, mock.Mock()]

        tmp_file = mock.Mock()
        tmp_file.name = "/tmp/ca.pem"
        mock_tempfile.return_value = tmp_file

        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "{}\n"
        result = gopro.capture_gopro_photo(ip_address="1.2.3.4", timeout=1, root_ca="CERT")

        self.assertEqual(result, b"data")


if __name__ == "__main__":
    unittest.main()
