import platform
import os
from datetime import datetime


def is_raspberry_pi():
    """
    Checks if the current platform is a Raspberry Pi.
    """
    return platform.machine() in ("armv7l", "aarch64")


def rotate_log_file(log_file_path: str):
    """Rotates a log file if it's older than 24 hours."""
    if os.path.exists(log_file_path) and (datetime.now() - datetime.fromtimestamp(os.path.getmtime(log_file_path))).days > 1:
        old_log_file_path = log_file_path + ".1"
        if os.path.exists(old_log_file_path):
            os.remove(old_log_file_path)
        os.rename(log_file_path, old_log_file_path)