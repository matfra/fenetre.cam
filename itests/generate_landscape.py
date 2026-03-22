import argparse
import datetime as dt
from io import BytesIO
import sys

from astral import Observer, moon
from astral.sun import azimuth as sun_azimuth
from astral.sun import elevation as sun_elevation
from PIL import Image, ImageDraw


def _parse_time(time_file: str) -> dt.datetime:
    with open(time_file, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    parsed = dt.datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _angle_delta_degrees(target: float, camera_azimuth: float) -> float:
    return (target - camera_azimuth + 180.0) % 360.0 - 180.0


def _project_to_image(
    obj_azimuth: float,
    obj_elevation: float,
    camera_azimuth: float,
    fov: float,
    width: int,
    height: int,
):
    az_delta = _angle_delta_degrees(obj_azimuth, camera_azimuth)
    if abs(az_delta) > (fov / 2.0):
        return None

    x = int(round(((az_delta / fov) + 0.5) * (width - 1)))
    horizon_y = (height // 2) - 1
    y = int(round(horizon_y - (obj_elevation / 90.0) * horizon_y))
    y = max(0, min(height - 1, y))
    return x, y


def _blend(c1, c2, t: float):
    clamped_t = max(0.0, min(1.0, t))
    return tuple(int(round(a + (b - a) * clamped_t)) for a, b in zip(c1, c2))


def _scene_palette(sun_elev: float):
    day_sky = (70, 160, 255)
    twilight_sky = (255, 140, 170)
    night_sky = (18, 24, 52)
    day_ground = (60, 160, 70)
    night_ground = (20, 55, 28)

    if sun_elev >= 6.0:
        return day_sky, day_ground
    if sun_elev <= -6.0:
        return night_sky, night_ground

    twilight_mix = 1.0 - min(abs(sun_elev) / 6.0, 1.0)
    if sun_elev >= 0:
        sky = _blend(day_sky, twilight_sky, twilight_mix)
    else:
        sky = _blend(night_sky, twilight_sky, twilight_mix)

    day_mix = max(0.0, min((sun_elev + 6.0) / 12.0, 1.0))
    ground = _blend(night_ground, day_ground, day_mix)
    return sky, ground


def generate_image(
    width: int,
    height: int,
    latitude: float,
    longitude: float,
    camera_azimuth: float,
    fov: float,
    when: dt.datetime,
) -> Image.Image:
    observer = Observer(latitude=latitude, longitude=longitude)
    sun_el = sun_elevation(observer, when)
    sun_az = sun_azimuth(observer, when)
    moon_el = moon.elevation(observer, when)
    moon_az = moon.azimuth(observer, when)

    sky_color, ground_color = _scene_palette(sun_el)

    image = Image.new("RGB", (width, height), sky_color)
    draw = ImageDraw.Draw(image)
    horizon_y = height // 2
    draw.rectangle((0, horizon_y, width, height), fill=ground_color)

    sun_xy = _project_to_image(sun_az, sun_el, camera_azimuth, fov, width, height)
    if sun_xy is not None and sun_el > -2.0:
        draw.ellipse(
            (
                sun_xy[0] - 8,
                sun_xy[1] - 8,
                sun_xy[0] + 8,
                sun_xy[1] + 8,
            ),
            fill=(255, 235, 120),
        )

    moon_xy = _project_to_image(moon_az, moon_el, camera_azimuth, fov, width, height)
    if moon_xy is not None and moon_el > -2.0:
        draw.ellipse(
            (
                moon_xy[0] - 6,
                moon_xy[1] - 6,
                moon_xy[0] + 6,
                moon_xy[1] + 6,
            ),
            fill=(220, 220, 235),
        )

    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--camera-azimuth", type=float, default=80.0)
    parser.add_argument("--fov", type=float, default=120.0)
    parser.add_argument("--time-file", type=str, required=True)
    args = parser.parse_args()

    when = _parse_time(args.time_file)
    image = generate_image(
        width=args.width,
        height=args.height,
        latitude=args.lat,
        longitude=args.lon,
        camera_azimuth=args.camera_azimuth,
        fov=args.fov,
        when=when,
    )

    out = BytesIO()
    image.save(out, format="JPEG", quality=92)
    sys.stdout.buffer.write(out.getvalue())


if __name__ == "__main__":
    main()
