import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from PIL import Image
from io import BytesIO
import sys
from types import SimpleNamespace

from fenetre.fenetre import (
    cleanup_frequent_timelapse_artifacts,
    get_pic_from_url,
    get_ssim_for_area,
    run_camera_unavailable_command,
)
from fenetre.picamera import Picamera2Capture


class TestFenetre(unittest.TestCase):
    @patch("fenetre.fenetre.subprocess.run")
    def test_run_camera_unavailable_command(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = ""
        mock_subprocess_run.return_value.stderr = ""

        run_camera_unavailable_command(
            "cam1",
            {
                "unavailable_command": "printf hello >> /tmp/cam1-unavailable",
                "unavailable_command_timeout_s": 7,
            },
            "thread stopped",
        )

        args, kwargs = mock_subprocess_run.call_args
        self.assertEqual(args[0], "printf hello >> /tmp/cam1-unavailable")
        self.assertTrue(kwargs["shell"])
        self.assertEqual(kwargs["timeout"], 7)
        self.assertEqual(kwargs["env"]["FENETRE_CAMERA_NAME"], "cam1")
        self.assertEqual(kwargs["env"]["FENETRE_UNAVAILABLE_REASON"], "thread stopped")
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])

    @patch("fenetre.fenetre.subprocess.run")
    def test_run_camera_unavailable_command_noop_without_config(
        self, mock_subprocess_run
    ):
        run_camera_unavailable_command("cam1", {}, "thread stopped")

        mock_subprocess_run.assert_not_called()

    @patch("fenetre.fenetre.requests.get")
    @patch("fenetre.fenetre.time.time", return_value=1234567890)
    def test_get_pic_from_url_cache_bust(self, mock_time, mock_requests_get):
        # Mock the response from requests.get
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Create a dummy image for the content
        dummy_image = Image.new("RGB", (100, 100), color="red")
        byte_arr = BytesIO()
        dummy_image.save(byte_arr, format="JPEG")
        mock_response.content = byte_arr.getvalue()
        mock_requests_get.return_value = mock_response

        # Test case 1: cache_bust enabled, no existing query params
        camera_config_1 = {"cache_bust": True}
        url_1 = "http://example.com/image.jpg"
        get_pic_from_url(url_1, 10, camera_config=camera_config_1, global_config={})
        mock_requests_get.assert_called_with(
            "http://example.com/image.jpg?_=1234567890",
            timeout=10,
            headers={"Accept": "image/*,*"},
        )

        # Test case 2: cache_bust enabled, with existing query params
        camera_config_2 = {"cache_bust": True}
        url_2 = "http://example.com/image.jpg?param=value"
        get_pic_from_url(url_2, 10, camera_config=camera_config_2, global_config={})
        mock_requests_get.assert_called_with(
            "http://example.com/image.jpg?param=value&_=1234567890",
            timeout=10,
            headers={"Accept": "image/*,*"},
        )

        # Test case 3: cache_bust disabled
        camera_config_3 = {"cache_bust": False}
        url_3 = "http://example.com/image.jpg"
        get_pic_from_url(url_3, 10, camera_config=camera_config_3, global_config={})
        mock_requests_get.assert_called_with(
            "http://example.com/image.jpg", timeout=10, headers={"Accept": "image/*,*"}
        )

        # Test case 4: cache_bust option not present
        camera_config_4 = {}
        url_4 = "http://example.com/image.jpg"
        get_pic_from_url(url_4, 10, camera_config=camera_config_4, global_config={})
        mock_requests_get.assert_called_with(
            "http://example.com/image.jpg", timeout=10, headers={"Accept": "image/*,*"}
        )

    def test_picamera2_capture_applies_base_and_mode_controls(self):
        instances = []

        class FakePicamera2:
            @staticmethod
            def load_tuning_file(path):
                return {"tuning_file": path}

            def __init__(self, tuning=None):
                self.tuning = tuning
                self.configured = None
                self.controls = []
                self.started = False
                self.stopped = False
                instances.append(self)

            def create_still_configuration(self, **kwargs):
                return {"still": kwargs}

            def configure(self, config, tuning=None):
                self.configured = (config, tuning)

            def start(self):
                self.started = True

            def stop(self):
                self.stopped = True

            def set_controls(self, controls):
                self.controls.append(controls)

            def capture_file(self, output, format=None):
                img = Image.new("RGB", (8, 6), color="red")
                img.save(output, format="JPEG")

        fake_controls = SimpleNamespace(
            draft=SimpleNamespace(
                NoiseReductionModeEnum=SimpleNamespace(HighQuality=42)
            )
        )

        old_picamera2 = sys.modules.get("picamera2")
        old_libcamera = sys.modules.get("libcamera")
        sys.modules["picamera2"] = SimpleNamespace(Picamera2=FakePicamera2)
        sys.modules["libcamera"] = SimpleNamespace(controls=fake_controls)
        try:
            capture = Picamera2Capture(
                {
                    "tuning_file": "/tmp/tuning.json",
                    "startup_warmup_s": 0,
                    "control_warmup_s": 0,
                    "main_size": [4056, 3040],
                    "exposure_value": 1.5,
                    "denoise_mode": "HighQuality",
                    "night_settings": {
                        "ae_enable": False,
                        "exposure_time": 1000000,
                        "analogue_gain": 2.0,
                    },
                }
            )
            pic = capture.capture("night")
            capture.close()
        finally:
            if old_picamera2 is None:
                sys.modules.pop("picamera2", None)
            else:
                sys.modules["picamera2"] = old_picamera2
            if old_libcamera is None:
                sys.modules.pop("libcamera", None)
            else:
                sys.modules["libcamera"] = old_libcamera

        self.assertEqual(pic.size, (8, 6))
        fake = instances[0]
        self.assertTrue(fake.started)
        self.assertTrue(fake.stopped)
        self.assertEqual(
            fake.configured[0],
            {"still": {"main": {"size": (4056, 3040)}}},
        )
        self.assertEqual(
            fake.controls[-1],
            {
                "ExposureValue": 1.5,
                "NoiseReductionMode": 42,
                "AeEnable": False,
                "ExposureTime": 1000000,
                "AnalogueGain": 2.0,
            },
        )

    def test_picamera2_exposure_control_updates_next_day_capture(self):
        instances = []

        class FakePicamera2:
            def __init__(self):
                self.controls = []
                instances.append(self)

            def create_still_configuration(self, **kwargs):
                return {}

            def configure(self, config, tuning=None):
                pass

            def start(self):
                pass

            def stop(self):
                pass

            def close(self):
                pass

            def set_controls(self, controls):
                self.controls.append(controls)

            def capture_file(self, output, format=None):
                img = Image.new("RGB", (8, 6), color="white")
                img.save(output, format="JPEG")

            def capture_metadata(self):
                return {"ExposureTime": 100000, "AnalogueGain": 8.0}

        fake_controls = SimpleNamespace(
            draft=SimpleNamespace(
                NoiseReductionModeEnum=SimpleNamespace(HighQuality=42)
            )
        )

        old_picamera2 = sys.modules.get("picamera2")
        old_libcamera = sys.modules.get("libcamera")
        sys.modules["picamera2"] = SimpleNamespace(Picamera2=FakePicamera2)
        sys.modules["libcamera"] = SimpleNamespace(controls=fake_controls)
        try:
            capture = Picamera2Capture(
                {
                    "startup_warmup_s": 0,
                    "control_warmup_s": 0,
                    "exposure_control": {
                        "enabled": True,
                        "target_luma": 0.45,
                        "min_adjustment_factor": 0.8,
                        "max_adjustment_factor": 1.25,
                        "day": {
                            "enabled": True,
                            "min_exposure_time": 100,
                            "max_exposure_time": 20000,
                            "min_analogue_gain": 1.0,
                            "max_analogue_gain": 4.0,
                            "start_exposure_time": 1000,
                            "start_analogue_gain": 1.0,
                        },
                    },
                }
            )
            capture.capture("day")
            capture.capture("day")
            capture.close()
        finally:
            if old_picamera2 is None:
                sys.modules.pop("picamera2", None)
            else:
                sys.modules["picamera2"] = old_picamera2
            if old_libcamera is None:
                sys.modules.pop("libcamera", None)
            else:
                sys.modules["libcamera"] = old_libcamera

        self.assertEqual(
            instances[0].controls[-1],
            {"AeEnable": False, "ExposureTime": 800, "AnalogueGain": 1.0},
        )
        self.assertEqual(
            capture.get_exposure_control_state()["modes"]["day"],
            {"ae_enable": False, "exposure_time": 640, "analogue_gain": 1.0},
        )

    def test_picamera2_exposure_control_restores_initial_state(self):
        instances = []

        class FakePicamera2:
            def __init__(self):
                self.controls = []
                instances.append(self)

            def create_still_configuration(self, **kwargs):
                return {}

            def configure(self, config, tuning=None):
                pass

            def start(self):
                pass

            def stop(self):
                pass

            def close(self):
                pass

            def set_controls(self, controls):
                self.controls.append(controls)

            def capture_file(self, output, format=None):
                img = Image.new("RGB", (8, 6), color="white")
                img.save(output, format="JPEG")

            def capture_metadata(self):
                return {"ExposureTime": 100000, "AnalogueGain": 8.0}

        fake_controls = SimpleNamespace(
            draft=SimpleNamespace(
                NoiseReductionModeEnum=SimpleNamespace(HighQuality=42)
            )
        )

        old_picamera2 = sys.modules.get("picamera2")
        old_libcamera = sys.modules.get("libcamera")
        sys.modules["picamera2"] = SimpleNamespace(Picamera2=FakePicamera2)
        sys.modules["libcamera"] = SimpleNamespace(controls=fake_controls)
        try:
            capture = Picamera2Capture(
                {
                    "startup_warmup_s": 0,
                    "control_warmup_s": 0,
                    "exposure_control": {
                        "enabled": True,
                        "target_luma": 0.45,
                        "min_adjustment_factor": 0.8,
                        "max_adjustment_factor": 1.25,
                        "day": {"enabled": True},
                    },
                },
                initial_exposure_state={
                    "enabled": True,
                    "modes": {
                        "day": {
                            "ae_enable": False,
                            "exposure_time": 500,
                            "analogue_gain": 2.0,
                        }
                    },
                },
            )
            capture.capture("day")
            capture.close()
        finally:
            if old_picamera2 is None:
                sys.modules.pop("picamera2", None)
            else:
                sys.modules["picamera2"] = old_picamera2
            if old_libcamera is None:
                sys.modules.pop("libcamera", None)
            else:
                sys.modules["libcamera"] = old_libcamera

        self.assertEqual(
            instances[0].controls[0],
            {"AeEnable": False, "ExposureTime": 500, "AnalogueGain": 2.0},
        )

    def test_picamera2_night_exposure_control_locks_analogue_gain(self):
        class FakePicamera2:
            def create_still_configuration(self, **kwargs):
                return {}

            def configure(self, config, tuning=None):
                pass

            def start(self):
                pass

            def stop(self):
                pass

            def close(self):
                pass

            def set_controls(self, controls):
                pass

            def capture_file(self, output, format=None):
                img = Image.new("RGB", (8, 6), color="black")
                img.save(output, format="JPEG")

            def capture_metadata(self):
                return {"ExposureTime": 100000, "AnalogueGain": 8.0}

        fake_controls = SimpleNamespace(
            draft=SimpleNamespace(
                NoiseReductionModeEnum=SimpleNamespace(HighQuality=42)
            )
        )

        old_picamera2 = sys.modules.get("picamera2")
        old_libcamera = sys.modules.get("libcamera")
        sys.modules["picamera2"] = SimpleNamespace(Picamera2=FakePicamera2)
        sys.modules["libcamera"] = SimpleNamespace(controls=fake_controls)
        try:
            capture = Picamera2Capture(
                {
                    "startup_warmup_s": 0,
                    "control_warmup_s": 0,
                    "exposure_control": {
                        "enabled": True,
                        "max_adjustment_factor": 3.0,
                        "night": {
                            "enabled": True,
                            "min_exposure_time": 1000,
                            "max_exposure_time": 15000000,
                            "min_analogue_gain": 2.0,
                            "max_analogue_gain": 2.0,
                            "start_exposure_time": 1000000,
                            "start_analogue_gain": 2.0,
                        },
                    },
                }
            )
            capture.capture("night")
            capture.close()
        finally:
            if old_picamera2 is None:
                sys.modules.pop("picamera2", None)
            else:
                sys.modules["picamera2"] = old_picamera2
            if old_libcamera is None:
                sys.modules.pop("libcamera", None)
            else:
                sys.modules["libcamera"] = old_libcamera

        self.assertEqual(
            capture.get_exposure_control_state()["modes"]["night"],
            {"ae_enable": False, "exposure_time": 3000000, "analogue_gain": 2.0},
        )

    def test_picamera2_exposure_metering_percentile_tracks_bright_pixels(self):
        image = Image.new("L", (64, 64), color=0)
        for x in range(58, 64):
            for y in range(64):
                image.putpixel((x, y), 255)

        capture = Picamera2Capture.__new__(Picamera2Capture)
        capture.closed = True
        capture.exposure_control = {"metering_area": None, "metering_percentile": 50}
        self.assertEqual(capture._measure_luma(image), 0.0)

        capture.exposure_control["metering_percentile"] = 95
        self.assertEqual(capture._measure_luma(image), 1.0)

    def test_get_ssim_for_area_clamps_crop_to_image_size(self):
        image1 = Image.new("RGB", (1921, 1440), color="black")
        image2 = Image.new("RGB", (1921, 1440), color="black")

        ssim = get_ssim_for_area(image1, image2, "0,0,2560,500")

        self.assertEqual(ssim, 1.0)

    def test_cleanup_frequent_timelapse_artifacts_removes_hls_outputs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            day_dir = os.path.join(tmp_dir, "2026-05-02")
            os.makedirs(day_dir)
            legacy_segment_dir = os.path.join(day_dir, "2026-05-02.segments")
            os.makedirs(legacy_segment_dir)

            hls_paths = [
                os.path.join(day_dir, "2026-05-02.m3u8"),
                os.path.join(day_dir, ".2026-05-02.hls-manifest.json"),
                os.path.join(day_dir, "init.mp4"),
                os.path.join(day_dir, "segment-000000.ts"),
                os.path.join(day_dir, "segment-000002.ts"),
                os.path.join(day_dir, "segment-000003.m4s"),
                os.path.join(legacy_segment_dir, "segment-legacy.ts"),
            ]
            preserved_paths = [
                os.path.join(day_dir, "2026-05-02.webm"),
                os.path.join(day_dir, "2026-05-02T10-00-00PDT.jpg"),
            ]
            for path in hls_paths + preserved_paths:
                with open(path, "w") as f:
                    f.write("test")

            deleted_paths = cleanup_frequent_timelapse_artifacts(
                day_dir,
                {"output_format": "hls", "file_extension": "mp4"},
                {"file_extension": "webm"},
            )

            self.assertFalse(os.path.exists(os.path.join(day_dir, "2026-05-02.m3u8")))
            self.assertFalse(
                os.path.exists(os.path.join(day_dir, ".2026-05-02.hls-manifest.json"))
            )
            self.assertFalse(os.path.exists(os.path.join(day_dir, "segment-000000.ts")))
            self.assertFalse(os.path.exists(os.path.join(day_dir, "segment-000002.ts")))
            self.assertFalse(os.path.exists(os.path.join(day_dir, "segment-000003.m4s")))
            self.assertFalse(os.path.exists(os.path.join(day_dir, "init.mp4")))
            self.assertFalse(os.path.exists(legacy_segment_dir))
            for path in preserved_paths:
                self.assertTrue(os.path.exists(path))
            self.assertEqual(len(deleted_paths), 7)

    def test_cleanup_frequent_timelapse_artifacts_removes_file_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            day_dir = os.path.join(tmp_dir, "2026-05-02")
            os.makedirs(day_dir)
            frequent_path = os.path.join(day_dir, "2026-05-02.mp4")
            daily_path = os.path.join(day_dir, "2026-05-02.webm")
            for path in [frequent_path, daily_path]:
                with open(path, "w") as f:
                    f.write("test")

            deleted_paths = cleanup_frequent_timelapse_artifacts(
                day_dir,
                {"output_format": "file", "file_extension": "mp4"},
                {"file_extension": "webm"},
            )

            self.assertFalse(os.path.exists(frequent_path))
            self.assertTrue(os.path.exists(daily_path))
            self.assertEqual(deleted_paths, [frequent_path])

    def test_cleanup_frequent_timelapse_artifacts_preserves_matching_file_extension(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp_dir:
            day_dir = os.path.join(tmp_dir, "2026-05-02")
            os.makedirs(day_dir)
            shared_path = os.path.join(day_dir, "2026-05-02.mp4")
            with open(shared_path, "w") as f:
                f.write("test")

            deleted_paths = cleanup_frequent_timelapse_artifacts(
                day_dir,
                {"output_format": "file", "file_extension": "mp4"},
                {"file_extension": "mp4"},
            )

            self.assertTrue(os.path.exists(shared_path))
            self.assertEqual(deleted_paths, [])


if __name__ == "__main__":
    unittest.main()
