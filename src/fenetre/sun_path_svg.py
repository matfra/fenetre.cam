
import datetime
import math
import pytz
from astral import LocationInfo
from astral.sun import sun, noon, elevation

def create_sun_path_svg(
    date,
    latitude,
    longitude,
    major_bar_width=1,
    minor_bar_width=1,
    major_bar_color="darkgrey",
    minor_bar_color="lightgrey",
    background_color="transparent",
    sun_arc_color="rgba(255, 255, 0, 0.5)",
    timezone="UTC",
):
    """
    Creates an SVG image showing the sun's path for a given date and location.

    Args:
        date: The date for which to calculate the sun's path.
        latitude: The latitude of the location.
        longitude: The longitude of the location.
        major_bar_width: The width of the 6am, 12pm, 6pm bars.
        minor_bar_width: The width of the other hourly bars.
        major_bar_color: The color of the major bars.
        minor_bar_color: The color of the minor bars.
        background_color: The background color of the SVG.
        sun_arc_color: The color of the sun arc.
        timezone: The timezone for the location.

    Returns:
        A string containing the SVG image.
    """
    width = 1000
    height = 50

    location = LocationInfo(latitude=latitude, longitude=longitude)
    tz = pytz.timezone(timezone)

    try:
        s = sun(location.observer, date=date, tzinfo=tz)
        sunrise = s["sunrise"]
        sunset = s["sunset"]
        noon_time = noon(location.observer, date=date, tzinfo=tz)
        max_elevation = elevation(location.observer, noon_time)
    except ValueError:
        # Sun never rises or sets (polar night/day)
        return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="transparent" /></svg>'

    if max_elevation <= 0:
        # Sun is below the horizon all day
        return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="transparent" /></svg>'


    # Convert to seconds from midnight
    sunrise_seconds = sunrise.hour * 3600 + sunrise.minute * 60 + sunrise.second
    sunset_seconds = sunset.hour * 3600 + sunset.minute * 60 + sunset.second

    sunrise_x = (sunrise_seconds / 86400) * width
    sunset_x = (sunset_seconds / 86400) * width

    arc_width = sunset_x - sunrise_x
    rx = arc_width / 2
    
    # Make arc height proportional to the sun's max elevation
    # Max elevation is 90 degrees. Max arc height is height - 10 for margin.
    ry = (max_elevation / 90.0) * (height - 10)

    # The arc should be placed at the bottom of the SVG.
    # The y-coordinate for start and end should be the same.
    y_coord = height - 5

    path_data = f"M {sunrise_x:.2f},{y_coord} A {rx:.2f},{ry} 0 0 1 {sunset_x:.2f},{y_coord}"

    time_bars = []
    hour_width = width / 24
    for hour in range(24):
        x = hour * hour_width
        if hour in [6, 12, 18]:
            time_bars.append(
                f'<line x1="{x:.2f}" y1="0" x2="{x:.2f}" y2="{height}" stroke="{major_bar_color}" stroke-width="{major_bar_width}" />'
            )
        else:
            time_bars.append(
                f'<line x1="{x:.2f}" y1="{height/2}" x2="{x:.2f}" y2="{height}" stroke="{minor_bar_color}" stroke-width="{minor_bar_width}" />'
            )
    time_bars_svg = "\n    ".join(time_bars)

    svg = f"""
<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <rect width="100%" height="100%" fill="{background_color}" />
    <path d="{path_data}" fill="{sun_arc_color}" stroke="{sun_arc_color}" stroke-width="2" />
    {time_bars_svg}
</svg>
"""
    return svg.strip()

