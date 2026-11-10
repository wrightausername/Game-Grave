"""Generate the panoramic HD header art, one per tab. Run: python3 tools/make_banner_art.py
Needs rsvg-convert and Pillow. Deterministic. Writes gg_desktop/assets/brand/banner_<tab>.jpg.

Abstract gaming motifs, one per tab, kept clear of the sidebar art (hex grid, circuit traces, gamepad outline):
pixel equalizer, perspective tunnel, HUD reticle, modular diamonds, glitch bands, HUD health bars, viewfinder,
pixel sparks, pixel helix, rewind chevrons, processor packages, mixer sliders, constellation and block puzzle. No characters, no logos.
Every picture is 6000x500 and exactly symmetric top to bottom, so it stays centred however the window crops it.
The left half stays calm behind the title; the motif builds toward the right, where the light is brightest.
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
CX = 4750  # where the light is brightest

# slug: (main accent, second accent, motif)
TABS = {
    "overview": ("#ff2a4d", "#13bcf5", "equalizer"),
    "ready_room": ("#ff3b30", "#ffb46a", "tunnel"),
    "games": ("#ff2a4d", "#7a5cff", "reticle"),
    "mods": ("#ff2a6d", "#13d5e2", "diamonds"),
    "old_files": ("#ff7a3a", "#ff2a4d", "glitch"),
    "other_storage": ("#18c9eb", "#ff2a4d", "healthbars"),
    "captures": ("#e175eb", "#ff2a4d", "viewfinder"),
    "graveyard": ("#9a6bff", "#ff2a4d", "sparks"),
    "dna": ("#ff2a4d", "#18c9eb", "helix"),
    "hardware": ("#13bcf5", "#ff2a4d", "chips"),
    "undo": ("#f2b43a", "#ff2a4d", "rewind"),
    "settings": ("#7f93ad", "#ff2a4d", "sliders"),
    "assistant": ("#30d76b", "#18c9eb", "constellation"),
    "more_tools": ("#ff2a4d", "#f2b43a", "blocks"),
}


def rect(x, y, w, h, fill, op, extra=""):
    return f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" fill="{fill}" opacity="{op:.2f}" {extra}/>'


def line(x1, y1, x2, y2, stroke, op, width=3):
    return (f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{stroke}" '
            f'stroke-width="{width}" opacity="{op:.2f}"/>')


def bell(x, centre=CX, spread=1100):
    return math.exp(-((x - centre) / spread) ** 2)


# ---------------------------------------------------------------- motifs drawn in the top half, then mirrored
def equalizer(a, b, r):
    out = []
    for i, x in enumerate(range(2500, W, 46)):
        height = int(1 + 6.2 * bell(x, CX - 150, 1300) * r.uniform(.45, 1.0) + r.uniform(0, 1.2))
        for k in range(min(height, 7)):
            y = MID - 8 - (k + 1) * 33
            peak = k == height - 1
            colour = b if i % 7 == 0 else a
            out.append(rect(x, y, 30, 31, colour, (.9 if peak else .28 + .25 * bell(x)) * (1 - k * .05)))
    return "".join(out)


def diamonds(a, b, r):
    out = []
    size = 96
    for row in range(0, 3):
        for col in range(0, 36):
            x = 2400 + col * size + (size / 2 if row % 2 else 0)
            y = MID - 28 - row * size * .5
            if r.random() < .30:
                continue  # a missing piece, like a removed mod
            fill = r.random() < .45
            colour = b if r.random() < .14 else a
            op = (.10 + .6 * bell(x, CX, 1200)) * (1 - row * .22)
            pts = f"{x:.0f},{y - 44:.0f} {x + 44:.0f},{y:.0f} {x:.0f},{y + 44:.0f} {x - 44:.0f},{y:.0f}"
            style = (f'fill="{colour}" fill-opacity="{op * .9:.2f}"' if fill
                     else f'fill="none" stroke="{colour}" stroke-width="3" stroke-opacity="{op + .1:.2f}"')
            out.append(f'<polygon points="{pts}" {style}/>')
    return "".join(out)


def glitch(a, b, r):
    out = []
    for _ in range(20):
        y = r.uniform(10, MID - 6)
        x = r.uniform(2400, 5800)
        w = r.uniform(90, 560)
        h = r.choice((6, 10, 16, 26))
        op = .08 + .55 * bell(x + w / 2, CX, 1500)
        out.append(rect(x, y, w, h, a, op))
        out.append(rect(x + 14, y + 2, w, h, b, op * .45))
        if r.random() < .4:
            out.append(rect(x + w * r.uniform(.2, .8), y - 3, r.uniform(30, 90), h + 6, "#ffffff", op * .35))
    return "".join(out)


def healthbars(a, b, r):
    out = []
    for row in range(5):
        centre = 34 + row * 46
        start = 2600 + row * 120 + r.uniform(0, 140)
        segments = int((W - start) // 64)
        lit = int(segments * r.uniform(.5, .92))
        for s in range(segments):
            x = start + s * 64
            height = r.choice((12, 18, 24, 32, 38))
            colour = b if row == 2 else a
            op = (.55 + .35 * bell(x, CX, 1300)) if s < lit else .12
            out.append(rect(x, centre - height / 2, 52, height, colour, op))
    return "".join(out)


def sparks(a, b, r):
    out = []
    for _ in range(46):
        x, y = r.uniform(2300, 5900), r.uniform(18, MID - 20)
        s = r.choice((8, 10, 14, 20))
        op = .12 + .75 * bell(x, CX, 1400) * r.uniform(.5, 1)
        colour = b if r.random() < .2 else a
        out += [rect(x - s / 2, y - s / 2, s, s, colour, op), rect(x - s * 1.5, y - s / 2, s, s, colour, op * .6),
                rect(x + s * .5, y - s / 2, s, s, colour, op * .6), rect(x - s / 2, y - s * 1.5, s, s, colour, op * .6),
                rect(x - s / 2, y + s * .5, s, s, colour, op * .6)]
        if r.random() < .35:
            tail = r.uniform(160, 520)
            out.append(f'<line x1="{x + s * 2:.0f}" y1="{y:.0f}" x2="{x + s * 2 + tail:.0f}" y2="{y:.0f}" '
                       f'stroke="{colour}" stroke-width="{max(2, s / 3):.0f}" stroke-dasharray="{s} {s * 1.4:.0f}" opacity="{op * .5:.2f}"/>')
    return "".join(out)


def sliders(a, b, r):
    out = []
    for i in range(4):
        y = 40 + i * 60
        x0 = 2500 + r.uniform(0, 300)
        x1 = W - r.uniform(0, 200)
        knob = x0 + (x1 - x0) * r.uniform(.25, .85)
        colour = b if i == 1 else a
        out.append(line(x0, y, x1, y, "#9aa8b6", .14, 4))
        out.append(line(x0, y, knob, y, colour, .55, 8))
        for t in range(0, 60):
            x = x0 + t * (x1 - x0) / 59
            out.append(line(x, y - 14, x, y - 6, "#9aa8b6", .16, 2))
        out.append(rect(knob - 16, y - 20, 32, 40, colour, .85))
        out.append(rect(knob - 16, y - 20, 32, 8, "#ffffff", .25))
    return "".join(out)


def constellation(a, b, r):
    pts = [(r.uniform(2400, 5950), r.uniform(14, MID - 10)) for _ in range(70)]
    out = []
    for i, (x, y) in enumerate(pts):
        near = sorted(((px - x) ** 2 + (py - y) ** 2, j) for j, (px, py) in enumerate(pts) if j != i)[:2]
        for dist, j in near:
            if dist < 330 ** 2 and j > i:
                out.append(line(x, y, pts[j][0], pts[j][1], a, .10 + .35 * bell(x, CX, 1500), 2))
    for i, (x, y) in enumerate(pts):
        op = .2 + .7 * bell(x, CX, 1500)
        size = r.choice((12, 16, 22))
        out.append(rect(x - size / 2, y - size / 2, size, size, b if i % 6 == 0 else a, op,
                        f'transform="rotate(45 {x:.0f} {y:.0f})"'))
    return "".join(out)


def blocks(a, b, r):
    shapes = [((0, 0), (1, 0), (2, 0), (3, 0)), ((0, 0), (1, 0), (0, 1), (1, 1)), ((0, 0), (1, 0), (2, 0), (1, 1)),
              ((0, 0), (0, 1), (1, 1), (2, 1)), ((1, 0), (2, 0), (0, 1), (1, 1)), ((0, 0), (1, 0), (1, 1), (2, 1))]
    cell, gap = 40, 6
    pitch = cell + gap
    taken, out = set(), []
    for _ in range(90):
        shape = r.choice(shapes)
        gx = r.randint(0, (W - 2400) // pitch - 5)
        gy = r.randint(0, 3)
        cells = {(gx + dx, gy + dy) for dx, dy in shape}
        halo = {(x + i, y + j) for x, y in cells for i in (-1, 0, 1) for j in (-1, 0, 1)}
        if halo & taken or any(y > 4 for _, y in cells):
            continue
        taken |= cells
        colour = b if r.random() < .2 else a
        for x, y in cells:
            px, py = 2400 + x * pitch, MID - 10 - (y + 1) * pitch
            out.append(rect(px, py, cell, cell, colour, .12 + .7 * bell(px, CX, 1300)))
    return "".join(out)


# ---------------------------------------------------------------- motifs that are symmetric by construction
def tunnel(a, b, r):
    vx = CX + 350
    out = []
    for k in range(-16, 17):
        out.append(line(vx + k * 40, MID, vx + k * 300, -20, a, .06 + .4 * math.exp(-(k / 8) ** 2), 3))
        out.append(line(vx + k * 40, MID, vx + k * 300, H + 20, a, .06 + .4 * math.exp(-(k / 8) ** 2), 3))
    for i in range(1, 10):
        d = MID * (i / 9) ** 1.9
        o = .12 + .5 * (1 - i / 10)
        colour = b if i % 4 == 0 else a
        x = vx - 3000 + r.uniform(0, 200)
        while x < W:
            length = r.uniform(140, 520)
            out.append(line(x, MID - d, x + length, MID - d, colour, o, 3))
            out.append(line(x, MID + d, x + length, MID + d, colour, o, 3))
            x += length + r.uniform(160, 520)
    out.append(f'<ellipse cx="{vx}" cy="{MID}" rx="120" ry="14" fill="{b}" opacity=".55"/>')
    return "".join(out)


def reticle(a, b, r):
    out = []
    for cx, scale, o in ((CX, 1.0, 1.0), (CX - 900, .55, .55), (CX + 900, .55, .55)):
        for radius, width, dash in ((205, 5, ""), (150, 3, 'stroke-dasharray="14 22"'), (78, 4, ""), (16, 0, "fill")):
            rr = radius * scale
            if dash == "fill":
                out.append(f'<circle cx="{cx}" cy="{MID}" r="{10 * scale + 4:.0f}" fill="{b}" opacity="{.9 * o:.2f}"/>')
            else:
                out.append(f'<circle cx="{cx}" cy="{MID}" r="{rr:.0f}" fill="none" stroke="{a}" stroke-width="{width}" '
                           f'opacity="{.7 * o:.2f}" {dash}/>')
        for ang in range(0, 360, 30):
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            out.append(line(cx + ca * 205 * scale, MID + sa * 205 * scale, cx + ca * 232 * scale, MID + sa * 232 * scale,
                            b if ang % 90 == 0 else a, .8 * o, 5))
        for sign in (-1, 1):
            out.append(line(cx + sign * 100 * scale, MID, cx + sign * 190 * scale, MID, a, .8 * o, 4))
            out.append(line(cx, MID + sign * 100 * scale, cx, MID + sign * 190 * scale, a, .8 * o, 4))
    out.append(line(CX - 2400, MID, CX - 260, MID, a, .25, 2))
    return "".join(out)


def chips(a, b, r):
    """Processor packages seen from above: square die, pin rows on all four sides, a heat spreader. Mirror-symmetric."""
    out = []
    for cx, size, o in ((CX, 340, 1.0), (CX - 1000, 210, .55), (CX + 1000, 210, .55)):
        half = size / 2
        scale = size / 340
        pins = 11
        gap = size / (pins + 1)
        for i in range(pins):
            offset = -half + gap * (i + 1)
            for sign in (-1, 1):
                out.append(rect(cx + offset - 5 * scale, MID + sign * (half + 17 * scale) - 17 * scale, 10 * scale, 34 * scale, a, .8 * o))
                out.append(rect(cx + sign * (half + 17 * scale) - 17 * scale, MID + offset - 5 * scale, 34 * scale, 10 * scale, a, .8 * o))
        out.append(rect(cx - half, MID - half, size, size, "#0a1218", .9 * o, f'stroke="{a}" stroke-width="{6 * scale:.1f}" rx="{14 * scale:.0f}"'))
        inner = half * .62
        out.append(rect(cx - inner, MID - inner, inner * 2, inner * 2, "none", .9 * o, f'stroke="{b}" stroke-width="{5 * scale:.1f}" rx="{8 * scale:.0f}"'))
        core = inner * .52
        out.append(rect(cx - core, MID - core, core * 2, core * 2, b, .55 * o, f'rx="{5 * scale:.0f}"'))
        for dx in (-1, 1):
            for dy in (-1, 1):
                out.append(rect(cx + dx * inner * .55 - 7 * scale, MID + dy * inner * .55 - 7 * scale, 14 * scale, 14 * scale, a, .9 * o))
    out.append(line(CX - 2500, MID, CX - 1250, MID, a, .25, 2))
    out.append(line(CX - 870, MID, CX - 200, MID, a, .35, 3))
    out.append(line(CX + 200, MID, CX + 870, MID, a, .35, 3))
    return "".join(out)


def viewfinder(a, b, r):
    out = []
    for half_w, half_h, o, length in ((1250, 215, .85, 90), (900, 150, .55, 70), (520, 85, .4, 50)):
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = CX + sx * half_w, MID + sy * half_h
                out.append(f'<path d="M{x - sx * length} {y} H{x} V{y - sy * length}" fill="none" stroke="{a}" '
                           f'stroke-width="7" opacity="{o:.2f}" stroke-linejoin="miter"/>')
    for t in range(-12, 13):
        h = 26 if t % 4 == 0 else 14
        out.append(line(CX + t * 90, MID - 215, CX + t * 90, MID - 215 + h, a, .5, 3))
        out.append(line(CX + t * 90, MID + 215, CX + t * 90, MID + 215 - h, a, .5, 3))
    out.append(f'<circle cx="{CX - 1100}" cy="{MID - 150}" r="16" fill="{b}" opacity=".9"/>')
    out.append(f'<circle cx="{CX - 1100}" cy="{MID + 150}" r="16" fill="{b}" opacity=".9"/>')
    out.append(line(CX - 60, MID, CX + 60, MID, b, .8, 5))
    out.append(line(CX, MID - 60, CX, MID + 60, b, .8, 5))
    return "".join(out)


def helix(a, b, r):
    out = []
    for x in range(2400, W, 34):
        phase = x / 118
        y1, y2 = MID + 150 * math.sin(phase), MID - 150 * math.sin(phase)
        depth = math.cos(phase)
        glow = .15 + .75 * bell(x, CX, 1500)
        size = 22 + 12 * depth
        if (x // 34) % 4 == 0:
            out.append(line(x, y1, x, y2, b, glow * .45, 3))
        out.append(rect(x - size / 2, y1 - size / 2, size, size, a, glow * (.6 + .4 * depth)))
        out.append(rect(x - size / 2, y2 - size / 2, size, size, b if (x // 34) % 9 == 0 else a, glow * (.6 - .4 * depth + .2)))
    return "".join(out)


def rewind(a, b, r):
    out = []
    for row, (height, pitch, o) in enumerate(((420, 190, 1.0), (260, 130, .55))):
        for i in range(0, 30):
            x = 2500 + i * pitch + row * 70
            if x > W:
                break
            glow = .08 + .75 * bell(x, CX, 1300)
            colour = b if (i % 6 == 0 and row == 0) else a
            out.append(f'<path d="M{x + height * .28:.0f} {MID - height / 2:.0f} L{x:.0f} {MID} L{x + height * .28:.0f} {MID + height / 2:.0f}" '
                       f'fill="none" stroke="{colour}" stroke-width="{26 - row * 10}" stroke-linejoin="miter" opacity="{glow * o:.2f}"/>')
    return "".join(out)


MIRRORED = {"equalizer": equalizer, "diamonds": diamonds, "glitch": glitch, "healthbars": healthbars, "sparks": sparks,
            "sliders": sliders, "constellation": constellation, "blocks": blocks}
CENTRED = {"chips": chips, "tunnel": tunnel, "reticle": reticle, "viewfinder": viewfinder, "helix": helix, "rewind": rewind}


def picture(slug, seed):
    a, b, motif = TABS[slug]
    r = random.Random(seed)
    if motif in MIRRORED:
        top = MIRRORED[motif](a, b, r)
        art = f'<g>{top}</g><g transform="matrix(1 0 0 -1 0 {H})">{top}</g>'
    else:
        art = CENTRED[motif](a, b, r)
    scan = "".join(line(0, y, W, y, "#000", .20, 2) for y in range(4, H, 10))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
 <linearGradient id="wall" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#03070a"/><stop offset=".55" stop-color="#070b10"/><stop offset="1" stop-color="#0b1117"/></linearGradient>
 <radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{a}" stop-opacity=".30"/><stop offset=".5" stop-color="{a}" stop-opacity=".09"/><stop offset="1" stop-color="{a}" stop-opacity="0"/></radialGradient>
 <radialGradient id="glow2" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{b}" stop-opacity=".26"/><stop offset="1" stop-color="{b}" stop-opacity="0"/></radialGradient>
 <linearGradient id="reveal" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".38" stop-color="#fff" stop-opacity=".25"/><stop offset=".72" stop-color="#fff" stop-opacity="1"/></linearGradient>
 <mask id="fadein" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="url(#reveal)"/></mask>
</defs>
<rect width="{W}" height="{H}" fill="url(#wall)"/>
<ellipse cx="{CX}" cy="{MID}" rx="1700" ry="520" fill="url(#glow)"/>
<ellipse cx="{CX + 800}" cy="{MID}" rx="800" ry="420" fill="url(#glow2)"/>
<g mask="url(#fadein)">{art}</g>
<g mask="url(#fadein)">{scan}</g>
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
