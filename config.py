import yaml
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union

class StorageManagement(BaseModel):
    enabled: bool = True
    dry_run: bool = True
    check_interval_s: int = 300
    work_dir_max_size_GB: int = 10

class GlobalConfig(BaseModel):
    ffmpeg_options: str = "-framerate 30 -c:v libvpx-vp9 -b:v 3M"
    ffmpeg_2pass: bool = False
    work_dir: str
    log_dir: str
    timezone: str = "America/Los_Angeles"
    sunrise_sunset_interval_s: int = 10
    storage_management: StorageManagement = Field(default_factory=StorageManagement)

class HttpServer(BaseModel):
    port: int = 8888
    host: str = "0.0.0.0"
    enabled: bool = True

class ConfigServer(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8889

class UI(BaseModel):
    landing_page: str = "list"
    fullscreen_camera: Optional[str] = None

class PostprocessingStep(BaseModel):
    type: str
    enabled: bool = True
    area: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    position: Optional[str] = None
    size: Optional[int] = None
    color: Optional[str] = None
    format: Optional[str] = None

class SunriseSunset(BaseModel):
    enabled: bool = True

class Camera(BaseModel):
    url: Optional[str] = None
    sky_area: Optional[str] = None
    work_dir_max_size_GB: Optional[int] = None
    ssim_area: Optional[str] = None
    ssim_setpoint: Optional[float] = None
    timeout_s: int = 20
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sunrise_sunset: SunriseSunset = Field(default_factory=SunriseSunset)
    postprocessing: List[PostprocessingStep] = []
    snap_interval_s: Optional[int] = None
    disabled: bool = False
    local_command: Optional[str] = None
    gopro_ip: Optional[str] = None
    gopro_ble_identifier: Optional[str] = None
    gopro_root_ca: Optional[str] = None
    gopro_preset: Optional[str] = None
    gopro_utility_poll_interval_s: int = 10
    gopro_bluetooth_retry_delay_s: int = 180

class Config(BaseModel):
    global_config: GlobalConfig = Field(alias="global")
    http_server: HttpServer
    config_server: ConfigServer
    ui: UI
    cameras: Dict[str, Camera]

_config: Optional[Config] = None

def config_load(config_file_path: str) -> Config:
    global _config
    if _config:
        return _config

    with open(config_file_path, "r") as f:
        config_data = yaml.safe_load(f)
    
    _config = Config.parse_obj(config_data)
    return _config

def get_log_dir() -> str:
    if not _config:
        raise Exception("Config not loaded")
    return _config.global_config.log_dir