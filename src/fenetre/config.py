import logging
import os
import difflib
import re
from typing import Dict, Tuple, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


def _log_config_diff(section_name: str, before: Dict, after: Dict):
    """Logs the difference between two configuration dictionaries using YAML."""
    before_str = yaml.dump(before, sort_keys=True, default_flow_style=False, indent=2)
    after_str = yaml.dump(after, sort_keys=True, default_flow_style=False, indent=2)

    if before_str != after_str:
        diff = difflib.unified_diff(
            before_str.splitlines(keepends=True),
            after_str.splitlines(keepends=True),
            fromfile=f"{section_name}_original",
            tofile=f"{section_name}_validated",
        )
        diff_str = "".join(diff)
        logger.warning(
            f"Configuration for '{section_name}' has been sanitized. "
            "Some values may have been ignored, coerced, or set to defaults.\n"
            f"Configuration diff for '{section_name}':\n{diff_str}"
        )


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
        "storage_management",
        "user_agent",
        "log_max_bytes",
        "log_backup_count",
        "ui",
        "deployment_name",
        "mqtt",
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

    out["deployment_name"] = _str(
        cfg.get("deployment_name"),
        "global.deployment_name",
        errors,
        default="fenetre.cam",
    )

    deployment_name = out.get("deployment_name") or "fenetre.cam"
    sanitized_deployment_name = re.sub(r"[^A-Za-z0-9_-]", "_", deployment_name)
    if not sanitized_deployment_name:
        sanitized_deployment_name = "fenetre"

    ui_cfg = _dict(cfg.get("ui"), "global.ui", errors)
    ui_out = {}
    _warn_unknown_keys(
        "global.ui",
        ui_cfg,
        {
            "landing_page",
            "fullscreen_camera",
            "main_website_url",
            "show_main_website_icon",
            "show_github_icon",
            "show_map_by_default",
            "linked_deployments",
        },
    )  # Add allowed keys for ui here
    ui_out["fullscreen_camera"] = _str(
        ui_cfg.get("fullscreen_camera"),
        "global.ui.fullscreen_camera",
        errors,
        default=None,
    )
    ui_out["landing_page"] = _str(
        ui_cfg.get("landing_page"),
        "global.ui.landing_page",
        errors,
        default="list",
    )
    ui_out["main_website_url"] = _str(
        ui_cfg.get("main_website_url"),
        "global.ui.main_website_url",
        errors,
        default="https://fenetre.cam",
    )
    ui_out["show_main_website_icon"] = _bool(
        ui_cfg.get("show_main_website_icon"),
        "global.ui.show_main_website_icon",
        errors,
        default=True,
    )
    ui_out["show_github_icon"] = _bool(
        ui_cfg.get("show_github_icon"),
        "global.ui.show_github_icon",
        errors,
        default=True,
    )
    ui_out["show_map_by_default"] = _bool(
        ui_cfg.get("show_map_by_default"),
        "global.ui.show_map_by_default",
        errors,
        default=False,
    )
    linked_cfg = ui_cfg.get("linked_deployments", [])
    linked_out = []
    if linked_cfg is None:
        linked_cfg = []
    if isinstance(linked_cfg, list):
        for idx, entry in enumerate(linked_cfg):
            entry_path = f"global.ui.linked_deployments[{idx}]"
            if not isinstance(entry, dict):
                errors.append(
                    f"{entry_path}: expected mapping, got {type(entry).__name__}"
                )
                continue
            base_url = _str(entry.get("base_url"), f"{entry_path}.base_url", errors)
            if not base_url:
                continue
            normalized = {"base_url": base_url}
            if entry.get("name") is not None:
                name = _str(entry.get("name"), f"{entry_path}.name", errors)
                if name:
                    normalized["name"] = name
            if entry.get("cameras_json_url") is not None:
                cameras_json_url = _str(
                    entry.get("cameras_json_url"),
                    f"{entry_path}.cameras_json_url",
                    errors,
                )
                if cameras_json_url:
                    normalized["cameras_json_url"] = cameras_json_url
            linked_out.append(normalized)
    else:
        errors.append(
            f"global.ui.linked_deployments: expected list, got {type(linked_cfg).__name__}"
        )
        linked_out = []
    ui_out["linked_deployments"] = linked_out
    out["ui"] = ui_out

    mqtt_cfg = _dict(cfg.get("mqtt"), "global.mqtt", errors)
    mqtt_out = {}
    _warn_unknown_keys(
        "global.mqtt",
        mqtt_cfg,
        {
            "enabled",
            "host",
            "port",
            "username",
            "password",
            "base_topic",
            "discovery_prefix",
        },
    )
    mqtt_out["enabled"] = _bool(
        mqtt_cfg.get("enabled"), "global.mqtt.enabled", errors, default=False
    )
    mqtt_out["host"] = _str(
        mqtt_cfg.get("host"), "global.mqtt.host", errors, default="localhost"
    )
    mqtt_out["port"] = _int(
        mqtt_cfg.get("port"),
        "global.mqtt.port",
        errors,
        default=1883,
        min_value=1,
        max_value=65535,
    )
    mqtt_out["username"] = _str(
        mqtt_cfg.get("username"),
        "global.mqtt.username",
        errors,
        default=f"fenetre_{sanitized_deployment_name}",
    )
    mqtt_out["password"] = _str(
        mqtt_cfg.get("password"), "global.mqtt.password", errors
    )
    mqtt_out["base_topic"] = _str(
        mqtt_cfg.get("base_topic"),
        "global.mqtt.base_topic",
        errors,
        default=f"fenetre/{sanitized_deployment_name}",
    )
    mqtt_out["discovery_prefix"] = _str(
        mqtt_cfg.get("discovery_prefix"),
        "global.mqtt.discovery_prefix",
        errors,
        default="homeassistant",
    )
    out["mqtt"] = mqtt_out
    return out


