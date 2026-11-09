"""Generate the panoramic HD header art, one per tab. Run: python3 tools/make_banner_art.py
Needs rsvg-convert and Pillow. Deterministic. Writes gg_desktop/assets/brand/banner_<tab>.jpg.

Restrained abstract art in the Game Grave brand language (the logo's slanted bars): no illustrations. Every picture
is 6000x500 and exactly symmetric top to bottom, so it stays centred however the window crops it. Light builds from
the left (calm, behind the title) to a soft glow on the right; each tab differs only in its accent colour and the
rhythm of its bars.
"""
from pathlib import Path
import io
import math
import random
import subprocess

from PIL import Image, ImageChops

OUT = Path(__file__).resolve().parents[1] / "gg_desktop" / "assets" / "brand"
W, H = 6000, 500
MID = H / 2

# slug: (main accent, second accent, bar rhythm: (count, spacing))
TABS = {
    "overview": ("#ff2a4d", "#13bcf5", (15, 1.00)),
    "ready_room": ("#ff3b30", "#ffb46a", (13, 1.10)),
    "games": ("#ff2a4d", "#7a5cff", (17, .90)),
    "mods": ("#ff2a6d", "#13d5e2", (14, 1.00)),
    "old_files": ("#ff7a3a", "#ff2a4d", (12, 1.15)),
    "other_storage": ("#18c9eb", "#ff2a4d", (14, 1.00)),
    "captures": ("#e175eb", "#ff2a4d", (16, .95)),
    "graveyard": ("#9a6bff", "#ff2a4d", (12, 1.10)),
    "dna": ("#ff2a4d", "#18c9eb", (18, .85)),
    "undo": ("#f2b43a", "#ff2a4d", (13, 1.05)),
    "settings": ("#7f93ad", "#ff2a4d", (14, 1.00)),
    "assistant": ("#30d76b", "#18c9eb", (15, .95)),
    "more_tools": ("#ff2a4d", "#f2b43a", (14, 1.00)),
}


def picture(slug, seed):
    a, b, (count, gap) = TABS[slug]
    r = random.Random(seed)
    cx = 4750  # where the light is brightest
    skew = math.tan(math.radians(20))
    bars = []
    step = 150 * gap
    for k in range(-count, count + 1):
        d = k * step + r.uniform(-18, 18)
        width = 60 if (k % 6 == 0 and k) else r.choice((8, 12, 18, 26))
        opacity = .03 + .34 * math.exp(-(d / 900) ** 2)
        colour = b if k % 5 == 0 else a
        x = cx + d
        top = -MID * skew
        bars.append(f'<path d="M{x + top:.0f} -20 h{width} L{x + width - top:.0f} {H + 20} h-{width} Z" '
                    f'fill="{colour}" opacity="{opacity:.2f}"/>')
    hairlines = "".join(
        f'<line x1="{cx - 2400}" y1="{MID + d}" x2="{W}" y2="{MID + d}" stroke="url(#hair)" stroke-width="2" opacity="{o}"/>'
        f'<line x1="{cx - 2400}" y1="{MID - d}" x2="{W}" y2="{MID - d}" stroke="url(#hair)" stroke-width="2" opacity="{o}"/>'
        for d, o in ((60, .55), (118, .38), (176, .24), (228, .14)))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
 <linearGradient id="wall" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#03070a"/><stop offset=".55" stop-color="#070b10"/><stop offset="1" stop-color="#0b1117"/></linearGradient>
 <radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{a}" stop-opacity=".30"/><stop offset=".5" stop-color="{a}" stop-opacity=".09"/><stop offset="1" stop-color="{a}" stop-opacity="0"/></radialGradient>
 <radialGradient id="glow2" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{b}" stop-opacity=".30"/><stop offset="1" stop-color="{b}" stop-opacity="0"/></radialGradient>
 <linearGradient id="hair" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{a}" stop-opacity="0"/><stop offset=".6" stop-color="{a}" stop-opacity=".9"/><stop offset="1" stop-color="{b}" stop-opacity=".8"/></linearGradient>
 <linearGradient id="reveal" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".4" stop-color="#fff" stop-opacity=".3"/><stop offset=".8" stop-color="#fff" stop-opacity="1"/></linearGradient>
 <mask id="fadein" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="url(#reveal)"/></mask>
 <pattern id="dots" width="44" height="44" patternUnits="userSpaceOnUse"><circle cx="22" cy="22" r="1.6" fill="{a}" opacity=".55"/></pattern>
</defs>
<rect width="{W}" height="{H}" fill="url(#wall)"/>
<ellipse cx="{cx}" cy="{MID}" rx="1700" ry="520" fill="url(#glow)"/>
<ellipse cx="{cx + 800}" cy="{MID}" rx="800" ry="420" fill="url(#glow2)"/>
<rect width="{W}" height="{H}" fill="url(#dots)" mask="url(#fadein)" opacity=".5"/>
<g mask="url(#fadein)">{hairlines}</g>
{"".join(bars)}
</svg>"""


def render(slug, seed):
    svg = OUT / (slug + ".svg")
    svg.write_text(picture(slug, seed))
    png = subprocess.run(["rsvg-convert", "-w", str(W), str(svg)], check=True, capture_output=True).stdout
    svg.unlink()
    image = Image.open(io.BytesIO(png)).convert("RGB")
    grain = Image.effect_noise(image.size, 2.5).convert("RGB")  # hides banding in the dark gradients
    image = ImageChops.add(image, grain, 1, -128)
    target = OUT / ("banner_" + slug + ".jpg")
    image.save(target, quality=90, subsampling=0, optimize=True)
    print("wrote", target, target.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    for i, name in enumerate(TABS):
        render(name, 40 + i)
