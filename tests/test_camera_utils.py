import unittest
from unittest.mock import patch

from fenetre.camera_utils import get_day_night_from_exif


class GetDayNightFromExifTests(unittest.TestCase):
    def setUp(self):
        self.base_config = {
            "day_settings": {"trigger_exposure_composite_value": 2},
            "night_settings": {"trigger_exposure_composite_value": 3},
        }

    def test_missing_exposure_time_yields_unknown(self):
        exif_dict = {"iso": 100}

        with patch("fenetre.camera_utils.logger") as mock_logger:
            result = get_day_night_from_exif(exif_dict, self.base_config, "day")

        self.assertEqual(result, "unknown")
        mock_logger.warning.assert_called_with(
            "Could not detect day/night mode based on EXIF data."
        )

    def test_switches_from_day_to_night_above_threshold(self):
        exif_dict = {"iso": 100, "exposure_time": 0.05}  # composite = 5

        with patch("fenetre.camera_utils.logger") as mock_logger:
            result = get_day_night_from_exif(exif_dict, self.base_config, "day")

        self.assertEqual(result, "night")
        self.assertTrue(
            any(
                "Switching to night mode" in call.args[0]
                for call in mock_logger.debug.call_args_list
                if call.args
            )
        )

    def test_switches_from_night_to_day_below_threshold(self):
        exif_dict = {"iso": 100, "exposure_time": 0.01}  # composite = 1

        with patch("fenetre.camera_utils.logger") as mock_logger:
            result = get_day_night_from_exif(exif_dict, self.base_config, "night")

        self.assertEqual(result, "day")
        self.assertTrue(
            any(
                "Switching to day mode" in call.args[0]
                for call in mock_logger.debug.call_args_list
                if call.args
            )
        )

    def test_switches_to_astro_when_threshold_exceeded(self):
        config = {
            **self.base_config,
            "astro_settings": {"trigger_exposure_composite_value": 2000},
        }
        exif_dict = {"iso": 400, "exposure_time": 10}  # composite = 4000

        result = get_day_night_from_exif(exif_dict, config, "night")

        self.assertEqual(result, "astro")

    def test_returns_to_night_from_astro_when_below_threshold(self):
        config = {
            **self.base_config,
            "astro_settings": {"trigger_exposure_composite_value": 2000},
        }
        exif_dict = {"iso": 100, "exposure_time": 5}  # composite = 500

        result = get_day_night_from_exif(exif_dict, config, "astro")

        self.assertEqual(result, "night")

    def test_unknown_mode_can_switch_to_night(self):
        exif_dict = {"iso": 200, "exposure_time": 0.05}  # composite = 10

        result = get_day_night_from_exif(exif_dict, self.base_config, "unknown")

        self.assertEqual(result, "night")

    def test_unknown_mode_can_switch_to_day(self):
        exif_dict = {"iso": 50, "exposure_time": 0.01}  # composite = 0.5

        result = get_day_night_from_exif(exif_dict, self.base_config, "unknown")

        self.assertEqual(result, "day")

    def test_requires_night_settings_when_day_settings_present(self):
        config = {"day_settings": {"trigger_exposure_composite_value": 2}}
        exif_dict = {"iso": 100, "exposure_time": 0.02}

        with patch("fenetre.camera_utils.logger") as mock_logger:
            result = get_day_night_from_exif(exif_dict, config, "day")

        self.assertEqual(result, "day")
        mock_logger.error.assert_called_with(
            "If you specify day settings, you must also specify night settings."
        )


if __name__ == "__main__":
    unittest.main()
