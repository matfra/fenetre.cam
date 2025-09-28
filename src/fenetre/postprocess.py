import logging
import os
from datetime import datetime
from typing import Dict, Optional, Tuple, Union
import io

import cairosvg
import numpy as np
import pyexiv2
import pytz  # To get timezone from global_config easily
from PIL import Image, ImageDraw, ImageFont, ImageOps
from skimage import exposure

from .sun_path_svg import create_sun_path_svg, overlay_time_bar

logger = logging.getLogger(__name__)

from fenetre.admin_server import (
    metric_picture_aperture,
    metric_picture_exposure_time_seconds,
    metric_picture_focal_length_mm,
    metric_picture_height_pixels,
    metric_picture_iso,
    metric_picture_size_bytes,
    metric_picture_white_balance,
    metric_picture_width_pixels,
)


def _parse_color(color_input: Union[str, Tuple[int, int, int]]) -> Tuple[int, int, int]:
    """Parses a color string (name or RGB tuple string) into an RGB tuple."""
    if isinstance(color_input, tuple):
        return color_input
    if isinstance(color_input, str):
        if color_input.startswith("(") and color_input.endswith(")"):
            try:
                parts = list(map(int, color_input.strip("()").split(",")))
                if len(parts) == 3:
                    return tuple(parts)  # type: ignore
                else:
                    logger.warning(
                        f"Invalid RGB tuple string (not 3 parts): {color_input}. Defaulting to white."
                    )
                    return (255, 255, 255)
            except ValueError:
                logger.warning(
                    f"Invalid RGB tuple string (non-integer parts): {color_input}. Defaulting to white."
                )
                return (255, 255, 255)
        # For common color names, PIL/Pillow can often handle them directly.
        # If specific name-to-RGB mapping is needed, expand here.
        return color_input  # type: ignore
    logger.warning(f"Invalid color type: {color_input}. Defaulting to white.")
    return (255, 255, 255)


