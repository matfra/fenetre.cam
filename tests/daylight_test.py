import daylight
import os
import sys
import unittest
from unittest import mock
from datetime import datetime

from PIL import Image  # Ensure Image is imported if spec=Image.Image is used

# Assume your script is named daylight.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestDaylightProcessor(unittest.TestCase):

    def setUp(self):
        self.default_sky_color = daylight.DEFAULT_SKY_COLOR
        self.daily_band_height = daylight.DAILY_BAND_HEIGHT
        self.test_camera_data_path = (
            "test_data/test_camera"  # Added from previous context
        )

    # ... (other test methods like test_iso_day_to_dt, test_parse_sky_area, etc., remain the same)

    def test_get_avg_color_success(self):
        """Tests get_avg_color on successful color averaging."""
        mock_img_input = mock.MagicMock(
            spec=Image.Image
        )  # Input image to get_avg_color
        mock_sky_region_cropped = mock.MagicMock(
            spec=Image.Image
        )  # Result of img.crop()
        mock_img_input.crop.return_value = mock_sky_region_cropped

        # 1. Mock the .mean() method that will be called on the result of np.array()
        #    Let this .mean() method return a simple Python list of floats.
        mock_mean_method = mock.MagicMock(return_value=[100.5, 150.2, 200.9])

        # 2. Mock the array object that np.array(sky_region_cropped) would return.
        #    This mock array object must have our mock_mean_method as its 'mean' attribute.
        mock_array_object_instance = mock.MagicMock()
        mock_array_object_instance.mean = mock_mean_method

        # 3. Patch 'daylight.np.array' (the function call)
        #    Configure it so when daylight.np.array() is called,
        #    it returns our mock_array_object_instance.
        with mock.patch(
            "daylight.np.array", return_value=mock_array_object_instance
        ) as mock_np_array_function:
            # Call the function under test
            avg_color_result = daylight.get_avg_color(mock_img_input, (0, 0, 10, 10))

            # Assertions
            self.assertEqual(
                avg_color_result, (100, 150, 200)
            )  # Expecting integers after conversion

            # Verify mocks were called as expected
            mock_img_input.crop.assert_called_once_with((0, 0, 10, 10))
            mock_np_array_function.assert_called_once_with(mock_sky_region_cropped)
            mock_array_object_instance.mean.assert_called_once_with(axis=(0, 1))

    def test_get_avg_color_error_on_crop(self):
        """Tests get_avg_color when image.crop() raises an error."""
        mock_img_input = mock.MagicMock(spec=Image.Image)
        mock_img_input.crop.side_effect = Exception(
            "Test crop failure"
        )  # Simulate error during crop

        avg_color_result = daylight.get_avg_color(mock_img_input, (0, 0, 10, 10))

        self.assertEqual(avg_color_result, self.default_sky_color)

    def test_get_avg_color_error_on_numpy_operation(self):
        """Tests get_avg_color when a numpy operation (array creation or mean) raises an error."""
        mock_img_input = mock.MagicMock(spec=Image.Image)
        mock_sky_region_cropped = mock.MagicMock(spec=Image.Image)
        mock_img_input.crop.return_value = mock_sky_region_cropped

        # Simulate an error when daylight.np.array() is called
        with mock.patch(
            "daylight.np.array", side_effect=Exception("Simulated Numpy error")
        ):
            avg_color_result = daylight.get_avg_color(mock_img_input, (0, 0, 10, 10))
            self.assertEqual(avg_color_result, self.default_sky_color)

        # Reset crop mock for the next scenario (if np.array works but .mean fails)
        mock_img_input.crop.reset_mock()
        mock_img_input.crop.side_effect = None  # Clear side effect
        mock_img_input.crop.return_value = mock_sky_region_cropped

        # Simulate an error when .mean() is called
        mock_mean_method_error = mock.MagicMock(
            side_effect=Exception("Simulated mean error")
        )
        mock_array_object_instance_for_mean_error = mock.MagicMock()
        mock_array_object_instance_for_mean_error.mean = mock_mean_method_error

        with mock.patch(
            "daylight.np.array", return_value=mock_array_object_instance_for_mean_error
        ):
            avg_color_result = daylight.get_avg_color(mock_img_input, (0, 0, 10, 10))
            self.assertEqual(avg_color_result, self.default_sky_color)

    # ... (Make sure to include other tests like test_create_daily_band_no_images, test_create_monthly_image_mixed_days, etc.)
    # test_iso_day_to_dt, test_parse_sky_area, test_get_month_pretty_name_html,
    # test_list_valid_days_directories, test_dump_html_header would remain the same as before.

    # Example of one of the previous tests for context:
    @mock.patch("daylight.os.listdir")
    @mock.patch("daylight.Image.new")
    @mock.patch("daylight.ImageDraw.Draw")
    # Removed @mock.patch('daylight.Image.open') as it's not used here
    # Removed @mock.patch('daylight.get_avg_color') as it's not used here
    def test_create_daily_band_no_images(
        self, mock_pil_draw, mock_pil_new, mock_os_listdir
    ):
        mock_os_listdir.return_value = []  # No JPG files
        mock_band_image = mock.MagicMock(spec=Image.Image)
        mock_pil_new.return_value = mock_band_image

        day_dir = os.path.join(self.test_camera_data_path, "2023-10-01")
        expected_save_path = os.path.join(day_dir, "daylight.png")

        result_path = daylight.create_daily_band(day_dir, (0, 0, 10, 10))

        mock_os_listdir.assert_called_once_with(day_dir)
        mock_pil_new.assert_called_once_with(
            "RGB", (1, self.daily_band_height), self.default_sky_color
        )
        mock_band_image.save.assert_called_once_with(expected_save_path)
        self.assertEqual(result_path, expected_save_path)

    @mock.patch("daylight.calendar.monthrange")
    @mock.patch("daylight.os.path.exists")
    @mock.patch("daylight.Image.open")
    @mock.patch("daylight.Image.new")
    @mock.patch("daylight.os.makedirs")
    def test_create_monthly_image_mixed_days(
        self,
        mock_makedirs,
        mock_pil_new,
        mock_pil_open,
        mock_os_path_exists,
        mock_monthrange,
    ):
        year_month_str = "2023-02"  # Test with February for varying days
        mock_monthrange.return_value = (None, 28)  # Mock 28 days for Feb 2023

        mock_valid_band = mock.MagicMock(spec=Image.Image)
        mock_valid_band.width = 1
        mock_valid_band.height = self.daily_band_height

        mock_invalid_dim_band = mock.MagicMock(spec=Image.Image)
        mock_invalid_dim_band.width = 2
        mock_invalid_dim_band.height = self.daily_band_height

        def os_path_exists_side_effect(path):
            if "2023-02-01/daylight.png" in path:
                return True
            if "2023-02-02/daylight.png" in path:
                return False
            if "2023-02-03/daylight.png" in path:
                return True
            if "2023-02-04/daylight.png" in path:
                return True
            if "2023-02-05/daylight.png" in path:
                return True
            return False

        mock_os_path_exists.side_effect = os_path_exists_side_effect

        def pil_open_side_effect(path):
            if "2023-02-01/daylight.png" in path:
                return mock_valid_band
            if "2023-02-03/daylight.png" in path:
                return mock_invalid_dim_band
            if "2023-02-04/daylight.png" in path:
                raise OSError("Cannot open image")
            if "2023-02-05/daylight.png" in path:
                return mock_valid_band
            raise FileNotFoundError

        mock_pil_open.side_effect = pil_open_side_effect

        mock_monthly_image = mock.MagicMock(spec=Image.Image)
        mock_default_band_image = mock.MagicMock(spec=Image.Image)
        mock_default_band_image.width = 1

        created_images_log = []

        def pil_new_side_effect(mode, size, color=None):
            img = mock.MagicMock(spec=Image.Image)
            img.width = size[0]
            img.height = size[1]
            created_images_log.append({"size": size, "color": color, "img_obj": img})
            if size == (28, self.daily_band_height):
                return mock_monthly_image
            elif (
                size == (1, self.daily_band_height) and color == self.default_sky_color
            ):
                return mock_default_band_image
            # Fallback for any other unexpected Image.new calls during test
            # print(f"Unexpected Image.new call: mode={mode}, size={size}, color={color}")
            return img

        mock_pil_new.side_effect = pil_new_side_effect

        expected_save_path = os.path.join(
            self.test_camera_data_path, "daylight", f"{year_month_str}.png"
        )

        result_path = daylight.create_monthly_image(
            year_month_str, self.test_camera_data_path
        )

        self.assertEqual(result_path, expected_save_path)
        mock_monthrange.assert_called_once_with(2023, 2)
        mock_makedirs.assert_called_once_with(
            os.path.join(self.test_camera_data_path, "daylight"), exist_ok=True
        )

        # Count how many times a default band was supposed to be created by Image.new
        num_default_bands_created_by_new = sum(
            1
            for ci in created_images_log
            if ci["size"] == (1, self.daily_band_height)
            and ci["color"] == self.default_sky_color
        )
        # Expected: Day 2 (missing), Day 3 (invalid dim), Day 4 (open error), and 23 other days (28 total - 5 handled explicitly)
        self.assertEqual(num_default_bands_created_by_new, 28 - 2)  # 2 days are valid

        self.assertEqual(mock_monthly_image.paste.call_count, 28)
        paste_calls = mock_monthly_image.paste.call_args_list
        self.assertIs(paste_calls[0][0][0], mock_valid_band)
        self.assertIs(paste_calls[1][0][0], mock_default_band_image)
        self.assertIs(paste_calls[2][0][0], mock_default_band_image)
        self.assertIs(paste_calls[3][0][0], mock_default_band_image)
        self.assertIs(paste_calls[4][0][0], mock_valid_band)
        for i in range(5, 28):
            self.assertIs(paste_calls[i][0][0], mock_default_band_image)
        mock_monthly_image.save.assert_called_once_with(expected_save_path)

    # --- Add other test methods here ---
    def test_iso_day_to_dt(self):
        self.assertEqual(daylight.iso_day_to_dt("2023-10-27"), datetime(2023, 10, 27))
        with self.assertRaises(ValueError):
            daylight.iso_day_to_dt("2023/10/27")

    def test_parse_sky_area(self):
        self.assertEqual(daylight.parse_sky_area("0,50,600,150"), (0, 50, 600, 150))
        self.assertIsNone(daylight.parse_sky_area("0,50,600"))
        self.assertIsNone(daylight.parse_sky_area("0,50,600,abc"))
        self.assertIsNone(daylight.parse_sky_area(None))
        self.assertIsNone(daylight.parse_sky_area(""))

    def test_get_month_pretty_name_html(self):
        self.assertEqual(daylight.get_month_pretty_name_html("2023-10"), "Oct<br>2023")
        self.assertEqual(daylight.get_month_pretty_name_html("2024-01"), "Jan<br>2024")

    @mock.patch("daylight.os.path.isdir")
    @mock.patch("daylight.os.listdir")
    def test_list_valid_days_directories(self, mock_os_listdir, mock_os_path_isdir):
        test_dir = "some_camera_dir"
        mock_os_listdir.return_value = [
            "2023-10-01",
            "2023-10-02",
            "invalid-dir",
            "2023-09-30",
            "not_a_dir.txt",
        ]

        def isdir_side_effect(path):
            if path.endswith("not_a_dir.txt"):
                return False
            return True

        mock_os_path_isdir.side_effect = isdir_side_effect

        expected = ["2023-09-30", "2023-10-01", "2023-10-02"]
        self.assertEqual(daylight.list_valid_days_directories(test_dir), expected)
        mock_os_listdir.assert_called_once_with(test_dir)

    @mock.patch("daylight.os.path.isdir", return_value=False)
    def test_list_valid_days_directories_non_existent_base(self, mock_os_path_isdir):
        self.assertEqual(daylight.list_valid_days_directories("non_existent_dir"), [])

    def test_dump_html_header(self):
        title = "Test Title"
        additional = "<meta name='test' content='value'>"
        html = daylight.dump_html_header(title, additional)
        self.assertIn(f"<title>{title}</title>", html)
        self.assertIn(additional, html)
        self.assertTrue(html.startswith("<!DOCTYPE html>"))


if __name__ == "__main__":
    # Ensure Pillow is available if spec=Image.Image is used, or remove spec.
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
