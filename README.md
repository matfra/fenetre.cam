# fenetre

Takes pictures periodically ( Raspberry Pi camera, GoPro or any URL ), make timelapse and publish them on a self-hosted website. Try it with you own cameras! Example: https://fenetre.cam


This is the inspired by https://github.com/matfra/isitfoggy.today and https://github.com/matfra/camaredn

This is mostly written in Python, runs best on Linux, in a virtualenv or in docker.

Currently supported picture sources:
- any local command yielding an image format supported by PIL https://pillow.readthedocs.io/en/latest/reference/features.html#features-module
- GoPro Hero 9+ via Bluetooth + WiFi with https://gopro.github.io/OpenGoPro/
- Raspberry Pi camera (tested with v2 and HQ)

## Development Setup

The test suite requires Python >=3.11. Install all dependencies using `pip install -r requirements.txt` before running tests.

## TODO:

### UI:
- Each camera should have a main visualization page

### Utility
- Enforce the disk usage limits

### Picture capture:
- Implement native libcamera python functions instead of relying on libcamera-still
- Add a preprocessing stage based on the previous picture to customize settings for the next picture
- Add a postprocessing stage with basic features to crop, resize, correct AWB, etc.
- Add support for time of day (day/sunset/sunrise/night) for different frequency and settings/profiles

### GoPro
- Add the ability to enable Wi-Fi AP on a GoPro using Bluetooth
- Fix unittests with the correct paths
- Create a custom photo profile