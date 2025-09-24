import platform
import os
from datetime import datetime


def is_raspberry_pi():
    """
    Checks if the current platform is a Raspberry Pi.
    """
    return platform.machine() in ("armv7l", "aarch64")