# fenetre

Takes pictures periodically, build timelapses, archive the footage and share it on a self-hosted website. Check it out at https://fenetre.cam or try it with your own cameras!


## Features
- Support taking pictures from:
  - Raspberry Pi camera, GoPro Hero 9+, local command or any URL)
  - GoPro Hero 9+ via Bluetooth + WiFi with https://gopro.github.io/OpenGoPro/
  - Raspberry Pi camera (tested with v2 and HQ)
  - any local command yielding an image format supported by PIL https://pillow.readthedocs.io/en/latest/reference/features.html#features-module
- Fixed interval or dynamic intervals (sunrise, sunset or fast changing landscape)
- Continuous timelapses (every 20 minutes) + daily high quality ones.
- Daylight browser to browser years of footage easily.
- Produces a fully static website, easy to self-host and put behind Cloudflare.
- Janky admin interface to help adjust picture settings
- Premetheus exporter to collect metrics for monitoring

## Installation

This is mostly written in Python and it's been tested on Linux but it could run on MacOS and Windows too.


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
    The project uses `pyproject.toml` to manage dependencies. Installing in editable mode (`-e`) is recommended for development. This command will install the `fenetre` package and all required libraries from PyPI.
    ```bash
    pip install -e .
    ```


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

### GoPro

On the first run:
- Put the GoPro in Pairing mode (Menu connections wireless Quic)
- Open bluetoothctl and locate the Mac address of the GoPro (use `scan le` if it's not already showing) then type `trust <MAC_ADDR>` and `pair <MAC_ADDR>`. You can then exit bluetoothctl with `quit`. Remeber to `scan off` if you had to turn ont he scan.
- In the app logs, you should see the Wi-Fi SSID and the password to connect to the GoPro. You may want to configure your system (netplan, wpa_supplicant ...) to autoconnect to the GoPro.

**By default, the admin server runs on `http://0.0.0.0:8889`.**