def overlay_time_bar(
    svg_content,
    time_to_overlay,
    overlay_rect_width=5,
    overlay_border_width=2,
    overlay_border_color="white",
    overlay_rect_height_ratio=1.0,
):
    """
    Overlays a vertical rectangle on an existing sun path SVG to indicate a specific time.

    Args:
        svg_content: The SVG image string to modify.
        time_to_overlay: A datetime object for the time to be marked.
        overlay_rect_width: The width of the overlay rectangle.
        overlay_border_width: The width of the rectangle's border.
        overlay_border_color: The color of the rectangle's border.
        overlay_rect_height_ratio: The height of the overlay rectangle as a ratio of the total height.

    Returns:
        A string containing the modified SVG image.
    """
    # Assuming width and height are 1000x50, as defined in the creation function
    width = 1000
    height = 50

    time_seconds = (
        time_to_overlay.hour * 3600
        + time_to_overlay.minute * 60
        + time_to_overlay.second
    )
    bar_center_x = (time_seconds / 86400) * width
    rect_x = bar_center_x - (overlay_rect_width / 2)

    rect_pixel_height = height * overlay_rect_height_ratio
    rect_y = (height - rect_pixel_height) / 2

    bar_svg = f'<rect x="{rect_x:.2f}" y="{rect_y:.2f}" width="{overlay_rect_width}" height="{rect_pixel_height}" stroke="{overlay_border_color}" stroke-width="{overlay_border_width}" fill="none" />'

    # Insert the bar just before the closing </svg> tag
    return svg_content.replace("</svg>", f"    {bar_svg}\n</svg>")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=datetime.date.today().isoformat(), help='Date in YYYY-MM-DD format for base SVG creation')
    parser.add_argument('--lat', type=float, help='Latitude for base SVG creation')
    parser.add_argument('--lon', type=float, help='Longitude for base SVG creation')
    parser.add_argument('--timezone', default='UTC', help='Timezone for base SVG creation')
    
    parser.add_argument('--major-bar-width', type=int, default=1, help='Width of major time bars')
    parser.add_argument('--minor-bar-width', type=int, default=1, help='Width of minor time bars')
    parser.add_argument('--major-bar-color', default='darkgrey', help='Color of major time bars')
    parser.add_argument('--minor-bar-color', default='lightgrey', help='Color of minor time bars')
    parser.add_argument('--background-color', default='transparent', help='Background color of the SVG')
    parser.add_argument('--sun-arc-color', default='rgba(255, 255, 0, 0.5)', help='Color of the sun arc')

    parser.add_argument('--input', help='Path to an existing SVG file to modify')
    parser.add_argument('--time', help='Time to overlay on the SVG, in HH:MM format')
    parser.add_argument('--overlay-rect-width', type=int, default=5, help='Width of the overlay rectangle')
    parser.add_argument('--overlay-rect-height-ratio', type=float, default=1.0, help='Height of the overlay rectangle as a ratio')
    parser.add_argument('--overlay-border-width', type=int, default=2, help='Width of the overlay rectangle border')
    parser.add_argument('--overlay-border-color', default='white', help='Color of the overlay rectangle border')

    parser.add_argument('--output', required=True, help='Output file name')
    args = parser.parse_args()

    if args.input and args.time:
        with open(args.input, 'r') as f:
            svg_content = f.read()
        
        time_obj = datetime.datetime.strptime(args.time, '%H:%M').time()
        # Combine with a dummy date to create a datetime object
        datetime_obj = datetime.datetime.combine(datetime.date.today(), time_obj)

        modified_svg = overlay_time_bar(
            svg_content,
            datetime_obj,
            args.overlay_rect_width,
            args.overlay_border_width,
            args.overlay_border_color,
            args.overlay_rect_height_ratio,
        )
        
        with open(args.output, 'w') as f:
            f.write(modified_svg)
        print(f"Overlay SVG image saved to {args.output}")

    elif args.lat is not None and args.lon is not None:
        date = datetime.date.fromisoformat(args.date)
        svg_content = create_sun_path_svg(
            date,
            args.lat,
            args.lon,
            args.major_bar_width,
            args.minor_bar_width,
            args.major_bar_color,
            args.minor_bar_color,
            args.background_color,
            args.sun_arc_color,
            args.timezone,
        )
        with open(args.output, 'w') as f:
            f.write(svg_content)
        print(f"Base SVG image saved to {args.output}")
    else:
        print("Error: You must either provide --lat and --lon to create a base image, or --input and --time to overlay a bar.")
