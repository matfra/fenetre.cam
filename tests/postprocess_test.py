import unittest
from unittest.mock import patch, MagicMock
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timezone
import pytz

# Assuming postprocess.py is in the parent directory or PYTHONPATH is set up
import sys
import os
# Add the parent directory to sys.path to allow imports from postprocess
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from postprocess import add_timestamp, _parse_color, postprocess

class TestPostprocess(unittest.TestCase):

    def create_test_image(self, width=200, height=100, color="blue") -> Image.Image:
        return Image.new("RGB", (width, height), color)

    def test_parse_color(self):
        self.assertEqual(_parse_color("red"), "red") # Pillow handles named colors
        self.assertEqual(_parse_color("(255,0,0)"), (255,0,0))
        self.assertEqual(_parse_color("( 255, 0, 0 )"), (255,0,0)) # With spaces
        self.assertEqual(_parse_color((0,255,0)), (0,255,0))
        # Test fallback for invalid string
        with patch('postprocess.logging') as mock_logging:
            self.assertEqual(_parse_color("invalid_color_string"), "invalid_color_string") # Will be passed to PIL
            self.assertEqual(_parse_color("(123,456)"), (255,255,255)) # Invalid tuple string
            mock_logging.warning.assert_called()
        with patch('postprocess.logging') as mock_logging:
            self.assertEqual(_parse_color(123), (255,255,255)) # Invalid type
            mock_logging.warning.assert_called()


    @patch('postprocess.ImageDraw.Draw')
    @patch('postprocess.ImageFont.truetype')
    @patch('postprocess.datetime')
    @patch('postprocess.pytz')
    def test_add_timestamp_basic(self, mock_pytz, mock_datetime, mock_truetype, mock_draw_constructor):
        mock_image = self.create_test_image()
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance
        mock_draw_instance.textsize.return_value = (100, 20) # example w, h

        # Mock datetime and timezone
        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mock_font = MagicMock()
        mock_truetype.return_value = mock_font

        # Expected text based on mock_now and default format
        expected_text = "2023-01-01 12:00:00 UTC"
        # If DEFAULT_TIMEZONE in postprocess.py is something else, adjust this
        # Forcing it for the test for predictability:
        with patch('postprocess.DEFAULT_TIMEZONE', "UTC"):
            add_timestamp(mock_image, size=12, color="yellow", position="bottom_right")

        mock_pytz.timezone.assert_called_with("UTC")
        mock_datetime.now.assert_called_with(mock_tz)

        mock_truetype.assert_called_with("DejaVuSans.ttf", 12) # or Arial.ttf if DejaVuSans fails
        mock_draw_instance.text.assert_called_once()
        args, kwargs = mock_draw_instance.text.call_args

        # Check text content by inspecting the call to draw.text
        # args[1] is the text argument to draw.text
        self.assertIn(expected_text, args[1])
        self.assertEqual(kwargs['fill'], "yellow")
        self.assertEqual(kwargs['font'], mock_font)

        # Check position (approximate, as exact calculation depends on textsize)
        # For "bottom_right", x would be img_width - text_width - padding
        # y would be img_height - text_height - padding
        # We can check that the coordinates are positive and less than image dimensions
        text_pos_x, text_pos_y = args[0]
        self.assertTrue(0 <= text_pos_x < mock_image.width)
        self.assertTrue(0 <= text_pos_y < mock_image.height)

    @patch('postprocess.ImageDraw.Draw')
    @patch('postprocess.ImageFont.truetype')
    @patch('postprocess.datetime')
    @patch('postprocess.pytz')
    def test_add_timestamp_custom_format_and_position(self, mock_pytz, mock_datetime, mock_truetype, mock_draw_constructor):
        mock_image = self.create_test_image(width=300, height=150)
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance
        mock_draw_instance.textsize.return_value = (120, 25) # example w, h

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2024, 5, 10, 8, 30, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now

        mock_font = MagicMock()
        mock_truetype.return_value = mock_font

        custom_format = "%H:%M %d/%m/%Y"
        expected_text = "08:30 10/05/2024"

        with patch('postprocess.DEFAULT_TIMEZONE', "UTC"):
             add_timestamp(mock_image, text_format=custom_format, size=20, color="(0,255,0)", position="top_left")

        mock_truetype.assert_called_with("DejaVuSans.ttf", 20)
        mock_draw_instance.text.assert_called_once()
        args, kwargs = mock_draw_instance.text.call_args

        self.assertEqual(args[1], expected_text)
        self.assertEqual(kwargs['fill'], (0,255,0))

        # For "top_left", position should be near (padding, padding)
        padding = 10
        self.assertEqual(args[0], (padding, padding))

    @patch('postprocess.ImageDraw.Draw')
    @patch('postprocess.ImageFont.truetype', side_effect=IOError("Font not found")) # Mock font load failure
    @patch('postprocess.ImageFont.load_default') # Mock fallback font
    @patch('postprocess.datetime')
    @patch('postprocess.pytz')
    def test_add_timestamp_font_fallback(self, mock_pytz, mock_datetime, mock_load_default, mock_truetype_fail, mock_draw_constructor):
        mock_image = self.create_test_image()
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance
        mock_draw_instance.textsize.return_value = (90, 18) # example w, h

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mock_default_font = MagicMock()
        mock_load_default.return_value = mock_default_font

        with patch('postprocess.DEFAULT_TIMEZONE', "UTC"):
            add_timestamp(mock_image, size=15)

        # Check that truetype was attempted for DejaVuSans and Arial, then load_default was called
        self.assertEqual(mock_truetype_fail.call_count, 2) # DejaVuSans and Arial
        mock_truetype_fail.assert_any_call("DejaVuSans.ttf", 15)
        mock_truetype_fail.assert_any_call("Arial.ttf", 15)
        mock_load_default.assert_called_once()

        args, kwargs = mock_draw_instance.text.call_args
        self.assertEqual(kwargs['font'], mock_default_font)

    @patch('postprocess.add_timestamp') # Mock the actual timestamping function
    def test_postprocess_integration_timestamp_enabled(self, mock_add_timestamp):
        img = self.create_test_image()
        postprocessing_steps = [
            {"type": "timestamp", "enabled": True, "size": 30, "color": "blue", "position": "center"}
        ]

        # Make the mocked add_timestamp return the original image for this test
        mock_add_timestamp.return_value = img
        returned_img, _ = postprocess(img, postprocessing_steps)

        self.assertEqual(img, returned_img)
        mock_add_timestamp.assert_called_once_with(
            img,
            text_format="%Y-%m-%d %H:%M:%S %Z", # Default
            position="center",
            size=30,
            color="blue"
        )

    @patch('postprocess.add_timestamp')
    def test_postprocess_integration_timestamp_disabled(self, mock_add_timestamp):
        img = self.create_test_image()
        postprocessing_steps = [
            {"type": "timestamp", "enabled": False, "size": 30}
        ]

        returned_img, _ = postprocess(img, postprocessing_steps)

        self.assertEqual(img, returned_img)
        mock_add_timestamp.assert_not_called()

    @patch('postprocess.ImageDraw.Draw')
    @patch('postprocess.ImageFont.truetype')
    @patch('postprocess.datetime')
    @patch('postprocess.pytz')
    def test_add_timestamp_specific_coordinates(self, mock_pytz, mock_datetime, mock_truetype, mock_draw_constructor):
        mock_image = self.create_test_image(width=300, height=150)
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2024, 5, 10, 8, 30, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now

        mock_font = MagicMock()
        mock_truetype.return_value = mock_font
        # Mock textsize return value
        mock_draw_instance.textsize.return_value = (100, 20) # width, height

        with patch('postprocess.DEFAULT_TIMEZONE', "UTC"):
             add_timestamp(mock_image, position="50,75", size=10, color="red")

        mock_draw_instance.text.assert_called_once()
        args, kwargs = mock_draw_instance.text.call_args

        # Position should be exactly (50,75)
        self.assertEqual(args[0], (50, 75))
        self.assertEqual(kwargs['fill'], "red")

    # Test for get_timezone_from_config - this is a bit tricky as it reads a file
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('yaml.safe_load')
    def test_get_timezone_from_config_success(self, mock_safe_load, mock_open_file):
        from postprocess import get_timezone_from_config # re-import for patch context
        mock_safe_load.return_value = {"global": {"timezone": "America/New_York"}}

        # Temporarily modify DEFAULT_TIMEZONE for this test scope if it's a global
        # Or, ensure get_timezone_from_config is called where its result is used
        # For this test, we are directly testing get_timezone_from_config

        tz = get_timezone_from_config()
        self.assertEqual(tz, "America/New_York")
        mock_open_file.assert_called_with("config.yaml", "r")

    @patch('builtins.open', side_effect=FileNotFoundError)
    @patch('postprocess.logging') # to check for warning
    def test_get_timezone_from_config_file_not_found(self, mock_logging, mock_open_file):
        from postprocess import get_timezone_from_config # re-import
        tz = get_timezone_from_config()
        self.assertEqual(tz, "UTC") # Fallback
        mock_logging.warning.assert_called_with("config.yaml not found, defaulting timezone to UTC for timestamps.")

if __name__ == '__main__':
    unittest.main()
