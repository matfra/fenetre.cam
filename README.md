# CamAREDN

Saves pictures of HTTP cameras in a structured directory, make daily timelapses and runs a web server. This is inspired by https://github.com/matfra/isitfoggy.today


## Capturing from a GoPro camera
The `gopro.py` module provides a helper function `capture_gopro_photo` to trigger a GoPro over WiFi and download the photo using the [OpenGoPro HTTP API](https://gopro.github.io/OpenGoPro/http). Example usage:
```python
from gopro import capture_gopro_photo
photo_bytes = capture_gopro_photo(output_file="latest.jpg")
```
This defaults to the standard GoPro WiFi address `10.5.5.9`.
When using a GoPro as a camera source, set the `gopro_ip` key in the camera configuration.
If the camera operates in COHN mode (where it joins your WiFi network and serves over HTTPS), provide the root TLS certificate in a `gopro_root_ca` field so requests can be verified.

## TODO
- Monthly and yearly daylight view
- Map browser to pick the cameras