def _add_text_overlay(
    pic: Image.Image,
    text_to_draw: str,
    position: str = "bottom_right",
    size: int = 24,
    color: Union[str, Tuple[int, int, int]] = "white",
    font_path: Optional[str] = None,
    background_color: Optional[Union[str, Tuple[int, int, int]]] = None,
    background_padding: int = 2,
) -> Image.Image:
    """Internal helper to add any text overlay to an image."""
    if not text_to_draw:  # Do nothing if text is empty
        return pic

    draw = ImageDraw.Draw(pic, "RGBA" if background_color else pic.mode)

    try:
        if font_path:
            font = ImageFont.truetype(font_path, size)
        else:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", size)
            except IOError:
                try:
                    font = ImageFont.truetype("Arial.ttf", size)
                except IOError:
                    logger.warning(
                        "DejaVuSans.ttf or Arial.ttf not found. Using default PIL font. Text might be small."
                    )
                    font = ImageFont.load_default()
    except Exception as e:
        logger.error(f"Error loading font: {e}. Using default PIL font.")
        font = ImageFont.load_default()

    parsed_text_color = _parse_color(color)

    try:
        text_bbox = draw.textbbox((0, 0), text_to_draw, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    except TypeError:
        try:
            text_width = draw.textlength(text_to_draw, font=font)
            cap_bbox = draw.textbbox((0, 0), "M", font=font)  # Estimate height
            text_height = cap_bbox[3] - cap_bbox[1]
            if text_width == 0:
                text_height = 0
        except AttributeError:
            logger.warning(
                "Cannot determine text size accurately with the default font. Text may be misplaced."
            )
            text_width = len(text_to_draw) * 6
            text_height = 10
            # Initialize text_bbox with estimated values if it couldn't be created before
            text_bbox = (0, 0, text_width, text_height)

    img_width, img_height = pic.size
    padding = 10

    if isinstance(position, str) and "," in position:
        try:
            x_str, y_str = position.split(",")
            x = int(x_str.strip())
            y = int(y_str.strip())
        except ValueError:
            logger.warning(
                f"Invalid coordinate string for position: {position}. Defaulting to bottom_right."
            )
            x = img_width - text_width - padding
            y = img_height - text_height - padding - (text_bbox[1] if text_bbox else 0)
    elif position == "top_left":
        x = padding
        y = padding - (text_bbox[1] if text_bbox else 0)
    elif position == "top_right":
        x = img_width - text_width - padding
        y = padding - (text_bbox[1] if text_bbox else 0)
    elif position == "bottom_left":
        x = padding
        y = img_height - text_height - padding - (text_bbox[1] if text_bbox else 0)
    elif position == "bottom_right":
        x = img_width - text_width - padding
        y = img_height - text_height - padding - (text_bbox[1] if text_bbox else 0)
    elif position == "top_center":
        x = (img_width - text_width) // 2
        y = padding - (text_bbox[1] if text_bbox else 0)
    elif position == "bottom_center":
        x = (img_width - text_width) // 2
        y = img_height - text_height - padding - (text_bbox[1] if text_bbox else 0)
    else:
        logger.warning(
            f"Unrecognized position: {position}. Defaulting to bottom_right."
        )
        x = img_width - text_width - padding
        y = img_height - text_height - padding - (text_bbox[1] if text_bbox else 0)

    final_x = x - (text_bbox[0] if text_bbox else 0)
    final_y = y - (text_bbox[1] if text_bbox else 0)

    final_x = max(0, min(final_x, img_width - text_width))
    final_y = max(0, min(final_y, img_height - text_height))

    if background_color:
        parsed_bg_color = _parse_color(background_color)
        bg_x0 = final_x + (text_bbox[0] if text_bbox else 0) - background_padding
        bg_y0 = final_y + (text_bbox[1] if text_bbox else 0) - background_padding
        bg_x1 = (
            final_x
            + (text_bbox[0] if text_bbox else 0)
            + text_width
            + background_padding
        )
        bg_y1 = (
            final_y
            + (text_bbox[1] if text_bbox else 0)
            + text_height
            + background_padding
        )

        bg_x0 = max(0, bg_x0)
        bg_y0 = max(0, bg_y0)
        bg_x1 = min(img_width, bg_x1)
        bg_y1 = min(img_height, bg_y1)

        if bg_x1 > bg_x0 and bg_y1 > bg_y0:
            if isinstance(parsed_bg_color, tuple) and len(parsed_bg_color) == 3:
                bg_color_tuple_with_alpha = parsed_bg_color + (255,)
            elif isinstance(parsed_bg_color, tuple) and len(parsed_bg_color) == 4:
                bg_color_tuple_with_alpha = parsed_bg_color
            else:  # String color name
                from PIL import ImageColor  # Moved import here

                try:
                    bg_color_tuple_with_alpha = ImageColor.getcolor(
                        parsed_bg_color, "RGBA"
                    )
                except ValueError:
                    logger.warning(
                        f"Invalid background color name: {background_color}. Defaulting to semi-transparent black."
                    )
                    bg_color_tuple_with_alpha = (0, 0, 0, 128)

            if pic.mode != "RGBA" and bg_color_tuple_with_alpha[3] < 255:
                overlay = Image.new("RGBA", pic.size, (0, 0, 0, 0))
                draw_overlay = ImageDraw.Draw(overlay)
                draw_overlay.rectangle(
                    [bg_x0, bg_y0, bg_x1, bg_y1], fill=bg_color_tuple_with_alpha
                )
                # Ensure pic is converted to RGBA before pasting if it's not already, to preserve alpha
                if pic.mode != "RGBA":
                    pic = pic.convert("RGBA")
                    draw = ImageDraw.Draw(
                        pic
                    )  # Re-create draw object for the new pic mode
                pic.alpha_composite(overlay)
            else:  # Main image is RGBA or background is opaque
                # If pic was not RGBA initially but background is opaque, ensure draw object is for current pic mode
                if (
                    draw.mode != pic.mode
                ):  # e.g. pic was RGB, bg_color is opaque, draw was made for RGB
                    # This case should be handled by the initial draw = ImageDraw.Draw(pic, "RGBA" if background_color else pic.mode)
                    # but as a safeguard:
                    pass  # Assuming draw object is appropriate or pic is already RGBA
                draw.rectangle(
                    [bg_x0, bg_y0, bg_x1, bg_y1], fill=bg_color_tuple_with_alpha
                )

    draw.text((final_x, final_y), text_to_draw, font=font, fill=parsed_text_color)
    return pic

# Simple in-memory cache for the daily sun path SVG
_sun_path_cache = {}

def _add_sun_path_overlay(
    pic: Image.Image,
    global_config: Dict,
    camera_config: Dict,
    step_config: Dict,
) -> Image.Image:
    """
    Generates and overlays the sun path SVG onto the image.
    """
    # Prioritize getting coordinates from the camera_config, fallback to global
    lat = camera_config.get("latitude") or global_config.get("latitude")
    lon = camera_config.get("longitude") or global_config.get("longitude")
    tz_str = camera_config.get("timezone") or global_config.get("timezone", "UTC")

    if not lat or not lon:
        logger.error(
            "sun_path overlay enabled, but 'latitude' and 'longitude' not found "
            "in the camera's configuration or the global configuration. Skipping."
        )
        return pic

    now = datetime.now(pytz.timezone(tz_str))
    today = now.date()

    # Use cache if available
    if today not in _sun_path_cache:
        logger.info(f"Generating new sun path SVG for {today}")
        _sun_path_cache[today] = create_sun_path_svg(
            date=today,
            latitude=lat,
            longitude=lon,
            major_bar_width=step_config.get("major_bar_width", 1),
            minor_bar_width=step_config.get("minor_bar_width", 1),
            major_bar_color=step_config.get("major_bar_color", "darkgrey"),
            minor_bar_color=step_config.get("minor_bar_color", "lightgrey"),
            background_color=step_config.get("background_color", "transparent"),
            sun_arc_color=step_config.get("sun_arc_color", "rgba(255, 255, 0, 0.5)"),
            timezone=tz_str,
        )
    
    base_svg = _sun_path_cache[today]
    
    final_svg = overlay_time_bar(
        svg_content=base_svg,
        time_to_overlay=now,
        overlay_rect_width=step_config.get("overlay_rect_width", 5),
        overlay_border_width=step_config.get("overlay_border_width", 2),
        overlay_border_color=step_config.get("overlay_border_color", "white"),
        overlay_rect_height_ratio=step_config.get("overlay_rect_height_ratio", 1.0),
    )

    try:
        overlay_width = step_config.get("overlay_width", pic.width)
        position = step_config.get("position", "top_left")
        padding = step_config.get("padding", 10)

        # Convert SVG to PNG in memory, scaled to the desired width
        png_data = cairosvg.svg2png(
            bytestring=final_svg.encode("utf-8"), output_width=overlay_width
        )
        overlay_img = Image.open(io.BytesIO(png_data))

        # Calculate position
        img_width, img_height = pic.size
        ov_width, ov_height = overlay_img.size

        if position == "top_left":
            x, y = padding, padding
        elif position == "top_right":
            x, y = img_width - ov_width - padding, padding
        elif position == "bottom_left":
            x, y = padding, img_height - ov_height - padding
        elif position == "bottom_right":
            x, y = img_width - ov_width - padding, img_height - ov_height - padding
        elif position == "top_center":
            x, y = (img_width - ov_width) // 2, padding
        elif position == "bottom_center":
            x, y = (img_width - ov_width) // 2, img_height - ov_height - padding
        else:
            logger.warning(f"Unrecognized position for sun_path: {position}. Defaulting to top_left.")
            x, y = padding, padding

        # Paste the overlay onto the main image
        if pic.mode != "RGBA":
            pic = pic.convert("RGBA")
        
        pic.paste(overlay_img, (x, y), overlay_img)

    except Exception as e:
        logger.error(f"Failed to create or overlay sun path SVG: {e}")

    return pic



def add_timestamp(
    pic: Image.Image,
    text_format: str = "%Y-%m-%d %H:%M:%S %Z",
    position: str = "bottom_right",
    size: int = 24,
    color: Union[str, Tuple[int, int, int]] = "white",
    font_path: Optional[str] = None,
    background_color: Optional[Union[str, Tuple[int, int, int]]] = None,
    background_padding: int = 2,
    custom_text: Optional[str] = None,
    timezone: str = "UTC",
) -> Image.Image:
    """Adds a timestamp and optional custom text to the image by utilizing _add_text_overlay."""
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        formatted_time = now.strftime(text_format)
        if custom_text:
            final_text_to_draw = f"{custom_text} {formatted_time}"
        else:
            final_text_to_draw = formatted_time
    except Exception as e:
        logger.error(f"Error formatting timestamp: {e}. Using default format.")
        formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if custom_text:
            final_text_to_draw = f"{custom_text} {formatted_time}"
        else:
            final_text_to_draw = formatted_time

    return _add_text_overlay(
        pic=pic,
        text_to_draw=final_text_to_draw,
        position=position,
        size=size,
        color=color,
        font_path=font_path,
        background_color=background_color,
        background_padding=background_padding,
    )


def postprocess(
    pic: Image.Image,
    postprocessing_steps: list,
    global_config: Optional[Dict] = None,
    camera_config: Optional[Dict] = None,
) -> Tuple[Image.Image, dict]:
    """
    Applies a series of post-processing steps to an image.
    """
    if global_config is None:
        global_config = {}
    if camera_config is None:
        camera_config = {}
    exif_data = pic.info.get("exif") or b""
    
    # Correct orientation based on EXIF data before any processing
    pic = ImageOps.exif_transpose(pic)

    for step in postprocessing_steps:
        if step["type"] == "crop":
            logger.debug(f"Cropping image to area: {step['area']}")
            pic = crop(pic, step["area"])
        elif step["type"] == "resize":
            logger.debug(
                f"Resizing image to width: {step.get('width')}, height: {step.get('height')}"
            )
            pic = resize(pic, step.get("width"), step.get("height"))
        elif step["type"] == "rotate":
            if "angle" in step:
                logger.debug(f"Rotating image by {step['angle']} degrees")
                pic = rotate(pic, step["angle"])
        elif step["type"] == "awb":
            logger.debug("Applying auto white balance to image")
            pic = auto_white_balance(pic)
        elif step["type"] == "timestamp":
            if step.get("enabled", False):
                logger.debug(
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
                    font_path=step.get(
                        "font_path"
                    ),  # Allow custom font path from config
                    background_color=step.get("background_color", None),
                    background_padding=step.get("background_padding", 2),
                    custom_text=step.get("custom_text", None),
                    timezone=global_config.get("timezone", "UTC"),
                )
        elif step["type"] == "text":
            if step.get("enabled", False) and step.get("text_content"):
                logger.debug(
                    f"Adding generic text overlay with config: "
                    f"text_content='{step.get('text_content')}', "
                    f"position={step.get('position', 'bottom_right')}, "
                    f"size={step.get('size', 24)}, "
                    f"color={step.get('color', 'white')}, "
                    f"font_path={step.get('font_path', None)}, "
                    f"background_color={step.get('background_color', None)}, "
                    f"background_padding={step.get('background_padding', 2)}"
                )
                pic = _add_text_overlay(
                    pic=pic,
                    text_to_draw=step.get("text_content"),
                    position=step.get("position", "bottom_right"),
                    size=step.get("size", 24),
                    color=step.get("color", "white"),
                    font_path=step.get("font_path", None),
                    background_color=step.get("background_color", None),
                    background_padding=step.get("background_padding", 2),
                )
            elif not step.get("text_content") and step.get("enabled", False):
                logger.warning(
                    "Generic text step is enabled but no 'text_content' was provided."
                )
        elif step["type"] == "sun_path":
            if step.get("enabled", False):
                logger.debug("Adding sun path overlay")
                pic = _add_sun_path_overlay(pic, global_config, camera_config, step)

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
    logger.debug(f"Cropping picture to {crop_points}")
    return pic.crop(crop_points)


def rotate(pic: Image.Image, angle: int) -> Image.Image:
    """
    Rotates an image by a specified angle.
    """
    return pic.rotate(angle, expand=True)


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


def gather_metrics(image_path: str, camera_name: str):
    """
    Reads metadata from an image file using pyexiv2 and updates Prometheus metrics.
    """
    try:
        with pyexiv2.Image(image_path) as img:
            exif = img.read_exif()

            # Basic file stats
            try:
                stat = os.stat(image_path)
                metric_picture_size_bytes.labels(camera_name=camera_name).set(
                    stat.st_size
                )

                # Get image dimensions from EXIF or fallback to reading image
                width = exif.get("Exif.Image.ImageWidth") or exif.get(
                    "Exif.Photo.PixelXDimension"
                )
                height = exif.get("Exif.Image.ImageLength") or exif.get(
                    "Exif.Photo.PixelYDimension"
                )

                if width and height:
                    metric_picture_width_pixels.labels(camera_name=camera_name).set(
                        int(width)
                    )
                    metric_picture_height_pixels.labels(camera_name=camera_name).set(
                        int(height)
                    )
                else:
                    # Fallback to PIL if dimensions not in EXIF
                    with Image.open(image_path) as pil_img:
                        metric_picture_width_pixels.labels(camera_name=camera_name).set(
                            pil_img.width
                        )
                        metric_picture_height_pixels.labels(
                            camera_name=camera_name
                        ).set(pil_img.height)

            except Exception as e:
                logger.error(
                    f"Error getting file stats or dimensions for {image_path}: {e}"
                )

            # EXIF Metrics
            def get_exif_value(key, default=0):
                v = exif.get(key)
                if v is None:
                    return default
                try:
                    # Fractions are returned as 'num/den' strings
                    if isinstance(v, str) and "/" in v:
                        num, den = v.split("/")
                        return float(num) / float(den)
                    return float(v)
                except (ValueError, TypeError):
                    return default

            metric_picture_iso.labels(camera_name=camera_name).set(
                get_exif_value("Exif.Photo.ISOSpeedRatings")
            )
            metric_picture_focal_length_mm.labels(camera_name=camera_name).set(
                get_exif_value("Exif.Photo.FocalLength")
            )
            metric_picture_aperture.labels(camera_name=camera_name).set(
                get_exif_value("Exif.Photo.FNumber")
            )
            metric_picture_exposure_time_seconds.labels(camera_name=camera_name).set(
                get_exif_value("Exif.Photo.ExposureTime")
            )
            metric_picture_white_balance.labels(camera_name=camera_name).set(
                get_exif_value("Exif.Photo.WhiteBalance")
            )

            logger.debug(f"Successfully gathered metrics for {image_path}")

    except Exception as e:
        logger.error(f"Error reading metadata from {image_path} with pyexiv2: {e}")
