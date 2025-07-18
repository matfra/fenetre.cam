import unittest
import os
import tempfile
import time
from datetime import datetime, timedelta
import pytz
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from archive import (
    keep_only_a_subset_of_jpeg_files,
    list_unarchived_dirs,
    check_dir_has_timelapse,
    check_dir_has_daylight_band,
    get_today_date,
    is_dir_older_than_n_days,
    archive_daydir,
)

class TestArchive(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('archive.global_config', {"timelapse_file_extension": "mp4"})
    @patch('archive.get_today_date')
    @patch('archive.is_dir_older_than_n_days')
    @patch('archive.check_dir_has_daylight_band')
    @patch('archive.check_dir_has_timelapse')
    @patch('archive.create_timelapse')
    @patch('archive.run_end_of_day')
    @patch('archive.keep_only_a_subset_of_jpeg_files')
    def test_archive_daydir(self, mock_keep_files, mock_run_end_of_day, mock_create_timelapse, mock_check_timelapse, mock_check_daylight, mock_is_older, mock_get_today):
        # Set up mocks
        mock_get_today.return_value = "2023-01-03"
        mock_is_older.return_value = True
        mock_check_daylight.return_value = True
        mock_check_timelapse.return_value = True

        # Create a dummy directory
        day_dir = os.path.join(self.temp_dir.name, "2023-01-01")
        os.makedirs(day_dir)

        # Call the function
        archive_daydir(day_dir)

        # Check that the correct functions were called
        mock_keep_files.assert_called_once_with(day_dir, dry_run=True)
        mock_run_end_of_day.assert_not_called()
        mock_create_timelapse.assert_not_called()


if __name__ == '__main__':
    unittest.main()
