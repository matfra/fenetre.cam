import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage import exposure
from typing import Optional, Tuple, Union
from absl import logging
from datetime import datetime
import pytz # To get timezone from global_config easily
import yaml # For get_timezone_from_config


# It's not ideal to re-read the config here, but it's the simplest way to get timezone
# without a major refactor of how config is passed down.
# Consider refactoring if more global configs are needed here.
def get_timezone_from_config():
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
            return config.get("global", {}).get("timezone", "UTC")
    except FileNotFoundError:
        logging.warning("config.yaml not found, defaulting timezone to UTC for timestamps.")
        return "UTC"
    except Exception as e:
        logging.error(f"Error reading timezone from config.yaml: {e}. Defaulting to UTC.")
        return "UTC"

DEFAULT_TIMEZONE = get_timezone_from_config()


def _parse_color(color_input: Union[str, Tuple[int, int, int]]) -> Tuple[int, int, int]:
    """Parses a color string (name or RGB tuple string) into an RGB tuple."""
    if isinstance(color_input, tuple):
        return color_input
    if isinstance(color_input, str):
        if color_input.startswith("(") and color_input.endswith(")"):
            try:
                parts = list(map(int, color_input.strip("()").split(',')))
                if len(parts) == 3:
                    return tuple(parts) # type: ignore
                else:
                    logging.warning(f"Invalid RGB tuple string (not 3 parts): {color_input}. Defaulting to white.")
                    return (255, 255, 255)
            except ValueError:
                logging.warning(f"Invalid RGB tuple string (non-integer parts): {color_input}. Defaulting to white.")
                return (255, 255, 255)
        # For common color names, PIL/Pillow can often handle them directly.
        # If specific name-to-RGB mapping is needed, expand here.
        return color_input # type: ignore
    logging.warning(f"Invalid color type: {color_input}. Defaulting to white.")
    return (255, 255, 255)


