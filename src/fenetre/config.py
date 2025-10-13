import logging
import os
from typing import Dict, Tuple

import yaml

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


def _bool(value, path, errors, default=None):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    errors.append(f"{path}: expected bool, got {type(value).__name__}")
    return default


def _int(value, path, errors, default=None, min_value=None, max_value=None):
    if value is None:
        return default
    if isinstance(value, int):
        if (min_value is not None and value < min_value) or (
            max_value is not None and value > max_value
        ):
            errors.append(
                f"{path}: expected int in range [{min_value},{max_value}], got {value}"
            )
            return default
        return value
    errors.append(f"{path}: expected int, got {type(value).__name__}")
    return default


def _float(value, path, errors, default=None, min_value=None, max_value=None):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        v = float(value)
        if (min_value is not None and v < min_value) or (
            max_value is not None and v > max_value
        ):
            errors.append(
                f"{path}: expected number in range [{min_value},{max_value}], got {value}"
            )
            return default
        return v
    errors.append(f"{path}: expected number, got {type(value).__name__}")
    return default


def _str(value, path, errors, default=None, choices=None):
    if value is None:
        return default
    if isinstance(value, str):
        if choices and value not in choices:
            errors.append(
                f"{path}: expected one of {sorted(list(choices))}, got '{value}'"
            )
            return default
        return value
    errors.append(f"{path}: expected str, got {type(value).__name__}")
    return default


def _dict(value, path, errors, default=None):
    if value is None:
        return default or {}
    if isinstance(value, dict):
        return value
    errors.append(f"{path}: expected mapping, got {type(value).__name__}")
    return default or {}


def _warn_unknown_keys(section_name: str, got: Dict, allowed_keys: set):
    for k in got.keys():
        if k not in allowed_keys:
            logger.warning(f"{section_name}: unknown key '{k}' will be ignored")


def _validate_global(cfg: Dict, errors) -> Dict:
    allowed = {
        "work_dir",
        "log_dir",
        "logging_level",
        "logging_levels",
        "timezone",
        "sunrise_sunset_interval_s",
        "storage_management",
        "user_agent",
        "log_max_bytes",
        "log_backup_count",
        "ui",
    }
    _warn_unknown_keys("global", cfg, allowed)

    out: Dict = {}
    work_dir = _str(cfg.get("work_dir"), "global.work_dir", errors)
    if not work_dir:
        errors.append("global.work_dir: required string is missing")
    else:
        out["work_dir"] = os.path.abspath(work_dir)

    log_dir = cfg.get("log_dir")
    if log_dir is not None:
        out["log_dir"] = os.path.abspath(_str(log_dir, "global.log_dir", errors))

    level = cfg.get("logging_level", "INFO")
    level = _str(level, "global.logging_level", errors)
    if isinstance(level, str):
        level = level.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            errors.append(
                f"global.logging_level: unsupported value '{level}' (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
            )
    out["logging_level"] = level or "INFO"

    logging_levels = cfg.get("logging_levels")
    if logging_levels is not None and not isinstance(logging_levels, dict):
        errors.append("global.logging_levels: expected mapping of module->level")
        out["logging_levels"] = {}
    else:
        out["logging_levels"] = logging_levels or {}

    tz = _str(cfg.get("timezone"), "global.timezone", errors)
    if not tz:
        errors.append("global.timezone: required string is missing")
    out["timezone"] = tz or "UTC"

    out["sunrise_sunset_interval_s"] = _int(
        cfg.get("sunrise_sunset_interval_s"),
        "global.sunrise_sunset_interval_s",
        errors,
        default=10,
        min_value=1,
    )

    sm = _dict(cfg.get("storage_management"), "global.storage_management", errors)
    if sm:
        sm_out = {}
        sm_out["enabled"] = _bool(
            sm.get("enabled"),
            "global.storage_management.enabled",
            errors,
            default=False,
        )
        sm_out["dry_run"] = _bool(
            sm.get("dry_run"), "global.storage_management.dry_run", errors, default=True
        )
        sm_out["check_interval_s"] = _int(
            sm.get("check_interval_s"),
            "global.storage_management.check_interval_s",
            errors,
            default=300,
            min_value=1,
        )
        sm_out["work_dir_max_size_GB"] = _int(
            sm.get("work_dir_max_size_GB"),
            "global.storage_management.work_dir_max_size_GB",
            errors,
            default=10,
            min_value=1,
        )
        out["storage_management"] = sm_out

    out["user_agent"] = _str(cfg.get("user_agent"), "global.user_agent", errors)
    out["log_max_bytes"] = _int(
        cfg.get("log_max_bytes"),
        "global.log_max_bytes",
        errors,
        default=10_000_000,
        min_value=1024,
    )
    out["log_backup_count"] = _int(
        cfg.get("log_backup_count"),
        "global.log_backup_count",
        errors,
        default=5,
        min_value=0,
    )
    return out


