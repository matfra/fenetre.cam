import getpass
import logging
import os
from typing import Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# Pydantic Models for Configuration Structure
class StorageManagementConfig(BaseModel):
    enabled: bool = False
    dry_run: bool = True
    check_interval_s: int = 300
    work_dir_max_size_GB: int = 10


class GlobalConfig(BaseModel):
    title: str = f"{getpass.getuser()}'s cameras"
    work_dir: str = "data"
    log_dir: str = "logs"
    timezone: str = "America/Los_Angeles"
    sunrise_sunset_interval_s: int = 10
    storage_management: StorageManagementConfig = Field(default_factory=StorageManagementConfig)
    pic_dir: Optional[str] = None


class FrequentTimelapseConfig(BaseModel):
    enabled: bool = True
    interval_s: int = 1200
    ffmpeg_2pass: bool = False
    ffmpeg_options: str = "-c:v libx264 -preset veryfast -crf 28"
    file_extension: str = "mp4"
    framerate: int = 30


class DailyTimelapseConfig(BaseModel):
    enabled: bool = True
    framerate: int = 60
    ffmpeg_options: str = "-c:v libvpx-vp9 -b:v 0 -crf 30 -deadline best"
    ffmpeg_2pass: bool = True
    file_extension: str = "webm"


class TimelapseConfig(BaseModel):
    frequent_timelapse: FrequentTimelapseConfig = Field(default_factory=FrequentTimelapseConfig)
    daily_timelapse: DailyTimelapseConfig = Field(default_factory=DailyTimelapseConfig)


class HttpServerConfig(BaseModel):
    enabled: bool = True
    listen: str = "0.0.0.0:8888"


class AdminServerConfig(BaseModel):
    enabled: bool = True
    listen: str = "0.0.0.0:8889"


class UiConfig(BaseModel):
    landing_page: str = "list"
    fullscreen_camera: Optional[str] = None


class CropStep(BaseModel):
    type: Literal["crop"]
    area: str


class ResizeStep(BaseModel):
    type: Literal["resize"]
    width: int
    height: int


class AwbStep(BaseModel):
    type: Literal["awb"]


class TimestampStep(BaseModel):
    type: Literal["timestamp"]
    enabled: bool = True
    position: str = "bottom_right"
    size: int = 24
    color: str = "white"
    format: str = "%Y-%m-%d %H:%M:%S %Z"


PostprocessingStep = Union[CropStep, ResizeStep, AwbStep, TimestampStep]


class SunriseSunsetConfig(BaseModel):
    enabled: bool = False


class CameraConfig(BaseModel):
    url: Optional[str] = None
    local_command: Optional[str] = None
    gopro_ip: Optional[str] = None
    gopro_ble_identifier: Optional[str] = None
    gopro_root_ca: Optional[str] = None
    gopro_preset_day: Optional[Dict[str, Any]] = None
    gopro_preset_night: Optional[Dict[str, Any]] = None
    gopro_utility_poll_interval_s: int = 10
    capture_method: Optional[str] = None
    tuning_file: Optional[str] = None
    exposure_time: Optional[int] = None
    analogue_gain: Optional[float] = None
    denoise_mode: Optional[str] = None
    timeout_s: int = 60
    cache_bust: bool = False
    sky_area: Optional[str] = None
    ssim_area: Optional[str] = None
    ssim_setpoint: float = 0.9
    snap_interval_s: Optional[int] = None
    postprocessing: List[PostprocessingStep] = Field(default_factory=list)
    mozjpeg_optimize: bool = False
    gather_metrics: bool = True
    disabled: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sunrise_sunset: SunriseSunsetConfig = Field(default_factory=SunriseSunsetConfig)
    work_dir_max_size_GB: Optional[int] = None
    description: Optional[str] = None


class AppConfig(BaseModel):
    global_config: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    timelapse: TimelapseConfig = Field(default_factory= TimelapseConfig)
    http_server: HttpServerConfig = Field(default_factory=HttpServerConfig)
    admin_server: AdminServerConfig = Field(default_factory=AdminServerConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    cameras: Dict[str, CameraConfig] = Field(default_factory=dict)


# Singleton Metaclass
class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class FenetreConfig(metaclass=Singleton):
    _config: AppConfig
    _config_file: Optional[str]

    def __init__(self, config_file: Optional[str] = None):
        self._config_file = config_file
        self.load_config()

    def load_config(self):
        if not self._config_file or not os.path.exists(self._config_file):
            if self._config_file:
                logger.warning(f"Config file not found at {self._config_file}, using defaults")
            else:
                logger.info("No config file provided, using defaults")
            self._config = AppConfig()
            return

        logger.info(f"Loading config from {self._config_file}")
        with open(self._config_file, "r") as f:
            config_data = yaml.safe_load(f) or {}

        try:
            self._config = AppConfig.model_validate(config_data)
        except ValidationError as e:
            logger.error(f"Configuration validation error in {self._config_file}:\n{e}")
            # Fallback to defaults or exit? For now, log error and use defaults.
            logger.error("Falling back to default configuration.")
            self._config = AppConfig()

    def get_config(self) -> AppConfig:
        return self._config

    def save_config(self, config_data: Dict[str, Any]):
        if not self._config_file:
            logger.error("Cannot save configuration: no config file path specified.")
            return

        logger.info(f"Saving config to {self._config_file}")
        with open(self._config_file, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
        self.load_config()  # Reload to ensure consistency and validation