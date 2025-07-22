import unittest
from unittest import mock

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gopro


class TestGoProFunctions(unittest.TestCase):
    """Test suite for GoPro camera functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.ip_address = "10.5.5.9"
        self.timeout = 5
        self.test_media_response = {
            "media": [
                {
                    "directory": "100GOPRO",
                    "files": [
                        {
                            "filename": "GOPR0001.JPG"
                        }
                    ]
                }
            ]
        }

    @mock.patch('gopro.requests.get')
    def test_set_ui_controller_success(self, mock_get):
        """Test successful UI controller setting."""
        # Mock response for set_ui_controller endpoint
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        # Test the internal function
        result = gopro._make_gopro_request("/gopro/camera/control/set_ui_controller?p=2")
        
        self.assertEqual(result.status_code, 200)
        mock_get.assert_called_once()

    @mock.patch('gopro.requests.get')
    def test_camera_setting_success(self, mock_get):
        """Test successful camera setting change."""
        # Mock response for camera setting endpoint
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = '{"option": 0}'
        mock_get.return_value = mock_response

        # Test the internal function
        result = gopro._make_gopro_request(
            "/gopro/camera/setting?option=1&setting=88",
            expected_response_text='{"option": 0}'
        )
        
        self.assertEqual(result.status_code, 200)
        mock_get.assert_called_once()

    @mock.patch('gopro.requests.get')
    def test_camera_setting_failure(self, mock_get):
        """Test camera setting failure response."""
        # Mock failure response for camera setting endpoint
        mock_response = mock.Mock()
        mock_response.status_code = 403
        mock_response.text = '''{
  "error": 1,
  "option_id": 0,
  "setting_id": 0,
  "supported_options": [
    {
      "display_name": "string",
      "id": 0
    }
  ]
}'''
        mock_get.return_value = mock_response

        # Test that RuntimeError is raised for unexpected status code
        with self.assertRaises(RuntimeError) as context:
            gopro._make_gopro_request("/gopro/camera/setting?option=1&setting=88")
        
        self.assertIn("Expected response code 200 but got 403", str(context.exception))
        mock_get.assert_called_once()

    @mock.patch('gopro.requests.get')
    def test_shutter_start_success(self, mock_get):
        """Test successful photo capture trigger."""
        # Mock response for shutter start endpoint
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        # Test the internal function
        result = gopro._make_gopro_request("/gopro/camera/shutter/start")
        
        self.assertEqual(result.status_code, 200)
        mock_get.assert_called_once()

    @mock.patch('gopro.requests.get')
    def test_delete_media_file_success(self, mock_get):
        """Test successful media file deletion."""
        # Mock response for delete media file endpoint
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        # Test the internal function
        result = gopro._make_gopro_request("/gopro/media/delete/file?path=100GOPRO/GOPR0001.JPG")
        
        self.assertEqual(result.status_code, 200)
        mock_get.assert_called_once()

    @mock.patch('gopro.requests.get')
    def test_delete_media_file_failure(self, mock_get):
        """Test media file deletion failure (400 error)."""
        # Mock failure response for delete media file endpoint
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        # Test that RuntimeError is raised for 400 status code
        with self.assertRaises(RuntimeError) as context:
            gopro._make_gopro_request("/gopro/media/delete/file?path=100GOPRO/GOPR0001.JPG")
        
        self.assertIn("Expected response code 200 but got 400", str(context.exception))
        mock_get.assert_called_once()

    @mock.patch('gopro.requests.get')
    def test_delete_media_file_busy(self, mock_get):
        """Test media file deletion when camera is busy (503 error)."""
        # Mock busy response for delete media file endpoint
        mock_response = mock.Mock()
        mock_response.status_code = 503
        mock_response.text = "{}\n"
        mock_get.return_value = mock_response

        # Test that RuntimeError is raised for 503 status code
        with self.assertRaises(RuntimeError) as context:
            gopro._make_gopro_request("/gopro/media/delete/file?path=100GOPRO/GOPR0001.JPG")
        
        self.assertIn("Expected response code 200 but got 503", str(context.exception))
        mock_get.assert_called_once()

    @mock.patch('gopro.requests.get')
    def test_get_latest_file_success(self, mock_get):
        """Test successful retrieval of latest file information."""
        # Mock response for media list endpoint
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.test_media_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test the internal function
        latest_dir, latest_file = gopro._get_latest_file(
            self.ip_address, self.timeout, "", "http"
        )
        
        self.assertEqual(latest_dir, "100GOPRO")
        self.assertEqual(latest_file, "GOPR0001.JPG")
        mock_get.assert_called_once_with(
            "http://10.5.5.9/gopro/media/list",
            timeout=5,
            verify=""
        )

    @mock.patch('gopro.requests.get')
    def test_get_latest_file_no_media(self, mock_get):
        """Test retrieval when no media files exist."""
        # Mock response with no media
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"media": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test the internal function
        latest_dir, latest_file = gopro._get_latest_file(
            self.ip_address, self.timeout, "", "http"
        )
        
        self.assertIsNone(latest_dir)
        self.assertIsNone(latest_file)

    @mock.patch('gopro._get_latest_file')
    @mock.patch('gopro.requests.get')
    def test_capture_gopro_photo_success(self, mock_get, mock_get_latest_file):
        """Test successful photo capture workflow."""
        # Create a simple mock that returns the expected bytes for content
        def mock_get_side_effect(url, **kwargs):
            mock_response = mock.Mock()
            mock_response.status_code = 200
            mock_response.text = "{}\n"
            mock_response.raise_for_status.return_value = None
            
            # Special handling for photo download URL
            if "/videos/DCIM/" in url:
                mock_response.content = b"fake_jpeg_data"
            
            return mock_response
        
        mock_get.side_effect = mock_get_side_effect
        
        # Mock _get_latest_file calls
        mock_get_latest_file.side_effect = [
            ("100GOPRO", "GOPR0001.JPG"),  # Before capture
            ("100GOPRO", "GOPR0002.JPG"),  # After capture
        ]
        
        # Test the main function
        result = gopro.capture_gopro_photo()
        
        self.assertEqual(result, b"fake_jpeg_data")
        self.assertEqual(mock_get.call_count, 9)  # All the HTTP calls
        self.assertEqual(mock_get_latest_file.call_count, 2)

    @mock.patch('gopro._get_latest_file')
    @mock.patch('gopro.requests.get')
    def test_capture_gopro_photo_with_output_file(self, mock_get, mock_get_latest_file):
        """Test photo capture with output file saving."""
        import tempfile
        import os
        
        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_filename = temp_file.name
        
        try:
            # Create a simple mock that returns the expected bytes for content
            def mock_get_side_effect(url, **kwargs):
                mock_response = mock.Mock()
                mock_response.status_code = 200
                mock_response.text = "{}\n"
                mock_response.raise_for_status.return_value = None
                
                # Special handling for photo download URL
                if "/videos/DCIM/" in url:
                    mock_response.content = b"test_jpeg_content"
                
                return mock_response
            
            mock_get.side_effect = mock_get_side_effect
            
            # Mock _get_latest_file calls
            mock_get_latest_file.side_effect = [
                ("100GOPRO", "GOPR0001.JPG"),  # Before capture
                ("100GOPRO", "GOPR0002.JPG"),  # After capture
            ]
            
            # Test the main function with output file
            result = gopro.capture_gopro_photo(output_file=temp_filename)
            
            # Verify the result and file was written
            self.assertEqual(result, b"test_jpeg_content")
            
            with open(temp_filename, 'rb') as f:
                file_content = f.read()
            self.assertEqual(file_content, b"test_jpeg_content")
            
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)


if __name__ == '__main__':
    unittest.main()
