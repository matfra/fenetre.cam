# fenetre

Takes pictures periodically, build timelapses, archive the footage and share it on a self-hosted website. Check it out at https://fenetre.cam or try it with your own cameras!


## Features
- Support taking pictures from:
  - Raspberry Pi camera (tested with v2 and HQ)
  - GoPro Hero 9+ via Bluetooth + WiFi with https://gopro.github.io/OpenGoPro/
  - any local command yielding an image format supported by PIL https://pillow.readthedocs.io/en/latest/reference/features.html#features-module
- Fixed interval or dynamic intervals (sunrise, sunset or fast changing landscape)
- Continuous timelapses (every 20 minutes) + daily high quality ones.
- Daylight browser to navigate years of footage easily. (i.e. https://zero.isitfoggy.com/daylight2.html)
- Produces a fully static website, easy to self-host and put behind Cloudflare.
- Admin interface to help adjust picture settings
- Prometheus exporter to collect metrics for monitoring
- MQTT integration for Home Assistant

## Installation

This is mostly written in Python and it's been tested on Linux but it might run on MacOS and Windows too.


1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/fenetre.cam.git
    cd fenetre.cam
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the package and its dependencies:**
    The project uses `pyproject.toml` to manage dependencies. Installing in editable mode (`-e`) is recommended for development. This command installs the `fenetre` package and the base runtime dependencies from PyPI.
    ```bash
    pip install -e .
    ```

    Optional dependencies are exposed as package extras. Install only the extras you need for the machine you are setting up:

    - `dev`: local development tools, including `pytest` and `black`.
    - `gopro`: Bluetooth and network helpers for GoPro cameras.
    - `picamera2`: Raspberry Pi camera support through `picamera2`.
    - `pyexiv2`: optional EXIF support through `pyexiv2`.

    For a development machine, install the dev extra:
    ```bash
    pip install -e '.[dev]'
    ```

    If you plan to control GoPro cameras over Bluetooth, install the GoPro extra:
    ```bash
    pip install -e '.[gopro]'
    ```

    If you plan to capture from a Raspberry Pi camera with `capture_method: picamera2`, install the Picamera2 extra:
    ```bash
    pip install -e '.[picamera2]'
    ```

    On Raspberry Pi OS, `picamera2` and `libcamera` are often best installed from Debian packages instead of PyPI. In that case, install the OS packages, create the virtual environment with `--system-site-packages`, and keep the Python install as the base package:
    ```bash
    sudo apt-get install python3-picamera2
    python3 -m venv --system-site-packages venv
    pip install -e .
    ```

    Extras can be combined in one install command:
    ```bash
    pip install -e '.[dev,gopro,picamera2,pyexiv2]'
    ```

    Production deployments should usually install only the base package unless a specific camera or workflow requires an extra. The base install does not install Raspberry Pi camera libraries.

## Usage

The application is run using the `fenetre` command, which is made available in your virtual environment after installation.

You must provide the path to a configuration file using the `--config` flag. A sample configuration is provided in `config.example.yaml`.

1.  **Copy the example configuration:**
    ```bash
    cp config.example.yaml config.yaml
    ```

2.  **Edit `config.yaml`** to match your setup (camera URLs, paths, etc.).

3.  **Run the application:**
    ```bash
    fenetre --config=config.yaml
    ```

The application will start, and based on your configuration, it will begin capturing images.

## Running with systemd

For a long-running deployment, create one systemd service per config file. The service should run the `fenetre` executable from the virtual environment, set the repository as the working directory, and pass the deployment-specific config with `--config`.

Example service for `config.fenetre-main.yaml`:

```ini
[Unit]
Description=fenetre.cam main capture service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mathieu
Group=mathieu
WorkingDirectory=/home/mathieu/fenetre-playground/fenetre.cam
ExecStart=/home/mathieu/fenetre-playground/venv/bin/fenetre --config=/home/mathieu/fenetre-playground/fenetre.cam/config.fenetre-main.yaml
Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=45
Environment=TZ=America/Los_Angeles
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Install it as a system service:

```bash
sudo install -m 0644 fenetre-main.service /etc/systemd/system/fenetre-main.service
sudo systemctl daemon-reload
sudo systemctl enable --now fenetre-main.service
```

Check that it started correctly:

```bash
systemctl status fenetre-main.service --no-pager
journalctl -u fenetre-main.service -n 80 --no-pager
```

To run multiple deployments on the same machine, repeat the same pattern with a unique service name and config path for each deployment. For example:

```text
fenetre-sfbay.service     -> config.sfbay.yaml
fenetre-camaredn.service  -> config.camaredn.yaml
fenetre-main.service      -> config.fenetre-main.yaml
```

Make sure each config uses distinct ports and work directories before enabling multiple services.

## Running with Docker on Intel

The included `Dockerfile` builds an Ubuntu 26.04 image with Python, ffmpeg, and Intel VA-API runtime libraries. This is intended for non-Raspberry Pi deployments where Docker is useful and the host has Intel graphics exposed through `/dev/dri`.

Build the image:

```bash
docker build --network=host -t fenetre:intel-vaapi .
```

Run it with the host render devices, config file, and data directories mounted:

```bash
docker run --rm \
  --name fenetre \
  --device /dev/dri:/dev/dri \
  -p 8888:8888 \
  -p 8889:8889 \
  -v "$PWD/config.yaml:/srv/fenetre/config.yaml:ro" \
  -v /srv/fenetre/data:/srv/fenetre/data \
  -v /srv/fenetre/logs:/srv/fenetre/logs \
  fenetre:intel-vaapi
```

Or use compose:

```bash
docker compose up --build
```

Useful checks inside the built image:

```bash
docker run --rm --device /dev/dri:/dev/dri --entrypoint vainfo fenetre:intel-vaapi
docker run --rm --entrypoint ffmpeg fenetre:intel-vaapi -hide_banner -encoders | grep -E 'vaapi|qsv'
```

When using hardware encoding, set `ffmpeg_options` in the relevant timelapse config to an encoder available on the host, such as `h264_vaapi`, `hevc_vaapi`, or a supported `*_qsv` encoder. The container provides the userspace libraries, but the host kernel driver and `/dev/dri` devices still determine what actually works.

Raspberry Pi camera deployments are better served by the systemd approach above because `picamera2`, `libcamera`, and device permissions are closely tied to Raspberry Pi OS.

## Recommended video encoding options

Timelapse encoding is controlled per deployment in `config.yaml` under `timelapse.daily_timelapse.ffmpeg_options` and `timelapse.frequent_timelapse.ffmpeg_options`.

The frequent timelapse usually benefits most from hardware encoding because it runs repeatedly and is normally viewed as HLS. The daily timelapse can use slower CPU encoding if quality or compression matters more than encode time.

Good default CPU options:

```yaml
timelapse:
  frequent_timelapse:
    ffmpeg_2pass: false
    ffmpeg_options: -c:v libx264 -preset veryfast -crf 23 -movflags +faststart
    file_extension: mp4
    output_format: hls
```

Recommended Intel VAAPI options:

```yaml
timelapse:
  frequent_timelapse:
    ffmpeg_2pass: false
    ffmpeg_options: -vaapi_device /dev/dri/renderD128 -vf format=nv12,hwupload -c:v h264_vaapi -qp 24 -movflags +faststart
    file_extension: mp4
    output_format: hls
```

The service user must be able to open the render device. For a systemd deployment, add a drop-in like this:

```ini
[Service]
SupplementaryGroups=render video
```

Then reload and restart the service:

```bash
sudo systemctl daemon-reload
sudo systemctl restart fenetre.service
```

For Docker deployments, pass the render device through to the container:

```bash
docker run --device /dev/dri:/dev/dri ...
```

or in compose:

```yaml
services:
  fenetre:
    devices:
      - /dev/dri:/dev/dri
```

Useful host checks:

```bash
ffmpeg -hide_banner -encoders | grep -E 'h264_vaapi|hevc_vaapi|h264_qsv|h264_v4l2m2m|libx264'
ls -l /dev/dri
```

Validate VAAPI before enabling it in a production config:

```bash
ffmpeg -hide_banner -loglevel error \
  -f lavfi -i testsrc2=size=640x360:rate=30 \
  -frames:v 30 \
  -vaapi_device /dev/dri/renderD128 \
  -vf format=nv12,hwupload \
  -c:v h264_vaapi -qp 24 \
  -f mp4 -y /tmp/fenetre-vaapi-test.mp4
```

If that command fails with a render-device permission error, fix the service user or container device access. If it fails with a VAAPI device or driver error, use CPU `libx264` until the host graphics driver stack is fixed.

Quick Sync (`h264_qsv`) can be faster on some Intel systems, but it is more sensitive to driver and ffmpeg build details. Prefer VAAPI on Linux unless QSV has been tested on the exact host:

```yaml
ffmpeg_options: -c:v h264_qsv -global_quality 24 -look_ahead 0 -movflags +faststart
```

Raspberry Pi deployments can use the V4L2 mem2mem encoder when available:

```yaml
ffmpeg_options: -c:v h264_v4l2m2m -b:v 5M
```

For high-quality daily archives, VP9 CPU encoding is still reasonable when encode time is acceptable:

```yaml
timelapse:
  daily_timelapse:
    ffmpeg_2pass: true
    ffmpeg_options: -c:v libvpx-vp9 -b:v 7M
    file_extension: webm
```

### GoPro

On the first run:
- Put the GoPro in Pairing mode (Menu connections wireless Quic)
- Open bluetoothctl and locate the Mac address of the GoPro (use `scan le` if it's not already showing) then type `trust <MAC_ADDR>` and `pair <MAC_ADDR>`. You can then exit bluetoothctl with `quit`. Remeber to `scan off` if you had to turn ont he scan.
- In the app logs, you should see the Wi-Fi SSID and the password to connect to the GoPro. You may want to configure your system (netplan, wpa_supplicant ...) to autoconnect to the GoPro.

**By default, the admin server runs on `http://0.0.0.0:8889`.**
