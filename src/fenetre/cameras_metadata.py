import hashlib
import json
import logging
import math
import os
from typing import Dict, Any


logger = logging.getLogger(__name__)


def _hash_to_unit_interval(value: bytes) -> float:
    return int.from_bytes(value, "big") / float(1 << (8 * len(value)))


def _meters_to_degree_offsets(lat: float, north_m: float, east_m: float) -> Any:
    meters_per_degree_lat = 111_320.0
    lat_rad = math.radians(lat)
    cos_lat = max(math.cos(lat_rad), 1e-6)
    meters_per_degree_lon = 111_320.0 * cos_lat
    return north_m / meters_per_degree_lat, east_m / meters_per_degree_lon


def _apply_privacy_jitter(
    camera_name: str, lat: float, lon: float, jitter_m: float
) -> Any:
    if jitter_m <= 0:
        return lat, lon

    digest = hashlib.sha256(f"{camera_name}:{lat}:{lon}".encode("utf-8")).digest()
    angle = _hash_to_unit_interval(digest[:8]) * 2 * math.pi
    distance = _hash_to_unit_interval(digest[8:16]) * jitter_m
    north_m = math.sin(angle) * distance
    east_m = math.cos(angle) * distance
    delta_lat, delta_lon = _meters_to_degree_offsets(lat, north_m, east_m)
    return lat + delta_lat, lon + delta_lon


def _load_existing_cameras(json_filepath: str) -> list:
    if not os.path.exists(json_filepath):
        return []

    try:
        with open(json_filepath, "r") as json_file:
            existing = json.load(json_file)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "Could not parse %s or it has an invalid format. It will be overwritten. Error: %s",
            json_filepath,
            exc,
        )
        return []

    if isinstance(existing, list):
        logger.warning(
            "Old format detected for %s. It will be updated to the new format.",
            json_filepath,
        )
        return existing
    if isinstance(existing, dict):
        return existing.get("cameras", [])

    logger.warning("Unrecognized format for %s. It will be overwritten.", json_filepath)
    return []


def build_cameras_metadata(
    cameras_configs: Dict[str, Dict[str, Any]],
    global_config: Dict[str, Any],
    timelapse_config: Dict[str, Any],
    json_filepath: str,
) -> Dict[str, Any]:
    updated_cameras_metadata = {"cameras": [], "global": {}}
    ui_public = dict((global_config or {}).get("ui", {}))
    default_privacy_radius = ui_public.get("map_privacy_radius_m") or 0.0
    default_privacy_jitter = ui_public.get("map_privacy_jitter_m")

    old_camera_list = _load_existing_cameras(json_filepath)
    for camera_metadata in old_camera_list:
        if camera_metadata.get("title") not in cameras_configs:
            logger.warning(
                "Camera %s is not configured anymore. Delete it from %s manually if you want to.",
                camera_metadata.get("title"),
                json_filepath,
            )
            updated_cameras_metadata["cameras"].append(camera_metadata)

    for cam, cam_conf in cameras_configs.items():
        metadata = {
            "title": cam,
            "url": f"list.html?camera={cam}",
            "fullscreen_url": f"fullscreen.html?camera={cam}",
        }

        if cam_conf.get("source") == "external_website":
            metadata["source"] = "external_website"
            metadata["url"] = cam_conf.get("url")
            metadata["thumbnail_url"] = cam_conf.get("thumbnail_url")
        else:
            metadata["original_url"] = cam_conf.get("url") or cam_conf.get(
                "local_command"
            )
            metadata["dynamic_metadata"] = os.path.join("photos", cam, "metadata.json")
            metadata["image"] = os.path.join("photos", cam, "latest.jpg")

        metadata["original_url"] = cam_conf.get("url") or cam_conf.get("local_command")
        metadata["description"] = cam_conf.get("description", "")
        metadata["snap_interval_s"] = cam_conf.get("snap_interval_s") or "dynamic"
        metadata["dynamic_metadata"] = os.path.join("photos", cam, "metadata.json")
        metadata["image"] = os.path.join("photos", cam, "latest.jpg")

        lat = cam_conf.get("lat")
        lon = cam_conf.get("lon")
        radius_m = cam_conf.get("map_privacy_radius_m")
        if radius_m is None:
            radius_m = default_privacy_radius
        radius_m = radius_m or 0.0
        jitter_m = cam_conf.get("map_privacy_jitter_m")
        if jitter_m is None:
            jitter_m = default_privacy_jitter
        if jitter_m is None:
            jitter_m = radius_m
        if radius_m > 0 and lat is not None and lon is not None:
            jitter_m = min(jitter_m, radius_m)
            obfuscated_lat, obfuscated_lon = _apply_privacy_jitter(
                cam, lat, lon, jitter_m
            )
            metadata["lat"] = obfuscated_lat
            metadata["lon"] = obfuscated_lon
        else:
            metadata["lat"] = lat
            metadata["lon"] = lon
        metadata["map_radius_m"] = radius_m

        updated_cameras_metadata["cameras"].append(metadata)

    timelapse_cfg = timelapse_config or {}
    daily_cfg = timelapse_cfg.get("daily_timelapse", {}) or {}
    freq_cfg = timelapse_cfg.get("frequent_timelapse", {}) or {}

    updated_cameras_metadata["global"] = {
        "timelapse_file_extension": daily_cfg.get("file_extension", "webm"),
        "frequent_timelapse_file_extension": freq_cfg.get("file_extension", "mp4"),
        "deployment_name": (global_config or {}).get("deployment_name"),
        "ui": ui_public,
    }

    return updated_cameras_metadata


def write_cameras_metadata(
    cameras_configs: Dict[str, Dict[str, Any]],
    global_config: Dict[str, Any],
    timelapse_config: Dict[str, Any],
    json_filepath: str,
) -> Dict[str, Any]:
    updated_cameras_metadata = build_cameras_metadata(
        cameras_configs,
        global_config,
        timelapse_config,
        json_filepath,
    )

    with open(json_filepath, "w") as json_file:
        json.dump(updated_cameras_metadata, json_file, indent=4)

    return updated_cameras_metadata