def add_timestamp(
    pic: Image.Image,
    text_format: str = "%Y-%m-%d %H:%M:%S %Z",
    position: str = "bottom_right",
    size: int = 24,
    color: Union[str, Tuple[int, int, int]] = "white",
    font_path: Optional[str] = None, # Allow custom font
    background_color: Optional[Union[str, Tuple[int, int, int]]] = None, # Optional background color
    background_padding: int = 2, # Padding around text for background
    custom_text: Optional[str] = None # Optional custom text to prepend
) -> Image.Image:
    """Adds a timestamp and optional custom text to the image."""
    draw = ImageDraw.Draw(pic, "RGBA" if background_color else "RGB") # Use RGBA if background needs transparency

    try:
        tz_str = DEFAULT_TIMEZONE
        tz = pytz.timezone(tz_str)
        now = datetime.now(tz)
        formatted_time = now.strftime(text_format)
        if custom_text:
            timestamp_text = f"{custom_text} {formatted_time}"
        else:
            timestamp_text = formatted_time
    except Exception as e:
        logging.error(f"Error formatting timestamp: {e}. Using default format.")
        formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if custom_text:
            timestamp_text = f"{custom_text} {formatted_time}"
        else:
            timestamp_text = formatted_time

    try:
        if font_path:
            font = ImageFont.truetype(font_path, size)
        else:
            # Try to load a commonly available font, fallback to default
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", size)
            except IOError:
                try:
                    font = ImageFont.truetype("Arial.ttf", size) # Common on Windows/macOS
                except IOError:
                    logging.warning("DejaVuSans.ttf or Arial.ttf not found. Using default PIL font. Timestamp text might be small.")
                    font = ImageFont.load_default()
    except Exception as e:
        logging.error(f"Error loading font: {e}. Using default PIL font.")
        font = ImageFont.load_default()

    parsed_color = _parse_color(color)

    # Calculate text size and position
    try:
        # textbbox returns (left, top, right, bottom)
        text_bbox = draw.textbbox((0, 0), timestamp_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    except TypeError: # If font is default font, textbbox might not accept it.
        # For default font, textlength and textbbox might behave differently or not be available.
        # A common fallback for default font if textbbox fails (though ideally it shouldn't with modern Pillow):
        try:
            text_width = draw.textlength(timestamp_text, font=font) # Get width
            # Estimate height for default font - this is a rough part for default fonts
            # as they don't have rich metrics like TrueType.
            # Often, the 'size' of default font is not directly comparable or settable like TTF.
            # We'll use a heuristic or assume a common aspect ratio if specific metrics are unavailable.
            # This might need adjustment based on visual results with the default font.
            # For now, let's assume a generic height based on a typical character, e.g., 'M'.
            # If 'font.size' attribute was available and meaningful for default, it could be used.
            # As a simple fallback, let's query bbox for a capital letter.
            cap_bbox = draw.textbbox((0,0), "M", font=font)
            text_height = cap_bbox[3] - cap_bbox[1]
            # If text_width from textlength is zero (e.g. empty string), ensure text_height is also zero
            if text_width == 0:
                text_height = 0

        except AttributeError: # Fallback for very old Pillow or if textlength not on default font
            logging.warning("Cannot determine text size accurately with the default font. Timestamp may be misplaced.")
            # As a last resort, make a guess or use fixed values if text metrics are unavailable
            text_width = len(timestamp_text) * 6 # Rough estimate: 6 pixels per char
            text_height = 10 # Rough estimate: 10 pixels high


    img_width, img_height = pic.size
    padding = 10  # Pixels padding from image border

    if isinstance(position, str) and "," in position: # "x,y" coordinates
        try:
            x_str, y_str = position.split(',')
            x = int(x_str.strip())
            # For bbox, the y-coordinate is the top of the text, so no further adjustment needed here for 'y'
            # However, if we want 'y' to specify the *bottom* of the text, we'd do y = int(y_str.strip()) - text_height
            y = int(y_str.strip())
        except ValueError:
            logging.warning(f"Invalid coordinate string for position: {position}. Defaulting to bottom_right.")
            x = img_width - text_width - padding
            y = img_height - text_height - padding - text_bbox[1] # Adjust for text_bbox top offset
    elif position == "top_left":
        x = padding
        y = padding - text_bbox[1] # Adjust for text_bbox top offset
    elif position == "top_right":
        x = img_width - text_width - padding
        y = padding - text_bbox[1] # Adjust for text_bbox top offset
    elif position == "bottom_left":
        x = padding
        y = img_height - text_height - padding - text_bbox[1] # Adjust for text_bbox top offset
    elif position == "bottom_right":
        x = img_width - text_width - padding
        y = img_height - text_height - padding - text_bbox[1] # Adjust for text_bbox top offset
    elif position == "top_center":
        x = (img_width - text_width) // 2
        y = padding - text_bbox[1] # Adjust for text_bbox top offset
    elif position == "bottom_center":
        x = (img_width - text_width) // 2
        y = img_height - text_height - padding - text_bbox[1] # Adjust for text_bbox top offset
    else: # Default to bottom_right if position is unrecognized
        logging.warning(f"Unrecognized position: {position}. Defaulting to bottom_right.")
        x = img_width - text_width - padding
        y = img_height - text_height - padding - text_bbox[1] # Adjust for text_bbox top offset

    # Ensure x, y are within image bounds
    # We need to consider the text_bbox[0] (left offset) as well for x positioning if it's not 0
    # And text_bbox[1] (top offset) for y.
    # The draw.text() function expects the top-left corner of the text *drawing area*,
    # not necessarily the top-left of the text characters themselves if there's internal padding/offset.
    # text_bbox[0] and text_bbox[1] are often 0 or small for typical fonts at (0,0) origin.

    # The x,y calculated so far is for the origin of the text according to textbbox.
    # draw.text((x,y)) will place the (text_bbox[0], text_bbox[1]) of the text at image coordinates (x,y).
    # So, if text_bbox[0] is negative (e.g. character extends left of origin), we need to shift x.
    # And if text_bbox[1] is negative (e.g. character extends above origin), we need to shift y.
    # The calculated x,y is the desired top-left of the *bounding box*.
    # So, we draw at (x - text_bbox[0], y - text_bbox[1])

    final_x = x - text_bbox[0]
    final_y = y - text_bbox[1]

    # Ensure the bounding box is within image bounds after adjusting for internal text offsets
    final_x = max(0, min(final_x, img_width - text_width))
    final_y = max(0, min(final_y, img_height - text_height))

    if background_color:
        parsed_background_color = _parse_color(background_color)
        # Define background rectangle position and size
        # The text_bbox already includes internal padding of the font.
        # We use final_x, final_y which are adjusted for text_bbox[0] and text_bbox[1]
        # So the background rectangle should start at (final_x + text_bbox[0], final_y + text_bbox[1])
        # and end at (final_x + text_bbox[2], final_y + text_bbox[3]) for tight fit.
        # Add background_padding to this.
        bg_x0 = final_x + text_bbox[0] - background_padding
        bg_y0 = final_y + text_bbox[1] - background_padding
        bg_x1 = final_x + text_bbox[0] + text_width + background_padding
        bg_y1 = final_y + text_bbox[1] + text_height + background_padding

        # Ensure background is within image bounds (optional, could allow partial backgrounds)
        bg_x0 = max(0, bg_x0)
        bg_y0 = max(0, bg_y0)
        bg_x1 = min(img_width, bg_x1)
        bg_y1 = min(img_height, bg_y1)

        if bg_x1 > bg_x0 and bg_y1 > bg_y0: # Only draw if valid rectangle
             # Check if parsed_background_color needs alpha for transparency
            if isinstance(parsed_background_color, tuple) and len(parsed_background_color) == 3:
                # Assume full opacity if alpha not provided
                bg_color_tuple = parsed_background_color + (255,)
            elif isinstance(parsed_background_color, tuple) and len(parsed_background_color) == 4:
                bg_color_tuple = parsed_background_color
            else: # String color name, let Pillow handle it, assume full opacity
                # To ensure RGBA for draw.rectangle, convert named colors to RGBA
                from PIL import ImageColor
                try:
                    # Convert named color to RGBA tuple
                    # ImageColor.getcolor can return RGB or RGBA depending on the color string
                    rgba_color = ImageColor.getcolor(parsed_background_color, "RGBA")
                    bg_color_tuple = rgba_color
                except ValueError: # Fallback if color name is not recognized by ImageColor
                    logging.warning(f"Invalid background color name: {background_color}. Defaulting to semi-transparent black.")
                    bg_color_tuple = (0,0,0,128) # Default: semi-transparent black

            # Create a temporary drawing surface if the main image is not RGBA and we need transparency
            if pic.mode != "RGBA" and bg_color_tuple[3] < 255:
                overlay = Image.new("RGBA", pic.size, (0,0,0,0))
                draw_overlay = ImageDraw.Draw(overlay)
                draw_overlay.rectangle([bg_x0, bg_y0, bg_x1, bg_y1], fill=bg_color_tuple)
                pic.paste(overlay, (0,0), overlay) # Paste using alpha
            else: # Main image is RGBA or background is opaque
                draw.rectangle([bg_x0, bg_y0, bg_x1, bg_y1], fill=bg_color_tuple)


    draw.text((final_x, final_y), timestamp_text, font=font, fill=parsed_color)
    return pic


def postprocess(pic: Image.Image, postprocessing_steps: list) -> Tuple[Image.Image, dict]:
    """
    Applies a series of post-processing steps to an image.
    """
    exif_data = pic.info.get("exif")
    for step in postprocessing_steps:
        if step["type"] == "crop":
            logging.debug(f"Cropping image to area: {step['area']}")
            pic = crop(pic, step["area"])
        elif step["type"] == "resize":
            logging.debug(
                f"Resizing image to width: {step.get('width')}, height: {step.get('height')}"
            )
            pic = resize(pic, step.get("width"), step.get("height"))
        elif step["type"] == "awb":
            logging.debug("Applying auto white balance to image")
            pic = auto_white_balance(pic)
        elif step["type"] == "timestamp":
            if step.get("enabled", False):
                logging.debug(
                    f"Adding timestamp with config: "
                    f"format={step.get('format', '%Y-%m-%d %H:%M:%S %Z')}, "
                    f"position={step.get('position', 'bottom_right')}, "
                    f"size={step.get('size', 24)}, "
                    f"color={step.get('color', 'white')}, "
                    f"background_color={step.get('background_color', None)}, "
                    f"background_padding={step.get('background_padding', 2)}, "
                    f"custom_text={step.get('custom_text', None)}"
                )
                pic = add_timestamp(
                    pic,
                    text_format=step.get("format", "%Y-%m-%d %H:%M:%S %Z"),
                    position=step.get("position", "bottom_right"),
                    size=step.get("size", 24),
                    color=step.get("color", "white"),
                    font_path=step.get("font_path"), # Allow custom font path from config
                    background_color=step.get("background_color", None),
                    background_padding=step.get("background_padding", 2),
                    custom_text=step.get("custom_text", None)
                )
    return pic, exif_data


def crop(pic: Image.Image, area: str) -> Image.Image:
    """
    Crops an image to a specified area.
    """
    crop_points_list = [float(i) for i in area.split(",")]
    crop_points = (
        crop_points_list[0],
        crop_points_list[1],
        crop_points_list[2],
        crop_points_list[3],
    )
    logging.debug(f"Cropping picture to {crop_points}")
    return pic.crop(crop_points)


# If only one dimension is provided, the other will be calculated based on the aspect ratio of the original image or the cropped area.
# If both dimensions are provided, the image will be resized to those exact dimensions
def resize(
    pic: Image.Image, width: Optional[int] = None, height: Optional[int] = None
) -> Image.Image:
    """
    Resizes an image to a specified width and height.
    """
    if width is None and height is None:
        return pic
    if width is None and height is not None:
        aspect_ratio = pic.width / pic.height
        width = int(height * aspect_ratio)
    if height is None and width is not None:
        aspect_ratio = pic.height / pic.width
        height = int(width * aspect_ratio)
    return pic.resize(size=(width, height), reducing_gap=3.0)  # type: ignore


def auto_white_balance(pic: Image.Image) -> Image.Image:
    """
    Applies auto white balance to an image.
    """
    # Convert the image to a NumPy array
    img_array = np.array(pic)

    # Perform auto white balance using histogram equalization on each channel
    img_array_awb = np.zeros_like(img_array)
    for channel in range(img_array.shape[2]):
        img_array_awb[:, :, channel] = (
            exposure.equalize_hist(img_array[:, :, channel]) * 255
        )

    # Convert the NumPy array back to a PIL image
    return Image.fromarray(img_array_awb.astype(np.uint8))