def _validate_http(cfg: Dict, errors) -> Dict:
    allowed = {"enabled", "listen", "allow_cors", "cors_allow_origin"}
    _warn_unknown_keys("http_server", cfg, allowed)
    out = {}
    out["enabled"] = _bool(
        cfg.get("enabled"), "http_server.enabled", errors, default=True
    )
    out["listen"] = _str(
        cfg.get("listen"), "http_server.listen", errors, default="0.0.0.0:8888"
    )
    out["allow_cors"] = _bool(
        cfg.get("allow_cors"), "http_server.allow_cors", errors, default=True
    )
    out["cors_allow_origin"] = _str(
        cfg.get("cors_allow_origin"),
        "http_server.cors_allow_origin",
        errors,
        default="https://dev.fenetre.cam",
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


def _validate_day_night_settings(cam_config: Dict, cam_name: str, errors: list) -> Dict:
    """Validate day_settings and night_settings for a camera."""
    out = {}

    def validate_settings_block(settings_key: str) -> Optional[Dict]:
        settings_block = _dict(
            cam_config.get(settings_key), f"cameras.{cam_name}.{settings_key}", errors
        )
        if not settings_block:
            return None

        block_out = {}
        path_prefix = f"cameras.{cam_name}.{settings_key}"

        if "trigger_exposure_composite_value" in settings_block:
            block_out["trigger_exposure_composite_value"] = _float(
                settings_block.get("trigger_exposure_composite_value"),
                f"{path_prefix}.trigger_exposure_composite_value",
                errors,
                min_value=0.0,
            )

        if "urlpaths_commands" in settings_block:
            if isinstance(settings_block["urlpaths_commands"], list):
                block_out["urlpaths_commands"] = settings_block["urlpaths_commands"]
            else:
                errors.append(
                    f"{path_prefix}.urlpaths_commands: expected a list of strings"
                )

        return block_out

    if day_settings := validate_settings_block("day_settings"):
        out["day_settings"] = day_settings
    if night_settings := validate_settings_block("night_settings"):
        out["night_settings"] = night_settings
    if astro_settings := validate_settings_block("astro_settings"):
        out["astro_settings"] = astro_settings

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
        # Capture method: require at least one of url, local_command, gopro_model or capture_method==picamera2
        url = cam.get("url")
        local_cmd = cam.get("local_command")
        gopro_ip = cam.get("gopro_ip")
        gopro_model = cam.get("gopro_model")
        capture_method = cam.get("capture_method")
        has_picamera2 = (
            isinstance(capture_method, str) and capture_method == "picamera2"
        )
        is_gopro = gopro_model is not None
        if not (url or local_cmd or is_gopro or has_picamera2):
            errors.append(
                f"cameras.{name}: one of 'url', 'local_command', 'gopro_model' or capture_method='picamera2' is required"
            )

        if url is not None:
            cam_out["url"] = _str(url, f"cameras.{name}.url", errors)
        if local_cmd is not None:
            cam_out["local_command"] = _str(
                local_cmd, f"cameras.{name}.local_command", errors
            )
        if gopro_ip is not None:
            cam_out["gopro_ip"] = _str(gopro_ip, f"cameras.{name}.gopro_ip", errors)
        if gopro_model is not None:
            validated_model = _str(
                gopro_model,
                f"cameras.{name}.gopro_model",
                errors,
                choices={"hero6", "hero9", "hero11", "open_gopro"},
            )
            if validated_model == "open_gopro":
                # normalize legacy value
                validated_model = "hero11"
            cam_out["gopro_model"] = validated_model
            if gopro_ip is None:
                errors.append(
                    f"cameras.{name}: gopro_model is set but 'gopro_ip' is missing."
                )
        elif gopro_ip is not None:
            errors.append(
                f"cameras.{name}: gopro_ip is set but gopro_model is missing. Specify one of hero6, hero9, or hero11."
            )
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
        ss_cfg = _dict(
            cam.get("sunrise_sunset"), f"cameras.{name}.sunrise_sunset", errors
        )
        if ss_cfg:
            ss_out = {}
            ss_out["enabled"] = _bool(
                ss_cfg.get("enabled"),
                f"cameras.{name}.sunrise_sunset.enabled",
                errors,
                default=False,
            )
            ss_out["interval_s"] = _int(
                ss_cfg.get("interval_s"),
                f"cameras.{name}.sunrise_sunset.interval_s",
                errors,
                default=10,
                min_value=1,
            )
            ss_out["sunrise_offset_start_minutes"] = _int(
                ss_cfg.get("sunrise_offset_start_minutes"),
                f"cameras.{name}.sunrise_sunset.sunrise_offset_start_minutes",
                errors,
                default=60,
            )
            ss_out["sunrise_offset_end_minutes"] = _int(
                ss_cfg.get("sunrise_offset_end_minutes"),
                f"cameras.{name}.sunrise_sunset.sunrise_offset_end_minutes",
                errors,
                default=30,
            )
            ss_out["sunset_offset_start_minutes"] = _int(
                ss_cfg.get("sunset_offset_start_minutes"),
                f"cameras.{name}.sunrise_sunset.sunset_offset_start_minutes",
                errors,
                default=30,
            )
            ss_out["sunset_offset_end_minutes"] = _int(
                ss_cfg.get("sunset_offset_end_minutes"),
                f"cameras.{name}.sunrise_sunset.sunset_offset_end_minutes",
                errors,
                default=60,
            )
            cam_out["sunrise_sunset"] = ss_out

        # Day/Night settings
        cam_out.update(_validate_day_night_settings(cam, name, errors))

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
            "name",
        ):
            if k in cam:
                cam_out[k] = cam[k]

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

    _log_config_diff("global", global_cfg, global_out)
    _log_config_diff("http_server", http_cfg, http_out)
    _log_config_diff("admin_server", admin_cfg, admin_out)
    _log_config_diff("cameras", cameras_cfg, cameras_out)
    _log_config_diff("timelapse", timelapse_cfg, timelapse_out)

    if errors:
        # Be strict: better fail fast with actionable messages
        msg = "Invalid configuration:\n" + "\n".join(f" - {e}" for e in errors)
        logger.error(msg)
        raise ConfigError(msg)

    return http_out, cameras_out, global_out, admin_out, timelapse_out
