import yaml
from absl import logging
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class StorageManagementConfig(BaseModel):
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
    storage_management: StorageManagementConfig

class HttpServerConfig(BaseModel):
    port: int = 8888
    host: str = "0.0.0.0"
    enabled: bool = True

class ConfigServerConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8889

class UIConfig(BaseModel):
    landing_page: str = "list"
    fullscreen_camera: str = "a-cool-http-cam-with-clouds"

class PostprocessingConfig(BaseModel):
    type: str
    enabled: Optional[bool] = True
    area: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    position: Optional[str] = None
    size: Optional[int] = None
    color: Optional[str] = None
    format: Optional[str] = None

class SunriseSunsetConfig(BaseModel):
    enabled: bool = True

class CameraConfig(BaseModel):
    url: Optional[str] = None
    sky_area: Optional[str] = None
    work_dir_max_size_GB: Optional[int] = None
    ssim_area: Optional[str] = None
    ssim_setpoint: Optional[float] = None
    timeout_s: int = 20
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sunrise_sunset: Optional[SunriseSunsetConfig] = None
    postprocessing: Optional[List[PostprocessingConfig]] = None
    snap_interval_s: Optional[int] = None
    disabled: bool = False
    local_command: Optional[str] = None
    gopro_ip: Optional[str] = None
    gopro_ble_identifier: Optional[str] = None
    gopro_root_ca: Optional[str] = None
    gopro_preset: Optional[str] = None
    gopro_utility_poll_interval_s: Optional[int] = None
    gopro_bluetooth_retry_delay_s: Optional[int] = None

class FenetreConfig(BaseModel):
    global_config: GlobalConfig = Field(..., alias='global')
    http_server: HttpServerConfig
    config_server: ConfigServerConfig
    ui: UIConfig
    cameras: Dict[str, CameraConfig]

def config_load(config_file_path: str) -> list[dict]:
    try:
        with open(config_file_path, "r") as f:
            config = yaml.safe_load(f)
            res = []
            for section in ["http_server", "cameras", "global", "admin_server"]:
                res.append(config.get(section, {}))
            return res
    except FileNotFoundError:
        logging.error(f"Configuration file {config_file_path} not found.")
        return [{}, {}, {}]
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML configuration file {config_file_path}: {e}")
        return [{}, {}, {}]

def load_and_validate_config(config_file_path: str) -> Optional[FenetreConfig]:
    try:
        with open(config_file_path, "r") as f:
            config_data = yaml.safe_load(f)
        return FenetreConfig(**config_data)
    except FileNotFoundError:
        logging.error(f"Configuration file {config_file_path} not found.")
        return None
    except Exception as e:
        logging.error(f"Error loading or validating configuration: {e}")
        return None

def get_log_dir() -> str:
    # This is a temporary hack until the config is fully migrated
    # to the pydantic models.
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
            return config.get("global", {}).get("log_dir", "/tmp/fenetre")
    except FileNotFoundError:
        return "/tmp/fenetre"
