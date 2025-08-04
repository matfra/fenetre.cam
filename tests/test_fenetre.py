import unittest
from unittest.mock import patch, MagicMock
from PIL import Image
from io import BytesIO

from fenetre.config import CameraConfig
from fenetre.fenetre import get_pic_from_url


class TestFenetre(unittest.TestCase):
    @patch('fenetre.fenetre.requests.get')
    @patch('fenetre.fenetre.time.time', return_value=1234567890)
    def test_get_pic_from_url_cache_bust(self, mock_time, mock_requests_get):
        # Mock the response from requests.get
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Create a dummy image for the content
        dummy_image = Image.new('RGB', (100, 100), color = 'red')
        byte_arr = BytesIO()
        dummy_image.save(byte_arr, format='JPEG')
        mock_response.content = byte_arr.getvalue()
        mock_requests_get.return_value = mock_response

        # Test case 1: cache_bust enabled, no existing query params
        camera_config_1 = CameraConfig(cache_bust=True)
        url_1 = "http://example.com/image.jpg"
        get_pic_from_url(url_1, 10, camera_config=camera_config_1, global_config={})
        mock_requests_get.assert_called_with(
            "http://example.com/image.jpg?_=1234567890",
            timeout=10,
            headers={'Accept': 'image/*,*'}
        )

        # Test case 2: cache_bust enabled, with existing query params
        camera_config_2 = CameraConfig(cache_bust=True)
        url_2 = "http://example.com/image.jpg?param=value"
        get_pic_from_url(url_2, 10, camera_config=camera_config_2, global_config={})
        mock_requests_get.assert_called_with(
            "http://example.com/image.jpg?param=value&_=1234567890",
            timeout=10,
            headers={'Accept': 'image/*,*'}
        )

        # Test case 3: cache_bust disabled
        camera_config_3 = CameraConfig(cache_bust=False)
        url_3 = "http://example.com/image.jpg"
        get_pic_from_url(url_3, 10, camera_config=camera_config_3, global_config={})
        mock_requests_get.assert_called_with(
            "http://example.com/image.jpg",
            timeout=10,
            headers={'Accept': 'image/*,*'}
        )

        # Test case 4: cache_bust option not present
        camera_config_4 = CameraConfig()
        url_4 = "http://example.com/image.jpg"
        get_pic_from_url(url_4, 10, camera_config=camera_config_4, global_config={})
        mock_requests_get.assert_called_with(
            "http://example.com/image.jpg",
            timeout=10,
            headers={'Accept': 'image/*,*'}
        )

if __name__ == '__main__':
    unittest.main()
