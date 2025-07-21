import os

def is_raspberry_pi():
    """Checks if the current platform is a Raspberry Pi."""
    if not os.path.exists('/proc/device-tree/model'):
        return False
    try:
        with open('/proc/device-tree/model', 'r') as f:
            if 'raspberry pi' in f.read().lower():
                return True
    except Exception:
        pass
    return False
