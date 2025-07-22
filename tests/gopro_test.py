import unittest
from unittest import mock

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gopro

# TODO: Write tests for all functions in gopro.py with the following mocked responses for each endpoint:

# /gopro/camera/control/set_ui_controller?p=2
# Success: 200
# Content type: application/json
# Response content: { }

# /gopro/camera/setting?option=1&setting=88
# Success: 200
# Content type: application/json
# Response content: { "option": 0 }
#
# Failure: 403
# Content type: application/json
# Response content: {
#   "error": 1,
#   "option_id": 0,
#   "setting_id": 0,
#   "supported_options": [
#     {
#       "display_name": "string",
#       "id": 0
#     }
#   ]
# }

# Capture a Photo
# /gopro/camera/shutter/start
# Success: 200
# Content type: application/json
# Response content: { }

# Delete a Media File
# /gopro/media/delete/file?path={latest_dir_after}/{latest_file_after}
# Failure: 400
# Busy: 503
# Success: 200
# Content type: application/json
# Response content: { }

# Download a Media File

# /videos/DCIM/100GOPRO/{filename}
# Success: 200
# Content type: application/octet-stream

# Get media list
# /gopro/media/list
# Success: 200
# Content type: application/json
# Response content: {
#   "id": "1554375628411872255",
#   "media": [
#     {
#       "d": "100GOPRO",
#       "fs": [
#         {
#           "cre": 1696600109,
#           "glrv": 817767,
#           "ls": -1,
#           "mod": 1696600109,
#           "n": "GOPR0001.JPG",
#           "raw": 1,
#           "s": 2806303
#         }
#       ]
#     }
#   ]
# }

if __name__ == "__main__":
    unittest.main()
