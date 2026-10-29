#!/usr/bin/env python3
"""
Builds the animated GIFs used by the page. Original artwork, drawn with code.

Run it from the repository root:

    python3 scripts/make_gifs.py

It needs two packages:  pip install pillow numpy

Outputs (in assets/):
    globe.gif    a spinning globe (invented continents, not real geography)
    orbit.gif    a small globe with a satellite circling it
    radar.gif    a radar sweep with blips
    divider.gif  a strip of twinkling stars with satellites crossing it
    *.png        one still frame of each GIF. The page shows these to visitors
                 whose system asks for reduced motion.

How the art works, for beginners:
  - A GIF is a list of small pictures (frames) shown one after another.
  - We draw each frame as a grid of pixels with numpy, then save them all.
  - "Pixel art" look: we draw small, then enlarge with no smoothing.
"""
import math
import os
import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(1996)  # fixed seed: same art every run


def save_gif(frames, name, ms):
    """Save a list of RGBA images as an animated GIF with a transparent background."""
    out_frames = []
    for im in frames:
        alpha = np.array(im)[:, :, 3] > 127                 # True where a pixel is visible
        q = im.convert('RGB').quantize(colors=255, method=Image.Quantize.MEDIANCUT,
                                       dither=Image.Dither.NONE)
        idx = np.array(q)
        idx[~alpha] = 255                                    # index 255 means "transparent"
        p = Image.fromarray(idx, mode='P')
        pal = (q.getpalette() or [])[:765]
        pal += [0] * (768 - len(pal))
        p.putpalette(pal)
        out_frames.append(p)
    out_frames[0].save(os.path.join(OUT, name + '.gif'), save_all=True,
                       append_images=out_frames[1:], duration=ms, loop=0,
                       transparency=255, disposal=2, optimize=False)
    frames[0].save(os.path.join(OUT, name + '.png'))        # still frame for reduced motion


def enlarge(im, k):
    """Make the picture k times bigger with hard pixel edges."""
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


