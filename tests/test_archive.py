import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import shutil

from fenetre.archive import archive_daydir, list_unarchived_dirs, check_dir_has_timelapse




class TestArchive(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_unarchived_dirs_skips_archived(self):
        # Create a dummy camera directory
        camera_dir = os.path.join(self.temp_dir.name, "camera1")
        os.makedirs(camera_dir)

        # Create a directory that is already archived but has many files
        archived_dir = os.path.join(camera_dir, "2025-07-18")
        os.makedirs(archived_dir)
        with open(os.path.join(archived_dir, "archived"), "w") as f:
            f.write("")
        for i in range(50):
            with open(os.path.join(archived_dir, f"img_{i}.jpg"), "w") as f:
                f.write("dummy")

        # Create a directory that is not archived
        unarchived_dir = os.path.join(camera_dir, "2025-07-19")
        os.makedirs(unarchived_dir)
        with open(os.path.join(unarchived_dir, "img_A.jpg"), "w") as f:
            f.write("dummy")

        # Create a directory with an invalid name
        invalid_dir = os.path.join(camera_dir, "not-a-date")
        os.makedirs(invalid_dir)

        # Call the function
        result = list_unarchived_dirs(camera_dir)

        # Check that only the unarchived directory is returned
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], unarchived_dir)

    @patch("fenetre.archive.get_today_date")
    @patch("fenetre.archive.is_dir_older_than_n_days")
    @patch("fenetre.archive.check_dir_has_daylight_band")
    @patch("fenetre.archive.check_dir_has_timelapse")
    @patch("fenetre.archive.create_timelapse")
    @patch("fenetre.archive.run_end_of_day")
    @patch("fenetre.archive.keep_only_a_subset_of_jpeg_files")
    def test_archive_daydir(
        self,
        mock_keep_files,
        mock_run_end_of_day,
        mock_create_timelapse,
        mock_check_timelapse,
        mock_check_daylight,
        mock_is_older,
        mock_get_today,
    ):
        # Set up mocks
        mock_get_today.return_value = "2023-01-03"
        mock_is_older.return_value = True
        mock_check_daylight.return_value = True
        mock_check_timelapse.return_value = True
        mock_global_config = {"timelapse_file_extension": "mp4"}
        mock_cam = "test_cam"
        mock_sky_area = (0, 0, 100, 100)

        # Create a dummy directory
        day_dir = os.path.join(self.temp_dir.name, "2023-01-01")
        os.makedirs(day_dir)

        # Call the function
        archive_daydir(day_dir, mock_global_config, mock_cam, mock_sky_area)

        # Check that the correct functions were called
        mock_keep_files.assert_called_once_with(day_dir, dry_run=True)
        mock_run_end_of_day.assert_not_called()
        mock_create_timelapse.assert_not_called()


class TestCheckDirHasTimelapse(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_no_timelapse(self):
        daydir = os.path.join(self.test_dir, "2025-08-20")
        os.makedirs(daydir)
        self.assertFalse(check_dir_has_timelapse(daydir))

    def test_webm_timelapse_large_enough(self):
        daydir = os.path.join(self.test_dir, "2025-08-20")
        os.makedirs(daydir)
        timelapse_path = os.path.join(daydir, "2025-08-20.webm")
        with open(timelapse_path, "wb") as f:
            f.write(b"0" * (1024 * 1024 + 1))
        self.assertTrue(check_dir_has_timelapse(daydir))

    def test_mp4_timelapse_large_enough(self):
        daydir = os.path.join(self.test_dir, "2025-08-20")
        os.makedirs(daydir)
        timelapse_path = os.path.join(daydir, "2025-08-20.mp4")
        with open(timelapse_path, "wb") as f:
            f.write(b"0" * (1024 * 1024 + 1))
        self.assertTrue(check_dir_has_timelapse(daydir))

    def test_timelapse_too_small(self):
        daydir = os.path.join(self.test_dir, "2025-08-20")
        os.makedirs(daydir)
        timelapse_path = os.path.join(daydir, "2025-08-20.webm")
        with open(timelapse_path, "wb") as f:
            f.write(b"0" * (1024 * 1024))
        self.assertFalse(check_dir_has_timelapse(daydir))

    def test_webm_exists_but_mp4_is_checked_first(self):
        # This test reproduces the suspected bug.
        # The function checks for mp4 first, and if it doesn't exist, it returns False
        # without checking for webm.
        daydir = os.path.join(self.test_dir, "2025-08-20")
        os.makedirs(daydir)
        timelapse_path = os.path.join(daydir, "2025-08-20.webm")
        with open(timelapse_path, "wb") as f:
            f.write(b"0" * (1024 * 1024 + 1))
        # With the buggy code, this will fail.
        self.assertTrue(check_dir_has_timelapse(daydir))


if __name__ == "__main__":
    unittest.main()