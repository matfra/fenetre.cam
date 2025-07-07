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
) -> Image.Image:
    """Adds a timestamp to the image."""
    draw = ImageDraw.Draw(pic)

    try:
        tz_str = DEFAULT_TIMEZONE
        tz = pytz.timezone(tz_str)
        now = datetime.now(tz)
        timestamp_text = now.strftime(text_format)
    except Exception as e:
        logging.error(f"Error formatting timestamp: {e}. Using default format.")
        timestamp_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
    # text_bbox = draw.textbbox((0, 0), timestamp_text, font=font) # Pillow >= 9.2.0
    # For older Pillow:
    try:
        text_width, text_height = draw.textsize(timestamp_text, font=font)
    except TypeError: # If font is default font, textsize might not accept it.
         text_width, text_height = draw.textsize(timestamp_text)


    img_width, img_height = pic.size
    padding = 10  # Pixels padding from image border

    if isinstance(position, str) and "," in position: # "x,y" coordinates
        try:
            x_str, y_str = position.split(',')
            x = int(x_str.strip())
            y = int(y_str.strip())
        except ValueError:
            logging.warning(f"Invalid coordinate string for position: {position}. Defaulting to bottom_right.")
            x = img_width - text_width - padding
            y = img_height - text_height - padding
    elif position == "top_left":
        x = padding
        y = padding
    elif position == "top_right":
        x = img_width - text_width - padding
        y = padding
    elif position == "bottom_left":
        x = padding
        y = img_height - text_height - padding
    elif position == "bottom_right":
        x = img_width - text_width - padding
        y = img_height - text_height - padding
    else: # Default to bottom_right if position is unrecognized
        logging.warning(f"Unrecognized position: {position}. Defaulting to bottom_right.")
        x = img_width - text_width - padding
        y = img_height - text_height - padding

    # Ensure x, y are within image bounds
    x = max(0, min(x, img_width - text_width))
    y = max(0, min(y, img_height - text_height))

    draw.text((x, y), timestamp_text, font=font, fill=parsed_color)
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
                    f"color={step.get('color', 'white')}"
                )
                pic = add_timestamp(
                    pic,
                    text_format=step.get("format", "%Y-%m-%d %H:%M:%S %Z"),
                    position=step.get("position", "bottom_right"),
                    size=step.get("size", 24),
                    color=step.get("color", "white"),
                    # font_path=step.get("font_path") # Add if custom font path is desired in config
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
