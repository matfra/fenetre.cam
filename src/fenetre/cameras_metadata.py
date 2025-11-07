import json
import logging
import os
from typing import Dict, Any


logger = logging.getLogger(__name__)


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
        metadata["lat"] = cam_conf.get("lat")
        metadata["lon"] = cam_conf.get("lon")

        updated_cameras_metadata["cameras"].append(metadata)

    timelapse_cfg = timelapse_config or {}
    daily_cfg = timelapse_cfg.get("daily_timelapse", {}) or {}
    freq_cfg = timelapse_cfg.get("frequent_timelapse", {}) or {}
    ui_public = dict((global_config or {}).get("ui", {}))

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
