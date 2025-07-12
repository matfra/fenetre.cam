import unittest
import os
import shutil
import time
from datetime import datetime, timedelta
from archive import (
    is_dir_older_than_n_days,
    check_dir_has_timelapse,
    list_unarchived_dirs,
    keep_only_a_subset_of_jpeg_files,
)


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_archive"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_is_dir_older_than_n_days(self):
        # Create a directory with a date of yesterday
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_dir = os.path.join(
            self.test_dir, yesterday.strftime("%Y-%m-%d")
        )
        os.makedirs(yesterday_dir)
        self.assertFalse(is_dir_older_than_n_days(yesterday_dir, n_days=3))

        # Create a directory with a date of 4 days ago
        four_days_ago = datetime.now() - timedelta(days=4)
        four_days_ago_dir = os.path.join(
            self.test_dir, four_days_ago.strftime("%Y-%m-%d")
        )
        os.makedirs(four_days_ago_dir)
        self.assertTrue(is_dir_older_than_n_days(four_days_ago_dir, n_days=3))

    def test_check_dir_has_timelapse(self):
        # Create a directory with a small timelapse file
        timelapse_dir = os.path.join(self.test_dir, "timelapse_dir")
        os.makedirs(timelapse_dir)
        timelapse_file = os.path.join(timelapse_dir, "timelapse_dir.mp4")
        with open(timelapse_file, "w") as f:
            f.write("small file")
        self.assertFalse(check_dir_has_timelapse(timelapse_dir))

        # Create a directory with a large timelapse file
        large_timelapse_dir = os.path.join(self.test_dir, "large_timelapse_dir")
        os.makedirs(large_timelapse_dir)
        large_timelapse_file = os.path.join(
            large_timelapse_dir, "large_timelapse_dir.mp4"
        )
        with open(large_timelapse_file, "wb") as f:
            f.write(os.urandom(2 * 1024 * 1024))
        self.assertTrue(check_dir_has_timelapse(large_timelapse_dir))


if __name__ == "__main__":
    unittest.main()