def _validate_http(cfg: Dict, errors) -> Dict:
    allowed = {"enabled", "listen"}
    _warn_unknown_keys("http_server", cfg, allowed)
    out = {}
    out["enabled"] = _bool(
        cfg.get("enabled"), "http_server.enabled", errors, default=True
    )
    out["listen"] = _str(
        cfg.get("listen"), "http_server.listen", errors, default="0.0.0.0:8888"
    )
    return out


def _validate_admin(cfg: Dict, errors) -> Dict:
    allowed = {"enabled", "listen"}
    _warn_unknown_keys("admin_server", cfg, allowed)
    out = {}
    out["enabled"] = _bool(
        cfg.get("enabled"), "admin_server.enabled", errors, default=True
    )
    out["listen"] = _str(
        cfg.get("listen"),
        "admin_server.listen",
        errors,
        default="0.0.0.0:8889 [::]:8889",
    )
    return out


def _validate_timelapse(cfg: Dict, errors) -> Dict:
    allowed = {"frequent_timelapse", "daily_timelapse"}
    _warn_unknown_keys("timelapse", cfg, allowed)
    out: Dict = {}

    ft = _dict(cfg.get("frequent_timelapse"), "timelapse.frequent_timelapse", errors)
    if ft is not None:
        ft_out = {}
        ft_out["enabled"] = _bool(
            ft.get("enabled"),
            "timelapse.frequent_timelapse.enabled",
            errors,
            default=True,
        )
        ft_out["ffmpeg_2pass"] = _bool(
            ft.get("ffmpeg_2pass"),
            "timelapse.frequent_timelapse.ffmpeg_2pass",
            errors,
            default=False,
        )
        ft_out["ffmpeg_options"] = _str(
            ft.get("ffmpeg_options"),
            "timelapse.frequent_timelapse.ffmpeg_options",
            errors,
        )
        ft_out["file_extension"] = _str(
            ft.get("file_extension"),
            "timelapse.frequent_timelapse.file_extension",
            errors,
            default="mp4",
        )
        out["frequent_timelapse"] = ft_out

    dt = _dict(cfg.get("daily_timelapse"), "timelapse.daily_timelapse", errors)
    if dt is not None:
        dt_out = {}
        dt_out["enabled"] = _bool(
            dt.get("enabled"), "timelapse.daily_timelapse.enabled", errors, default=True
        )
        dt_out["framerate"] = _int(
            dt.get("framerate"),
            "timelapse.daily_timelapse.framerate",
            errors,
            default=60,
            min_value=1,
        )
        dt_out["ffmpeg_options"] = _str(
            dt.get("ffmpeg_options"), "timelapse.daily_timelapse.ffmpeg_options", errors
        )
        dt_out["ffmpeg_2pass"] = _bool(
            dt.get("ffmpeg_2pass"),
            "timelapse.daily_timelapse.ffmpeg_2pass",
            errors,
            default=False,
        )
        dt_out["file_extension"] = _str(
            dt.get("file_extension"),
            "timelapse.daily_timelapse.file_extension",
            errors,
            default="webm",
        )
        out["daily_timelapse"] = dt_out

    return out


