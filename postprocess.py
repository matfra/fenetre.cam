
import numpy as np
from PIL import Image
from skimage import exposure
from typing import Optional

def postprocess(pic: Image, postprocessing_steps: list) -> Image:
    """
    Applies a series of post-processing steps to an image.
    """
    for step in postprocessing_steps:
        if step["type"] == "crop":
            pic = crop(pic, step["area"])
        elif step["type"] == "resize":
            pic = resize(pic, step.get("width"), step.get("height"))
        elif step["type"] == "awb":
            pic = auto_white_balance(pic)
    return pic

def crop(pic: Image, area: str) -> Image:
    """
    Crops an image to a specified area.
    """
    return pic.crop([int(i) for i in area.split(",")])

# If only one dimension is provided, the other will be calculated based on the aspect ratio of the original image or the cropped area.
# If both dimensions are provided, the image will be resized to those exact dimensions
def resize(pic: Image, width: Optional[int] = None, height: Optional[int] = None) -> Image:
    """
    Resizes an image to a specified width and height.
    """
    if width is None and height is None:
        return pic
    if width is None:
        aspect_ratio = pic.width / pic.height
        width = int(height * aspect_ratio)
    if height is None:
        aspect_ratio = pic.height / pic.width
        height = int(width * aspect_ratio)
    return pic.resize(size=(width, height), reducing_gap=3.0)

def auto_white_balance(pic: Image) -> Image:
    """
    Applies auto white balance to an image.
    """
    # Convert the image to a NumPy array
    img_array = np.array(pic)

    # Perform auto white balance using histogram equalization on each channel
    img_array_awb = np.zeros_like(img_array)
    for channel in range(img_array.shape[2]):
        img_array_awb[:, :, channel] = exposure.equalize_hist(img_array[:, :, channel]) * 255

    # Convert the NumPy array back to a PIL image
    return Image.fromarray(img_array_awb.astype(np.uint8))
