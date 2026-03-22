import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytz
from PIL import Image, ImageStat
from prometheus_client import REGISTRY

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.fenetre.config import config_load
from src.fenetre.fenetre import exit_event, shutdown_application
from src.fenetre import fenetre as fenetre_module


class _FrozenDateTime(datetime):
    current = datetime(2024, 1, 31, 0, 0, tzinfo=pytz.UTC)

    @classmethod
    def now(cls, tz=None):
        value = cls.current
        if tz is None:
            return value.replace(tzinfo=None)
        return value.astimezone(tz)


class LocalCommandLandscapeIntegrationTest(unittest.TestCase):
    def setUp(self):
        collectors = list(REGISTRY._collector_to_names.keys())
        for collector in collectors:
            REGISTRY.unregister(collector)

        itests_dir = Path(__file__).resolve().parent
        self.temp_dir = tempfile.TemporaryDirectory(dir=itests_dir)
        self.runtime_dir = Path(self.temp_dir.name)
        self.work_dir = self.runtime_dir / "work"
        self.time_file = self.runtime_dir / "virtual_time.txt"
        self.config_path = self.runtime_dir / "config.yaml"
        _FrozenDateTime.current = datetime(2024, 1, 31, 0, 0, tzinfo=pytz.UTC)
        self.time_file.write_text(_FrozenDateTime.current.isoformat(), encoding="utf-8")

        script_path = Path(__file__).resolve().parent / "generate_landscape.py"
        python_path = Path(__file__).resolve().parent.parent / "venv" / "bin" / "python"
        local_command = (
            f"{python_path} {script_path} --width 320 --height 180 --lat 48.8566 --lon 2.3522 "
            f"--camera-azimuth 80 --fov 120 --time-file {self.time_file}"
        )

        template_path = (
            Path(__file__).resolve().parent / "config.integration.local_command.yaml"
        )
        template = template_path.read_text(encoding="utf-8")
        config_content = template.replace("__WORK_DIR__", str(self.work_dir)).replace(
            "__LOCAL_COMMAND__", local_command
        )
        self.config_path.write_text(config_content, encoding="utf-8")

        fenetre_module.server_config = {}
        fenetre_module.cameras_config = {}
        fenetre_module.global_config = {}
        fenetre_module.sleep_intervals = {}
        fenetre_module.active_camera_threads = {}
        fenetre_module.daylight_q = []
        fenetre_module.exit_event.clear()

    def tearDown(self):
        shutdown_application()
        self.temp_dir.cleanup()

    def test_25_hour_capture_crosses_day_and_month(self):
        _, cameras_config, global_config, _, _ = config_load(str(self.config_path))
        fenetre_module.global_config = global_config

        camera_name = "fake_landscape"
        camera_config = cameras_config[camera_name]

        expected_frame_count = 26
        written_frames = {"count": 0}
        original_write = fenetre_module.write_pic_to_disk

        def counting_write(pic, pic_path, optimize=False, exif_data=b""):
            original_write(pic, pic_path, optimize, exif_data)
            written_frames["count"] += 1
            if written_frames["count"] >= expected_frame_count:
                fenetre_module.exit_event.set()

        def fast_sleep(duration, should_exit):
            if should_exit.is_set():
                return
            _FrozenDateTime.current += timedelta(seconds=duration)
            self.time_file.write_text(
                _FrozenDateTime.current.isoformat(), encoding="utf-8"
            )

        with (
            mock.patch.object(fenetre_module, "datetime", _FrozenDateTime),
            mock.patch.object(
                fenetre_module, "interruptible_sleep", side_effect=fast_sleep
            ),
            mock.patch.object(
                fenetre_module, "write_pic_to_disk", side_effect=counting_write
            ),
        ):
            snap_thread = threading.Thread(
                target=fenetre_module.snap,
                args=[camera_name, camera_config],
                daemon=True,
            )
            snap_thread.start()
            snap_thread.join(timeout=15)

        self.assertFalse(snap_thread.is_alive())

        jan_dir = self.work_dir / "photos" / camera_name / "2024-01-31"
        feb_dir = self.work_dir / "photos" / camera_name / "2024-02-01"
        self.assertTrue(jan_dir.exists())
        self.assertTrue(feb_dir.exists())

        jan_frames = sorted(jan_dir.glob("*.jpg"))
        feb_frames = sorted(feb_dir.glob("*.jpg"))
        self.assertEqual(len(jan_frames), 24)
        self.assertEqual(len(feb_frames), 2)

        noon = jan_dir / "2024-01-31T12-00-00UTC.jpg"
        midnight = jan_dir / "2024-01-31T00-00-00UTC.jpg"
        self.assertTrue(noon.exists())
        self.assertTrue(midnight.exists())

        noon_brightness = ImageStat.Stat(Image.open(noon).convert("L")).mean[0]
        midnight_brightness = ImageStat.Stat(Image.open(midnight).convert("L")).mean[0]
        self.assertGreater(noon_brightness, midnight_brightness)


if __name__ == "__main__":
    unittest.main()