def _validate_cameras(cfg: Dict, errors) -> Dict:
    if cfg is None:
        return {}
    if not isinstance(cfg, dict):
        errors.append("cameras: expected mapping of camera_name -> camera_config")
        return {}

    out: Dict = {}
    for name, cam in cfg.items():
        if not isinstance(cam, dict):
            errors.append(f"cameras.{name}: expected mapping, got {type(cam).__name__}")
            continue

        cam_out = {}
        # Capture method: require at least one of url, local_command, gopro_ip or capture_method==picamera2
        url = cam.get("url")
        local_cmd = cam.get("local_command")
        gopro_ip = cam.get("gopro_ip")
        capture_method = cam.get("capture_method")
        has_picamera2 = (
            isinstance(capture_method, str) and capture_method == "picamera2"
        )
        if not (url or local_cmd or gopro_ip or has_picamera2):
            errors.append(
                f"cameras.{name}: one of 'url', 'local_command', 'gopro_ip' or capture_method='picamera2' is required"
            )

        if url is not None:
            cam_out["url"] = _str(url, f"cameras.{name}.url", errors)
        if local_cmd is not None:
            cam_out["local_command"] = _str(
                local_cmd, f"cameras.{name}.local_command", errors
            )
        if gopro_ip is not None:
            cam_out["gopro_ip"] = _str(gopro_ip, f"cameras.{name}.gopro_ip", errors)
        if capture_method is not None:
            cam_out["capture_method"] = _str(
                capture_method, f"cameras.{name}.capture_method", errors
            )

        cam_out["timeout_s"] = _int(
            cam.get("timeout_s"),
            f"cameras.{name}.timeout_s",
            errors,
            default=60,
            min_value=1,
        )
        cam_out["cache_bust"] = _bool(
            cam.get("cache_bust"), f"cameras.{name}.cache_bust", errors, default=False
        )
        cam_out["mozjpeg_optimize"] = _bool(
            cam.get("mozjpeg_optimize"),
            f"cameras.{name}.mozjpeg_optimize",
            errors,
            default=False,
        )
        cam_out["gather_metrics"] = _bool(
            cam.get("gather_metrics"),
            f"cameras.{name}.gather_metrics",
            errors,
            default=True,
        )

        # SSIM controls
        cam_out["ssim_setpoint"] = _float(
            cam.get("ssim_setpoint"),
            f"cameras.{name}.ssim_setpoint",
            errors,
            default=0.85,
            min_value=0.0,
            max_value=1.0,
        )
        if cam.get("ssim_area") is not None:
            s = _str(cam.get("ssim_area"), f"cameras.{name}.ssim_area", errors)
            cam_out["ssim_area"] = s
        if cam.get("sky_area") is not None:
            s = _str(cam.get("sky_area"), f"cameras.{name}.sky_area", errors)
            cam_out["sky_area"] = s

        # Geo / sunrise-sunset (lat/lon only; hard break)
        if cam.get("latitude") is not None:
            errors.append(
                f"cameras.{name}.latitude: unsupported key; use 'lat' instead"
            )
        if cam.get("longitude") is not None:
            errors.append(
                f"cameras.{name}.longitude: unsupported key; use 'lon' instead"
            )
        if cam.get("lat") is not None:
            cam_out["lat"] = _float(
                cam.get("lat"),
                f"cameras.{name}.lat",
                errors,
                min_value=-90,
                max_value=90,
            )
        if cam.get("lon") is not None:
            cam_out["lon"] = _float(
                cam.get("lon"),
                f"cameras.{name}.lon",
                errors,
                min_value=-180,
                max_value=180,
            )

        # Optional postprocessing list (pass-through, validated elsewhere)
        if cam.get("postprocessing") is not None:
            if isinstance(cam.get("postprocessing"), list):
                cam_out["postprocessing"] = cam.get("postprocessing")
            else:
                errors.append(f"cameras.{name}.postprocessing: expected list")

        # Copy any known keys used elsewhere without deep validation to preserve behavior
        for k in (
            "work_dir_max_size_GB",
            "snap_interval_s",
            "tuning_file",
            "exposure_time",
            "analogue_gain",
            "denoise_mode",
            "gopro_ble_identifier",
            "bluetooth_adapter",
            "gopro_utility_poll_interval_s",
            "bluetooth_retry_delay_s",
            "gopro_usb",
            "gopro_model",
            "name",
        ):
            if k in cam:
                cam_out[k] = cam[k]

        if "gopro_model" in cam_out:
            cam_out["gopro_model"] = _str(
                cam_out["gopro_model"],
                f"cameras.{name}.gopro_model",
                errors,
                default="open_gopro",
                choices={"hero6", "open_gopro"},
            )
        else:
            cam_out["gopro_model"] = "open_gopro"

        out[name] = cam_out

    return out


def _extract_sections(config: Dict) -> Tuple[Dict, Dict, Dict, Dict, Dict]:
    http_cfg = config.get("http_server", {}) or {}
    cameras_cfg = config.get("cameras", {}) or {}
    global_cfg = config.get("global", {}) or {}
    admin_cfg = config.get("admin_server", {}) or {}
    timelapse_cfg = config.get("timelapse", {}) or {}
    return http_cfg, cameras_cfg, global_cfg, admin_cfg, timelapse_cfg


def config_load(config_file_path: str) -> Tuple[Dict, Dict, Dict, Dict, Dict]:
    try:
        with open(config_file_path, "r") as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error(f"Configuration file {config_file_path} not found.")
        # Return 5 empty sections to maintain unpacking compatibility
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML configuration file {config_file_path}: {e}")
        raise

    http_cfg, cameras_cfg, global_cfg, admin_cfg, timelapse_cfg = _extract_sections(raw)

    errors = []

    http_out = _validate_http(http_cfg, errors)
    cameras_out = _validate_cameras(cameras_cfg, errors)
    global_out = _validate_global(global_cfg, errors)
    admin_out = _validate_admin(admin_cfg, errors)
    timelapse_out = _validate_timelapse(timelapse_cfg, errors)

    if errors:
        # Be strict: better fail fast with actionable messages
        msg = "Invalid configuration:\n" + "\n".join(f" - {e}" for e in errors)
        logger.error(msg)
        raise ConfigError(msg)

    return http_out, cameras_out, global_out, admin_out, timelapse_out
