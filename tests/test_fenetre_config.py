import logging
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from fenetre.config import FenetreConfig, AppConfig

# Configure logging to capture warnings
logging.basicConfig(level=logging.WARNING)


class FenetreConfigTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        # Reset the singleton instance before each test
        if FenetreConfig in FenetreConfig._instances:
            del FenetreConfig._instances[FenetreConfig]

    def tearDown(self):
        self.temp_dir.cleanup()
        if FenetreConfig in FenetreConfig._instances:
            del FenetreConfig._instances[FenetreConfig]

    def _create_temp_config_file(self, data):
        fd, path = tempfile.mkstemp(suffix=".yaml", dir=self.temp_dir.name)
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f)
        return path

    def test_singleton_behavior(self):
        config_path = self._create_temp_config_file({"global": {"title": "value"}})
        config1 = FenetreConfig(config_file=config_path)
        config2 = FenetreConfig()
        self.assertIs(config1, config2)
        self.assertEqual(config1.get_config().global_config.title, "value")

    def test_load_defaults_if_file_missing(self):
        with self.assertLogs('fenetre.config', level='WARNING') as cm:
            config = FenetreConfig(config_file="non_existent_file.yaml")
            self.assertEqual(config.get_config(), AppConfig())
            self.assertEqual(len(cm.output), 1)
            self.assertIn("Config file not found at non_existent_file.yaml, using defaults", cm.output[0])

    def test_load_config_from_file(self):
        test_data = {
            "global": {"title": "My Test Cameras"},
            "cameras": {"cam1": {"url": "http://localhost/cam1"}},
        }
        config_path = self._create_temp_config_file(test_data)
        config = FenetreConfig(config_file=config_path)

        self.assertEqual(config.get_config().global_config.title, "My Test Cameras")
        self.assertEqual(config.get_config().cameras["cam1"].url, "http://localhost/cam1")
        # Check if default values are merged
        self.assertIsNotNone(config.get_config().global_config.work_dir)

    def test_get_specific_configs(self):
        test_data = {
            "global": {"title": "Test"},
            "http_server": {"enabled": True},
            "admin_server": {"enabled": False},
            "timelapse": {"daily_timelapse": {"file_extension": "mov"}},
            "cameras": {"cam1": {"url": "test_url"}},
        }
        config_path = self._create_temp_config_file(test_data)
        config = FenetreConfig(config_file=config_path)

        self.assertEqual(config.get_config().http_server.enabled, True)
        self.assertEqual(config.get_config().admin_server.enabled, False)
        self.assertEqual(config.get_config().timelapse.daily_timelapse.file_extension, "mov")
        self.assertEqual(config.get_config().cameras["cam1"].url, "test_url")
        self.assertNotIn("non_existent_cam", config.get_config().cameras)

    def test_save_and_reload_config(self):
        config_path = self._create_temp_config_file({"global": {"title": "Initial"}})
        config = FenetreConfig(config_file=config_path)
        self.assertEqual(config.get_config().global_config.title, "Initial")

        new_data = {"global": {"title": "Updated"}}
        config.save_config(new_data)

        # The singleton instance should have reloaded the config
        self.assertEqual(config.get_config().global_config.title, "Updated")

        # Verify the file content
        with open(config_path, "r") as f:
            saved_data = yaml.safe_load(f)
        self.assertEqual(saved_data, new_data)


if __name__ == "__main__":
    unittest.main()
