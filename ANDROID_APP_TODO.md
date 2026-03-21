# Android App MVP Todo

Scope: native Kotlin app running on-device, keep all current features.

- Core runtime orchestration: load config, init global state, start/stop loops, graceful shutdown/reload.
- Camera capture loop: periodic capture, write to `work_dir/photos/<camera>/<YYYY-MM-DD>/YYYY-MM-DDTHH-MM-SS<tz>.jpg`, update `latest.jpg` and `metadata.json`.
- Capture sources: phone camera (primary), optional URL fetch/local command equivalent if kept.
- Adaptive scheduling: SSIM-based dynamic interval, sunrise/sunset fast interval, day/night/astro mode transitions from EXIF (exposure/ISO).
- Post-processing pipeline: EXIF orientation, crop/resize/rotate/AWB, timestamp/text overlays, sun-path overlay.
- Timelapse creation: queue file, frequent timelapse loop, daily timelapse loop, ffmpeg-equivalent encoder with scaling rules.
- Daylight bands: daily 1x1440 band, monthly composite, HTML generation for browser pages.
- Archival loop: scan day dirs, require daylight + timelapse, prune images to 48, mark archived.
- Disk management: per-camera and global size limits, delete oldest day dirs.
- Web server for pictures: static file server rooted at work_dir, optional CORS.
- Admin server: metrics, config GET/PUT, reload trigger, UI sync, capture-for-UI, preview crop, rebuild cameras.json.
- UI assets: static HTML/JS/CSS copying into work_dir and index generation.
- Config parsing/validation: migrate YAML to protobuf schema, use textpb for configs.
- Config migration tooling: converter from existing YAML to textpb, plus schema versioning.
- Metadata generation: `cameras.json` with privacy jitter + UI metadata.
- Observability: metrics (Prometheus equivalent), per-camera logs, optional MQTT state publishing.
