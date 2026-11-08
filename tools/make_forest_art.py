"""Generate the HD red-forest backdrop used at the bottom of the sidebar. Run: python3 tools/make_forest_art.py
Deterministic (fixed seed). Output is an opaque PNG, 1736x1432, meant to be scaled down smoothly."""
from pathlib import Path
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H, SS = 1736, 1432, 2
rng = random.Random(7)
np_rng = np.random.default_rng(7)


def noise(w, h, scale, octaves=4):
    out = np.zeros((h, w), dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        s = max(2, int(scale / (2 ** o)))
        small = np_rng.random((h // s + 2, w // s + 2)).astype(np.float32)
        img = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        out += np.asarray(img, dtype=np.float32) / 255 * amp
        total += amp
        amp *= .5
    return out / total


def sky():
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    x = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    glow = np.exp(-(((x - .30) / .55) ** 2 + ((y - .30) / .34) ** 2) * 1.5)
    mist = noise(W, H, 260)
    base = np.clip(glow * (.55 + .75 * mist), 0, 1.25)
    r = 10 + 245 * base ** 1.05
    g = 2 + 36 * base ** 2.2
    b = 6 + 46 * base ** 1.8
    fade = np.clip(1 - np.maximum(0, x - .55) * 1.1, 0.25, 1)
    return np.dstack([r * fade, g * fade, b * fade]).clip(0, 255).astype(np.uint8)


def pine(draw, cx, base_y, height, shade):
    tiers = rng.randint(9, 13)
    width = height * rng.uniform(.28, .36)
    draw.rectangle([cx - height * .012, base_y - height * .12, cx + height * .012, base_y], fill=shade)
    for i in range(tiers):
        t = i / tiers
        y = base_y - height * (.10 + .90 * t)
        half = width * (1 - t) ** .9 * rng.uniform(.92, 1.08) + height * .01
        drop = height * .09 * (1.1 - t * .4)
        pts = [(cx, y - drop * .55), (cx + half, y + drop * .55), (cx + half * .55, y + drop * .35),
               (cx + half * .8, y + drop * .95), (cx, y + drop * .55), (cx - half * .8, y + drop * .95),
               (cx - half * .55, y + drop * .35), (cx - half, y + drop * .55)]
        draw.polygon(pts, fill=shade)
    draw.polygon([(cx, base_y - height * 1.06), (cx + height * .012, base_y - height * .92),
                  (cx - height * .012, base_y - height * .92)], fill=shade)


def mountains(draw):
    pts = [(0, H * .70)]
    for i in range(0, 120):
        x = W * (.34 + .66 * i / 119)
        peak = math.exp(-((i - 30) / 18) ** 2) * H * .17 + math.exp(-((i - 85) / 22) ** 2) * H * .10
        pts.append((x, H * .62 - peak + rng.uniform(-6, 6) * SS))
    pts += [(W, H * .74), (W, H), (0, H)]
    draw.polygon([(x * SS, y * SS) for x, y in [(0, H * .74)] + pts[1:]], fill=(30, 4, 10, 255))


def trees(layer_draw, count, y_lo, y_hi, h_lo, h_hi, shade, x_lo=0, x_hi=1):
    for _ in range(count):
        cx = rng.uniform(W * x_lo, W * x_hi) * SS
        base = rng.uniform(H * y_lo, H * y_hi) * SS
        pine(layer_draw, cx, base, rng.uniform(h_lo, h_hi) * H * SS, shade)


def main():
    base = Image.fromarray(sky(), "RGB").convert("RGBA")
    layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    mountains(d)
    trees(d, 16, .66, .74, .10, .17, (34, 5, 12, 255), .20, 1.0)       # far, hazy
    trees(d, 9, .66, .80, .22, .34, (14, 2, 6, 255), 0.0, .70)          # mid
    trees(d, 4, .70, .84, .40, .56, (4, 1, 3, 255), 0.0, .46)           # near, tall
    slope = [(0, H * .96 * SS)]
    for i in range(0, 60):
        x = W * SS * i / 59
        slope.append((x, (H * (.74 + .13 * i / 59) + math.sin(i * .6) * 10) * SS))
    d.polygon([(0, H * SS)] + slope[1:] + [(W * SS, H * SS)], fill=(2, 1, 3, 255))
    layer = layer.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(.6))
    base.alpha_composite(layer)
    arr = np.asarray(base.convert("RGB"), dtype=np.float32)
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    x = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    vignette = np.clip(1 - (((x - .3) / .95) ** 2 + ((y - .4) / .85) ** 2) * .55, .25, 1)
    arr *= vignette
    arr += np_rng.normal(0, 1.6, arr.shape).astype(np.float32)  # fine grain stops banding after scaling
    out = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB")
    target = Path(__file__).resolve().parents[1] / "gg_desktop" / "assets" / "brand" / "forest_hd.png"
    out.save(target, optimize=True)
    print("wrote", target, out.size)


if __name__ == "__main__":
    main()
