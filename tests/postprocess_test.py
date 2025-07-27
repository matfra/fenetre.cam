from fenetre.postprocess import _parse_color, add_timestamp, postprocess
import os
# Assuming postprocess.py is in the parent directory or PYTHONPATH is set up
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytz

from PIL import Image

# Add the parent directory to sys.path to allow imports from postprocess
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestPostprocess(unittest.TestCase):

    def create_test_image(
        self, width=200, height=100, color=(0, 0, 255)
    ) -> Image.Image:  # Default to blue tuple
        return Image.new("RGB", (width, height), color)

    def test_parse_color(self):
        self.assertEqual(_parse_color("red"), "red")  # Pillow handles named colors
        self.assertEqual(_parse_color("(255,0,0)"), (255, 0, 0))
        self.assertEqual(_parse_color("( 255, 0, 0 )"), (255, 0, 0))  # With spaces
        self.assertEqual(_parse_color((0, 255, 0)), (0, 255, 0))
        # Test fallback for invalid string
        with patch("fenetre.postprocess.logging") as mock_logging:
            self.assertEqual(
                _parse_color("invalid_color_string"), "invalid_color_string"
            )  # Will be passed to PIL
            self.assertEqual(
                _parse_color("(123,456)"), (255, 255, 255)
            )  # Invalid tuple string
            mock_logging.warning.assert_called()
        with patch("fenetre.postprocess.logging") as mock_logging:
            self.assertEqual(_parse_color(123), (255, 255, 255))  # Invalid type
            mock_logging.warning.assert_called()

    @patch("fenetre.postprocess.ImageDraw.Draw")
    @patch("fenetre.postprocess.ImageFont.truetype")
    @patch("fenetre.postprocess.datetime")
    @patch("fenetre.postprocess.pytz")
    def test_add_timestamp_basic(
        self, mock_pytz, mock_datetime, mock_truetype, mock_draw_constructor
    ):
        mock_image = self.create_test_image()
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance
        # Corrected to mock textbbox instead of textsize for width/height
        mock_draw_instance.textbbox.return_value = (0, 0, 100, 20)  # l, t, r, b

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
        with patch("fenetre.postprocess.DEFAULT_TIMEZONE", "UTC"):
            add_timestamp(mock_image, size=12, color="yellow", position="bottom_right")

        mock_pytz.timezone.assert_called_with("UTC")
        mock_datetime.now.assert_called_with(mock_tz)

        mock_truetype.assert_called_with(
            "DejaVuSans.ttf", 12
        )  # or Arial.ttf if DejaVuSans fails
        mock_draw_instance.text.assert_called_once()
        args, kwargs = mock_draw_instance.text.call_args

        # Check text content by inspecting the call to draw.text
        # args[1] is the text argument to draw.text
        self.assertIn(expected_text, args[1])
        self.assertEqual(kwargs["fill"], "yellow")
        self.assertEqual(kwargs["font"], mock_font)

        # Check position (approximate, as exact calculation depends on textsize)
        # For "bottom_right", x would be img_width - text_width - padding
        # y would be img_height - text_height - padding
        # We can check that the coordinates are positive and less than image dimensions
        text_pos_x, text_pos_y = args[0]
        self.assertTrue(0 <= text_pos_x < mock_image.width)
        self.assertTrue(0 <= text_pos_y < mock_image.height)

    @patch("fenetre.postprocess.ImageDraw.Draw")
    @patch("fenetre.postprocess.ImageFont.truetype")
    @patch("fenetre.postprocess.datetime")
    @patch("fenetre.postprocess.pytz")
    def test_add_timestamp_custom_format_and_position(
        self, mock_pytz, mock_datetime, mock_truetype, mock_draw_constructor
    ):
        mock_image = self.create_test_image(width=300, height=150)
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance
        # Corrected to mock textbbox
        mock_draw_instance.textbbox.return_value = (0, 0, 120, 25)  # l, t, r, b

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2024, 5, 10, 8, 30, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now

        mock_font = MagicMock()
        mock_truetype.return_value = mock_font

        custom_format = "%H:%M %d/%m/%Y"
        expected_text = "08:30 10/05/2024"

        with patch("fenetre.postprocess.DEFAULT_TIMEZONE", "UTC"):
            add_timestamp(
                mock_image,
                text_format=custom_format,
                size=20,
                color="(0,255,0)",
                position="top_left",
            )

        mock_truetype.assert_called_with("DejaVuSans.ttf", 20)
        mock_draw_instance.text.assert_called_once()
        args, kwargs = mock_draw_instance.text.call_args

        self.assertEqual(args[1], expected_text)
        self.assertEqual(kwargs["fill"], (0, 255, 0))

        # For "top_left", position should be near (padding, padding)
        # With textbbox, the coordinates might be adjusted by text_bbox[0] and text_bbox[1]
        # Assuming text_bbox = (0, 0, 120, 25) for this test for simplicity in asserting position.
        mock_draw_instance.textbbox.return_value = (0, 0, 120, 25)
        padding = 10
        # final_x = padding - text_bbox[0]
        # final_y = padding - text_bbox[1]
        self.assertEqual(args[0], (padding - 0, padding - 0))

    @patch("fenetre.postprocess.ImageDraw.Draw")
    @patch(
        "fenetre.postprocess.ImageFont.truetype", side_effect=IOError("Font not found")
    )  # Mock font load failure
    @patch("fenetre.postprocess.ImageFont.load_default")  # Mock fallback font
    @patch("fenetre.postprocess.datetime")
    @patch("fenetre.postprocess.pytz")
    def test_add_timestamp_font_fallback(
        self,
        mock_pytz,
        mock_datetime,
        mock_load_default,
        mock_truetype_fail,
        mock_draw_constructor,
    ):
        mock_image = self.create_test_image()
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance
        # Corrected to mock textbbox
        mock_draw_instance.textbbox.return_value = (0, 0, 90, 18)  # l, t, r, b

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mock_default_font = MagicMock()
        mock_load_default.return_value = mock_default_font

        with patch("fenetre.postprocess.DEFAULT_TIMEZONE", "UTC"):
            add_timestamp(mock_image, size=15)

        # Check that truetype was attempted for DejaVuSans and Arial, then load_default was called
        self.assertEqual(mock_truetype_fail.call_count, 2)  # DejaVuSans and Arial
        mock_truetype_fail.assert_any_call("DejaVuSans.ttf", 15)
        mock_truetype_fail.assert_any_call("Arial.ttf", 15)
        mock_load_default.assert_called_once()

        args, kwargs = mock_draw_instance.text.call_args
        self.assertEqual(kwargs["font"], mock_default_font)

    @patch("fenetre.postprocess.add_timestamp")  # Mock the actual timestamping function
    def test_postprocess_integration_timestamp_enabled(self, mock_add_timestamp):
        img = self.create_test_image()
        postprocessing_steps = [
            {
                "type": "timestamp",
                "enabled": True,
                "size": 30,
                "color": "blue",
                "position": "center",
            }
        ]

        # Make the mocked add_timestamp return the original image for this test
        mock_add_timestamp.return_value = img
        returned_img, _ = postprocess(img, postprocessing_steps)

        self.assertEqual(img, returned_img)
        mock_add_timestamp.assert_called_once_with(
            img,
            text_format="%Y-%m-%d %H:%M:%S %Z",  # Default
            position="center",
            size=30,
            color="blue",
            font_path=None,
            background_color=None,
            background_padding=2,
            custom_text=None,
        )

    @patch("fenetre.postprocess.add_timestamp")
    def test_postprocess_integration_timestamp_disabled(self, mock_add_timestamp):
        img = self.create_test_image()
        postprocessing_steps = [{"type": "timestamp", "enabled": False, "size": 30}]

        returned_img, _ = postprocess(img, postprocessing_steps)

        self.assertEqual(img, returned_img)
        mock_add_timestamp.assert_not_called()

    @patch("fenetre.postprocess.ImageDraw.Draw")
    @patch("fenetre.postprocess.ImageFont.truetype")
    @patch("fenetre.postprocess.datetime")
    @patch("fenetre.postprocess.pytz")
    def test_add_timestamp_specific_coordinates(
        self, mock_pytz, mock_datetime, mock_truetype, mock_draw_constructor
    ):
        mock_image = self.create_test_image(width=300, height=150)
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2024, 5, 10, 8, 30, 0, tzinfo=pytz.utc)
        mock_datetime.now.return_value = mock_now

        mock_font = MagicMock()
        mock_truetype.return_value = mock_font
        # Mock textbbox return value
        mock_draw_instance.textbbox.return_value = (0, 0, 100, 20)  # l, t, r, b

        with patch("fenetre.postprocess.DEFAULT_TIMEZONE", "UTC"):
            add_timestamp(mock_image, position="50,75", size=10, color="red")

        mock_draw_instance.text.assert_called_once()
        args, kwargs = mock_draw_instance.text.call_args

        # Position should be exactly (50,75)
        self.assertEqual(args[0], (50, 75))
        self.assertEqual(kwargs["fill"], "red")

    # Test for get_timezone_from_config - this is a bit tricky as it reads a file
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch("yaml.safe_load")
    def test_get_timezone_from_config_success(self, mock_safe_load, mock_open_file):
        from fenetre.postprocess import get_timezone_from_config

        mock_safe_load.return_value = {"global": {"timezone": "America/New_York"}}

        # Temporarily modify DEFAULT_TIMEZONE for this test scope if it's a global
        # Or, ensure get_timezone_from_config is called where its result is used
        # For this test, we are directly testing get_timezone_from_config

        tz = get_timezone_from_config()
        self.assertEqual(tz, "America/New_York")
        mock_open_file.assert_called_with("config.yaml", "r")

    @patch("builtins.open", side_effect=FileNotFoundError)
    @patch("fenetre.postprocess.logging")  # to check for warning
    def test_get_timezone_from_config_file_not_found(
        self, mock_logging, mock_open_file
    ):
        from fenetre.postprocess import get_timezone_from_config  # re-import

        tz = get_timezone_from_config()
        self.assertEqual(tz, "UTC")  # Fallback
        mock_logging.warning.assert_called_with(
            "config.yaml not found, defaulting timezone to UTC for timestamps."
        )

    @patch("fenetre.postprocess.ImageDraw.Draw")
    @patch("fenetre.postprocess.ImageFont.truetype")
    @patch("fenetre.postprocess.datetime")
    @patch("fenetre.postprocess.pytz")
    def test_add_timestamp_new_positions(
        self, mock_pytz, mock_datetime, mock_truetype, mock_draw_constructor
    ):
        mock_image = self.create_test_image(width=400, height=200)
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mock_font = MagicMock()
        mock_truetype.return_value = mock_font

        # Define text_bbox for consistent calculations: (left, top, right, bottom)
        # Meaning text_width = 100, text_height = 20, left_offset=0, top_offset=0
        example_text_bbox = (0, 0, 100, 20)
        mock_draw_instance.textbbox.return_value = example_text_bbox
        text_width = example_text_bbox[2] - example_text_bbox[0]
        text_height = example_text_bbox[3] - example_text_bbox[1]

        padding = 10
        img_width, img_height = mock_image.size

        positions_to_test = {
            "top_center": (
                (img_width - text_width) // 2,
                padding - example_text_bbox[1],
            ),
            "bottom_center": (
                (img_width - text_width) // 2,
                img_height - text_height - padding - example_text_bbox[1],
            ),
        }

        for position_name, expected_coords in positions_to_test.items():
            with patch("fenetre.postprocess.DEFAULT_TIMEZONE", "UTC"):
                add_timestamp(
                    mock_image, position=position_name, size=10, color="green"
                )

            args, _ = mock_draw_instance.text.call_args
            # final_x = expected_coords[0] - example_text_bbox[0]
            # final_y = expected_coords[1] - example_text_bbox[1]
            # Since example_text_bbox[0] and [1] are 0, final_x,y are same as expected_coords
            self.assertEqual(
                args[0], expected_coords, f"Position failed for {position_name}"
            )
            # Reset mock for next iteration if necessary, though here it's implicitly reset by new call_args
            mock_draw_instance.text.reset_mock()

    @patch("fenetre.postprocess.ImageDraw.Draw")
    @patch("fenetre.postprocess.ImageFont.truetype")
    @patch("fenetre.postprocess.datetime")
    @patch("fenetre.postprocess.pytz")
    @patch("PIL.ImageColor.getcolor")  # Corrected patch target
    def test_add_timestamp_with_background(
        self,
        mock_pil_imagecolor_getcolor,
        mock_pytz,
        mock_datetime,
        mock_truetype,
        mock_draw_constructor,
    ):
        mock_image = self.create_test_image(width=200, height=100)
        # Important: Ensure image mode allows for transparency if background has alpha
        # For this test, let's assume we might use a semi-transparent background
        mock_image = mock_image.convert(
            "RGBA"
        )  # Ensure image is RGBA for background testing

        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance  # Standard mock setup

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mock_font = MagicMock()
        mock_truetype.return_value = mock_font

        example_text_bbox = (0, 0, 80, 15)  # l,t,r,b
        mock_draw_instance.textbbox.return_value = example_text_bbox

        # Test with a string background color (e.g., "gray")
        background_color_string = "gray"
        # Mock what ImageColor.getcolor would return for "gray" in RGBA
        mock_pil_imagecolor_getcolor.return_value = (128, 128, 128, 255)  # Opaque gray

        with patch("fenetre.postprocess.DEFAULT_TIMEZONE", "UTC"):
            add_timestamp(
                mock_image,
                color="black",
                background_color=background_color_string,
                background_padding=5,
                position="bottom_left",
            )

        # Check that draw.rectangle was called for the background
        mock_draw_instance.rectangle.assert_called_once()
        rect_args, rect_kwargs = mock_draw_instance.rectangle.call_args

        # rect_args[0] is the [x0, y0, x1, y1] list for the rectangle
        # We need to calculate the expected background coordinates
        # final_x, final_y for text (bottom_left)
        padding = 10
        text_width = example_text_bbox[2] - example_text_bbox[0]
        text_height = example_text_bbox[3] - example_text_bbox[1]

        # Expected text position (bottom_left)
        # x = padding - example_text_bbox[0]
        # y = mock_image.height - text_height - padding - example_text_bbox[1]
        # Since text_bbox offsets are 0:
        expected_text_x = padding
        expected_text_y = mock_image.height - text_height - padding

        # final_x for text drawing is expected_text_x - example_text_bbox[0]
        # final_y for text drawing is expected_text_y - example_text_bbox[1]
        final_text_x = expected_text_x - example_text_bbox[0]
        final_text_y = expected_text_y - example_text_bbox[1]

        background_padding = 5
        # bg_x0 = final_text_x + example_text_bbox[0] - background_padding
        # bg_y0 = final_text_y + example_text_bbox[1] - background_padding
        # bg_x1 = final_text_x + example_text_bbox[0] + text_width + background_padding
        # bg_y1 = final_text_y + example_text_bbox[1] + text_height + background_padding
        expected_bg_x0 = final_text_x + example_text_bbox[0] - background_padding
        expected_bg_y0 = final_text_y + example_text_bbox[1] - background_padding
        expected_bg_x1 = (
            final_text_x + example_text_bbox[0] + text_width + background_padding
        )
        expected_bg_y1 = (
            final_text_y + example_text_bbox[1] + text_height + background_padding
        )

        self.assertEqual(
            rect_args[0],
            [expected_bg_x0, expected_bg_y0, expected_bg_x1, expected_bg_y1],
        )
        self.assertEqual(rect_kwargs["fill"], mock_pil_imagecolor_getcolor.return_value)

        # Check that text is drawn on top
        mock_draw_instance.text.assert_called_once()
        text_args, _ = mock_draw_instance.text.call_args
        self.assertEqual(text_args[0], (final_text_x, final_text_y))

        # Test with a tuple background color with alpha
        mock_draw_instance.reset_mock()
        mock_pil_imagecolor_getcolor.reset_mock()  # Reset if it's used for tuple conversion too (it's not here)

        background_color_to_test = (0, 0, 255, 128)  # Semi-transparent blue
        # No need to mock ImageColor.getcolor for tuple inputs

        # Re-patch draw_constructor for this specific call if mode check is important
        # Or ensure the side_effect handles this state change
        # For simplicity, the previous check for RGBA mode on Draw init covers the general case.

        with patch("fenetre.postprocess.DEFAULT_TIMEZONE", "UTC"):
            add_timestamp(
                mock_image,
                color="white",
                background_color=background_color_to_test,
                background_padding=3,
                position="top_right",
            )

        mock_draw_instance.rectangle.assert_called_once()
        rect_args_transparent, rect_kwargs_transparent = (
            mock_draw_instance.rectangle.call_args
        )
        self.assertEqual(rect_kwargs_transparent["fill"], background_color_to_test)

    @patch("fenetre.postprocess.ImageDraw.Draw")
    @patch("fenetre.postprocess.ImageFont.truetype")
    @patch("fenetre.postprocess.datetime")
    @patch("fenetre.postprocess.pytz")
    def test_add_timestamp_with_custom_text(
        self, mock_pytz, mock_datetime, mock_truetype, mock_draw_constructor
    ):
        mock_image = self.create_test_image()
        mock_draw_instance = MagicMock()
        mock_draw_constructor.return_value = mock_draw_instance

        mock_tz = MagicMock()
        mock_pytz.timezone.return_value = mock_tz
        # Use a fixed datetime for predictable output
        mock_now = datetime(2024, 7, 15, 10, 30, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now

        mock_font = MagicMock()
        mock_truetype.return_value = mock_font

        # Mock textbbox to prevent issues with text size calculation in test
        mock_draw_instance.textbbox.return_value = (0, 0, 150, 20)  # l,t,r,b

        custom_text_to_add = "Front Cam:"
        # Default format is "%Y-%m-%d %H:%M:%S %Z"
        expected_time_part = "2024-07-15 10:30:00 UTC"
        expected_full_text = f"{custom_text_to_add} {expected_time_part}"

        with patch("fenetre.postprocess.DEFAULT_TIMEZONE", "UTC"):
            add_timestamp(mock_image, custom_text=custom_text_to_add)

        # Verify that draw.text was called with the combined custom text and timestamp
        mock_draw_instance.text.assert_called_once()
        args, _ = mock_draw_instance.text.call_args

        # args[1] is the text argument in draw.text((coords), text, font=..., fill=...)
        self.assertEqual(args[1], expected_full_text)

        # Also test the integration through the main postprocess function
        mock_draw_instance.text.reset_mock()  # Reset for the next call test

        # Mock the add_timestamp call within postprocess to check parameters
        # This requires re-patching add_timestamp if we want to inspect its direct call from postprocess
        # For simplicity here, we'll assume the earlier direct test of add_timestamp covers its internal logic
        # and focus on the parameters passed from the 'postprocess' function config.

        # To test the 'postprocess' function's handling of 'custom_text' from config:
        # We need to mock 'add_timestamp' as it's called by 'postprocess'
        with patch(
            "fenetre.postprocess.add_timestamp"
        ) as mock_add_timestamp_in_postprocess:  # This mocks the public add_timestamp
            img_for_postproc = self.create_test_image()
            postprocessing_steps = [
                {
                    "type": "timestamp",
                    "enabled": True,
                    "custom_text": "Test Prefix",
                    # other params like color, size, position etc. would be passed here
                    # and checked in kwargs_passed if needed.
                }
            ]
            postprocess(img_for_postproc, postprocessing_steps)

            mock_add_timestamp_in_postprocess.assert_called_once()
            call_args_list = mock_add_timestamp_in_postprocess.call_args_list
            # Example of checking specific args passed to the mocked add_timestamp:
            # self.assertEqual(call_args_list[0][1]['custom_text'], "Test Prefix")
            # self.assertEqual(call_args_list[0][1]['color'], "white") # Default if not specified
            _, kwargs_passed = call_args_list[0]  # call_args is a tuple (args, kwargs)
            self.assertEqual(kwargs_passed.get("custom_text"), "Test Prefix")

    @patch(
        "fenetre.postprocess._add_text_overlay"
    )  # Mock the internal helper directly for generic text step
    def test_postprocess_integration_generic_text_step(self, mock_add_text_overlay):
        img = self.create_test_image()
        text_content = "Hello World"
        text_color = "orange"
        text_size = 40
        text_position = "top_center"
        bg_color = "black"
        bg_padding = 5
        font_p = "Arial.ttf"

        postprocessing_steps = [
            {
                "type": "text",
                "enabled": True,
                "text_content": text_content,
                "color": text_color,
                "size": text_size,
                "position": text_position,
                "background_color": bg_color,
                "background_padding": bg_padding,
                "font_path": font_p,
            }
        ]

        mock_add_text_overlay.return_value = img  # Ensure the mock returns an image

        returned_img, _ = postprocess(img, postprocessing_steps)

        self.assertEqual(img, returned_img)  # Check if image is returned
        mock_add_text_overlay.assert_called_once()

        # Verify that _add_text_overlay was called with the correct parameters
        args_passed, kwargs_passed = mock_add_text_overlay.call_args

        self.assertEqual(kwargs_passed.get("pic"), img)
        self.assertEqual(kwargs_passed.get("text_to_draw"), text_content)
        self.assertEqual(kwargs_passed.get("color"), text_color)
        self.assertEqual(kwargs_passed.get("size"), text_size)
        self.assertEqual(kwargs_passed.get("position"), text_position)
        self.assertEqual(kwargs_passed.get("background_color"), bg_color)
        self.assertEqual(kwargs_passed.get("background_padding"), bg_padding)
        self.assertEqual(kwargs_passed.get("font_path"), font_p)

    @patch("fenetre.postprocess._add_text_overlay")
    @patch("fenetre.postprocess.logging")
    def test_postprocess_integration_generic_text_step_disabled_or_no_text(
        self, mock_logging, mock_add_text_overlay
    ):
        img = self.create_test_image()

        # Test case 1: Step disabled
        postprocessing_steps_disabled = [
            {"type": "text", "enabled": False, "text_content": "Should not appear"}
        ]
        postprocess(img, postprocessing_steps_disabled)
        mock_add_text_overlay.assert_not_called()

        # Test case 2: Step enabled but no text_content
        postprocessing_steps_no_text = [
            {"type": "text", "enabled": True}  # Missing text_content
        ]
        postprocess(img, postprocessing_steps_no_text)
        mock_add_text_overlay.assert_not_called()
        mock_logging.warning.assert_called_with(
            "Generic text step is enabled but no 'text_content' was provided."
        )


if __name__ == "__main__":
    unittest.main()
