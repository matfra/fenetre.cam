import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from timelapse import create_timelapse

class TestTimelapse(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('timelapse.subprocess.run')
    def test_create_timelapse(self, mock_subprocess_run):
        # Create a dummy directory with some jpg files
        for i in range(10):
            with open(os.path.join(self.temp_dir.name, f"test_{i}.jpg"), "w") as f:
                f.write("test")

        # Call the function
        create_timelapse(self.temp_dir.name, overwrite=True)

        # Check that ffmpeg was called
        self.assertTrue(mock_subprocess_run.called)

if __name__ == '__main__':
    unittest.main()