# ---------------------------------------------------------------- globe
def globe_pixels(n, spin, tilt=0.4):
    """Return an n x n RGBA array of a lit globe turned by 'spin' radians."""
    ys, xs = np.mgrid[0:n, 0:n]
    x = (xs + 0.5 - n / 2) / (n / 2 - 0.5)
    y = -(ys + 0.5 - n / 2) / (n / 2 - 0.5)
    r2 = x * x + y * y
    inside = r2 <= 1.0
    z = np.sqrt(np.clip(1 - r2, 0, 1))

    # Tilt the globe toward the viewer, then read off latitude and longitude.
    ct, st = math.cos(tilt), math.sin(tilt)
    y2 = y * ct + z * st
    z2 = -y * st + z * ct
    lat = np.arcsin(np.clip(y2, -1, 1))
    lon = np.arctan2(x, z2) + spin

    # Invented continents: a few overlapping waves, cut at a threshold.
    wave = (np.sin(2 * lon + 1.3) * np.cos(1.5 * lat)
            + 0.7 * np.sin(3 * lon - 2.0 + 2 * lat)
            + 0.5 * np.cos(3 * lat + lon))
    land = wave > 0.55
    ice = np.abs(lat) > 1.22

    # Simple lighting: bright upper left, dark lower right, in five steps.
    light = 0.5 + 0.5 * (-0.45 * x + 0.55 * y + 0.7 * z)
    light = np.clip(np.floor(light * 5) / 5, 0.25, 1.0)

    ocean_c = np.array([30, 100, 220])
    land_c = np.array([70, 190, 80])
    ice_c = np.array([235, 245, 255])
    rgb = np.where(land[..., None], land_c, ocean_c).astype(float)
    rgb = np.where(ice[..., None], ice_c, rgb)
    rgb *= light[..., None]

    # Grid lines every 30 degrees of longitude and 30 of latitude.
    deg_lon = np.degrees(lon) % 30
    deg_lat = np.degrees(lat) % 30
    grid = ((deg_lon < 3) | (deg_lon > 27) | (deg_lat < 3) | (deg_lat > 27)) & (z > 0.15)
    rgb = np.where(grid[..., None], rgb * 0.55 + np.array([255, 255, 255]) * 0.45 * 0.5, rgb)

    # Dark rim so the globe reads against any background.
    rim = r2 > 0.82
    rgb = np.where(rim[..., None], rgb * 0.45, rgb)

    out = np.zeros((n, n, 4), dtype=np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = np.where(inside, 255, 0)
    return out


def make_globe():
    frames = []
    count = 24
    for i in range(count):
        px = globe_pixels(48, 2 * math.pi * i / count)
        frames.append(enlarge(Image.fromarray(px, 'RGBA'), 2))     # 96 x 96
    save_gif(frames, 'globe', 80)


# ---------------------------------------------------------------- satellite sprite
def draw_satellite(d, cx, cy):
    """Draw a tiny satellite centered near (cx, cy) on an ImageDraw canvas."""
    d.rectangle([cx - 6, cy - 1, cx - 3, cy + 1], fill=(60, 120, 255, 255))   # left panel
    d.rectangle([cx + 3, cy - 1, cx + 6, cy + 1], fill=(60, 120, 255, 255))   # right panel
    d.rectangle([cx - 2, cy - 2, cx + 2, cy + 2], fill=(235, 235, 235, 255))  # body
    d.rectangle([cx - 1, cy - 1, cx + 1, cy + 1], fill=(255, 210, 0, 255))    # gold core
    d.point([cx, cy - 3], fill=(255, 80, 80, 255))                            # antenna tip
    d.point([cx, cy - 4], fill=(255, 80, 80, 255))


def make_orbit():
    w, h = 64, 40            # drawn small, shown at 2x: 128 x 80
    frames = []
    count = 36
    cx, cy = w // 2, h // 2 + 1
    a, b, tilt = 27, 9, math.radians(-18)
    globe = Image.fromarray(globe_pixels(24, 0.0, tilt=0.5), 'RGBA')
    for i in range(count):
        t = 2 * math.pi * i / count
        # Spin the little globe a bit each frame too.
        globe = Image.fromarray(globe_pixels(24, t, tilt=0.5), 'RGBA')

        def pos(u):
            ex, ey = a * math.cos(u), b * math.sin(u)
            return (cx + ex * math.cos(tilt) - ey * math.sin(tilt),
                    cy + ex * math.sin(tilt) + ey * math.cos(tilt))

        back = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        front = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        db, df = ImageDraw.Draw(back), ImageDraw.Draw(front)
        for k in range(0, 72, 2):                                # dotted orbit line
            u = 2 * math.pi * k / 72
            x, y = pos(u)
            target = db if math.sin(u) < 0 else df
            target.point([round(x), round(y)], fill=(170, 220, 255, 200))
        sx, sy = pos(t)
        (db if math.sin(t) < 0 else df)  # satellite is behind the globe when sin(t) < 0
        sat_layer = db if math.sin(t) < 0 else df
        draw_satellite(sat_layer, round(sx), round(sy))

        frame = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        frame.alpha_composite(back)
        frame.alpha_composite(globe, (cx - 12, cy - 12))
        frame.alpha_composite(front)
        frames.append(enlarge(frame, 2))
    save_gif(frames, 'orbit', 70)


# ---------------------------------------------------------------- radar
def make_radar():
    n = 40
    ys, xs = np.mgrid[0:n, 0:n]
    x = (xs + 0.5 - n / 2) / (n / 2 - 0.5)
    y = -(ys + 0.5 - n / 2) / (n / 2 - 0.5)
    r = np.sqrt(x * x + y * y)
    theta = np.arctan2(y, x) % (2 * math.pi)
    blips = [(0.55, 0.9), (0.30, 2.6), (0.75, 4.1), (0.62, 5.5)]   # (distance, angle)
    frames = []
    count = 36
    for i in range(count):
        sweep = (2 * math.pi - 2 * math.pi * i / count) % (2 * math.pi)  # clockwise
        behind = (sweep - theta) % (2 * math.pi)                         # how far behind the beam
        glow = np.clip(1 - behind / 1.4, 0, 1)
        rgb = np.zeros((n, n, 3), dtype=float)
        rgb[..., 1] = 25 + 180 * glow                                    # green glow
        rgb[..., 0] = 10 * glow
        rings = (np.abs(r - 0.33) < 0.04) | (np.abs(r - 0.66) < 0.04) | (np.abs(r - 0.97) < 0.05)
        cross = (np.abs(x) < 0.03) | (np.abs(y) < 0.03)
        rgb[rings | cross] = np.maximum(rgb[rings | cross], [0, 110, 0])
        for dist, ang in blips:                                          # blips fade after the beam passes
            lag = (sweep - ang) % (2 * math.pi)
            level = max(0.0, 1 - lag / 3.0)
            if level > 0:
                bx = round(n / 2 + dist * math.cos(ang) * (n / 2 - 1))
                by = round(n / 2 - dist * math.sin(ang) * (n / 2 - 1))
                rgb[by - 1:by + 1, bx - 1:bx + 1] = [120 + 135 * level, 255 * level + 20, 80 * level]
        out = np.zeros((n, n, 4), dtype=np.uint8)
        out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
        out[..., 3] = np.where(r <= 1.0, 255, 0)
        edge = (r > 0.93) & (r <= 1.0)
        out[edge, :3] = [40, 200, 40]
        frames.append(enlarge(Image.fromarray(out, 'RGBA'), 2))          # 80 x 80
    save_gif(frames, 'radar', 70)


# ---------------------------------------------------------------- divider strip
def make_divider():
    w, h = 240, 12                       # shown at 2x: 480 x 24 (tiles side by side)
    count = 24
    step = w // count                    # satellites move 10 pixels a frame, so the loop is seamless
    stars = [(int(rng.integers(0, w)), int(rng.integers(0, h)), float(rng.random() * 6.28),
              [(255, 255, 255), (255, 255, 0), (0, 255, 255)][int(rng.integers(0, 3))]) for _ in range(34)]
    sats = [0, w // 2]                   # two satellites, half a strip apart
    frames = []
    for i in range(count):
        frame = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(frame)
        for k in range(0, w, 4):                                  # dotted line down the middle
            d.point([k, h // 2], fill=(120, 190, 255, 140))
        for sx, sy, phase, color in stars:                        # twinkle
            if math.sin(phase + 2 * math.pi * i / count * 2) > -0.2:
                d.point([sx, sy], fill=color + (255,))
        for base in sats:
            px = (base + step * i) % w
            for off in (-w, 0, w):                                # draw again at both edges so it wraps
                x = px + off
                if -8 <= x <= w + 8:
                    # small satellite: body plus two panels
                    d.rectangle([x - 3, h // 2 - 1, x - 2, h // 2 + 1], fill=(60, 120, 255, 255))
                    d.rectangle([x + 2, h // 2 - 1, x + 3, h // 2 + 1], fill=(60, 120, 255, 255))
                    d.rectangle([x - 1, h // 2 - 1, x + 1, h // 2 + 1], fill=(255, 210, 0, 255))
        frames.append(enlarge(frame, 2))
    save_gif(frames, 'divider', 90)


if __name__ == '__main__':
    make_globe()
    make_orbit()
    make_radar()
    make_divider()
    print('Wrote GIFs and PNG stills to', os.path.abspath(OUT))
