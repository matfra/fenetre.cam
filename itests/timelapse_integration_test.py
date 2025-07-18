import unittest
import os
import shutil
import tempfile
from PIL import Image
from unittest.mock import patch
import yaml
import json

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from timelapse import create_timelapse
from config import config_load

class TestTimelapseIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = config_load('config.integration.yaml')
        self.image_dir = os.path.join(self.config[2]['work_dir'], "images")
        
        if os.path.exists(self.image_dir):
            shutil.rmtree(self.image_dir)
        os.makedirs(self.image_dir, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()
        if os.path.exists(self.image_dir):
            shutil.rmtree(self.image_dir)

    def _create_dummy_images(self, width, height, count=1):
        for i in range(count):
            img = Image.new('RGB', (width, height), color = 'red')
            img.save(os.path.join(self.image_dir, f"test_{i:04d}.jpg"))

    @patch('timelapse.is_raspberry_pi', return_value=True)
    def test_create_timelapse_pi_wide(self, mock_is_pi):
        self._create_dummy_images(2000, 1000)
        self.assertTrue(create_timelapse(self.image_dir, overwrite=True, tmp_dir=self.config[2]['work_dir']))
        self.assertTrue(os.path.exists(os.path.join(self.image_dir, "images.mp4")))

    @patch('timelapse.is_raspberry_pi', return_value=True)
    def test_create_timelapse_pi_tall(self, mock_is_pi):
        self._create_dummy_images(1000, 2000)
        self.assertTrue(create_timelapse(self.image_dir, overwrite=True, tmp_dir=self.config[2]['work_dir']))
        self.assertTrue(os.path.exists(os.path.join(self.image_dir, "images.mp4")))
        
        # Check that cameras.json was updated
        cameras_json_path = os.path.join(self.config[2]['work_dir'], "cameras.json")
        if os.path.exists(cameras_json_path):
            with open(cameras_json_path, "r") as f:
                data = json.load(f)
                self.assertEqual(data['cameras'][0]['latest_timelapse'], 'photos/images/images.mp4')

    @patch('timelapse.is_raspberry_pi', return_value=False)
    def test_create_timelapse_not_pi_wide_fast(self, mock_is_pi):
        self._create_dummy_images(4000, 2000, count=1300)
        self.assertTrue(create_timelapse(self.image_dir, overwrite=True, tmp_dir=self.config[2]['work_dir']))
        self.assertTrue(os.path.exists(os.path.join(self.image_dir, "images.webm")))

    @patch('timelapse.is_raspberry_pi', return_value=False)
    def test_create_timelapse_not_pi_wide_slow(self, mock_is_pi):
        self._create_dummy_images(4000, 2000)
        self.assertTrue(create_timelapse(self.image_dir, overwrite=True, tmp_dir=self.config[2]['work_dir']))
        self.assertTrue(os.path.exists(os.path.join(self.image_dir, "images.webm")))

    @patch('timelapse.is_raspberry_pi', return_value=False)
    def test_create_timelapse_not_pi_tall(self, mock_is_pi):
        self._create_dummy_images(2000, 4000)
        self.assertTrue(create_timelapse(self.image_dir, overwrite=True, tmp_dir=self.config[2]['work_dir']))
        self.assertTrue(os.path.exists(os.path.join(self.image_dir, "images.webm")))

if __name__ == '__main__':
    unittest.main()
