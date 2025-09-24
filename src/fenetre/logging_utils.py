import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional


COLOR_CODES = [
    "\033[31m",
    "\033[32m",
    "\033[33m",
    "\033[34m",
    "\033[35m",
    "\033[36m",
    "\033[91m",
    "\033[92m",
    "\033[93m",
    "\033[94m",
    "\033[95m",
    "\033[96m",
]
RESET = "\033[0m"
MODULE_COLORS: Dict[str, str] = {}


def _module_color(name: str) -> str:
    if not name.startswith("fenetre"):
        return ""
    color = MODULE_COLORS.get(name)
    if not color:
        color = COLOR_CODES[len(MODULE_COLORS) % len(COLOR_CODES)]
        MODULE_COLORS[name] = color
    return color


class ModuleColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        base = super().format(record)
        color = _module_color(record.name)
        if color:
            parts = base.split("]", 1)
            if len(parts) == 2:
                return f"{color}{parts[0]}{RESET}{parts[1]}"
            else:
                return f"{color}{base}{RESET}"
        return base


def setup_logging(
    log_dir: Optional[str] = None,
    level: Optional[str] = None,
    log_max_bytes: int = 10000000,
    log_backup_count: int = 5,
) -> None:
    formatter = ModuleColorFormatter(
        "%(levelname).1s%(asctime)s %(filename)s:%(lineno)d] %(message)s",
        datefmt="%m%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.handlers = []
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "fenetre.log"),
            maxBytes=log_max_bytes,
            backupCount=log_backup_count,
        )
        file_formatter = logging.Formatter(
            "%(levelname).1s%(asctime)s %(filename)s:%(lineno)d] %(message)s",
            datefmt="%m%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root.addHandler(file_handler)
    if level:
        root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    else:
        root.setLevel(logging.INFO)


def apply_module_levels(levels: Dict[str, str]) -> None:
    for name, level_name in levels.items():
        level = getattr(logging, str(level_name).upper(), None)
        if isinstance(level, int):
            logging.getLogger(name).setLevel(level)


def get_camera_logger(
    camera_name: str,
    log_dir: str,
    log_max_bytes: int = 10000000,
    log_backup_count: int = 5,
) -> logging.Logger:
    """Gets a logger for a specific camera with its own rotating file handler."""
    logger = logging.getLogger(f"fenetre.camera.{camera_name}")

    # Prevent adding handlers multiple times
    if logger.hasHandlers() and any(
        isinstance(h, RotatingFileHandler) for h in logger.handlers
    ):
        return logger

    log_file_path = os.path.join(log_dir, f"{camera_name}.log")
    handler = RotatingFileHandler(
        log_file_path, maxBytes=log_max_bytes, backupCount=log_backup_count
    )
    formatter = logging.Formatter(
        "%(levelname).1s%(asctime)s %(filename)s:%(lineno)d] %(message)s",
        datefmt="%m%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)  # Set a default level
    logger.propagate = False  # Don't send to root logger
    return logger
