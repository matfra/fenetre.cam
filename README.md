# fenetre

Takes pictures periodically ( Raspberry Pi camera, GoPro, local command or any URL), make timelapse and publish them on a self-hosted website. Try it with you own cameras! Example: https://fenetre.cam


This is the inspired by https://github.com/matfra/isitfoggy.today and https://github.com/matfra/camaredn

This is mostly written in Python and meant to run on Linux in a virtualenv or in docker.

Currently supported picture sources:
- any local command yielding an image format supported by PIL https://pillow.readthedocs.io/en/latest/reference/features.html#features-module
- GoPro Hero 9+ via Bluetooth + WiFi with https://gopro.github.io/OpenGoPro/
- Raspberry Pi camera (tested with v2 and HQ)

## TODO:

## How to run?
If you have a GoPro, you will need to run
`git submodule update --init --recursive`


### UI:
- Each camera should have a main visualization page
- If cameras don't have coordinates (lat and lon), don't display the map. Display only the right panel

### Utility
- Enforce the disk usage limits
- Add an http listener for a prometheus exporter
- Create counters for the number of pictures taken since start for each camera
- Create counters for the size of each camera directory

### Picture capture:
- Implement native libcamera python functions instead of relying on libcamera-still
- Add a preprocessing stage based on the previous picture to customize settings for the next picture
- Add a postprocessing stage with basic features to crop, resize, correct AWB, etc.
- Add support for time of day (day/sunset/sunrise/night) for different frequency and settings/profiles

### GoPro
- Add the ability to enable Wi-Fi AP on a GoPro using Bluetooth
- Fix unittests with the correct paths
- Create a custom photo profile
- Use the Python SDK https://gopro.github.io/OpenGoPro/python_sdk/api.html