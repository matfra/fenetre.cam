import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from fenetre.timelapse import create_timelapse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestTimelapse(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("fenetre.timelapse.subprocess.run")
    @patch("fenetre.timelapse.get_image_dimensions", return_value=(1920, 1080))
    @patch("fenetre.timelapse.is_raspberry_pi", return_value=False)
    def test_create_timelapse_ffmpeg_args_not_pi(
        self, mock_is_pi, mock_get_dims, mock_subprocess_run
    ):
        # Create a dummy directory with some jpg files
        for i in range(10):
            with open(os.path.join(self.temp_dir.name, f"test_{i}.jpg"), "w") as f:
                f.write("test")

        # Call the function
        create_timelapse(
            self.temp_dir.name,
            overwrite=True,
            two_pass=False,
            log_dir=self.temp_dir.name,
        )

        # Check that ffmpeg was called with the correct arguments
        self.assertTrue(mock_subprocess_run.called)
        args, kwargs = mock_subprocess_run.call_args
        self.assertIn("-c:v", args[0])
        self.assertIn("libvpx-vp9", args[0])
        self.assertIn(".mp4", args[0][-1])

    @patch("fenetre.timelapse.subprocess.run")
    @patch("fenetre.timelapse.get_image_dimensions", return_value=(1920, 1080))
    @patch("fenetre.timelapse.is_raspberry_pi", return_value=True)
    def test_create_timelapse_ffmpeg_args_pi(
        self, mock_is_pi, mock_get_dims, mock_subprocess_run
    ):
        # Create a dummy directory with some jpg files
        for i in range(10):
            with open(os.path.join(self.temp_dir.name, f"test_{i}.jpg"), "w") as f:
                f.write("test")

        # Call the function
        create_timelapse(
            self.temp_dir.name,
            overwrite=True,
            two_pass=False,
            log_dir=self.temp_dir.name,
        )

        # Check that ffmpeg was called with the correct arguments
        self.assertTrue(mock_subprocess_run.called)
        args, kwargs = mock_subprocess_run.call_args
        self.assertIn("-c:v", args[0])
        self.assertIn("h264_v4l2m2m", args[0])
        self.assertIn(".mp4", args[0][-1])


if __name__ == "__main__":
    unittest.main()
