"""Generate the panoramic HD banner art, one per tab. Run: python3 tools/make_banner_art.py
Needs rsvg-convert and Pillow. Deterministic. Writes gg_desktop/assets/brand/banner_<tab>.jpg.

Every picture is 6000x500 (12:1) so it can be cropped to fill the full width of any window: the busy part
sits at about 83% of the width (clear of the title on the left and of the window controls on the far right),
and the rest is calm atmosphere (hex grid, circuit traces, glow) that keeps the whole header looking finished.
"""
from math import cos, pi, sin
from pathlib import Path
import io
import random
import subprocess

from PIL import Image, ImageChops

OUT = Path(__file__).resolve().parents[1] / "gg_desktop" / "assets" / "brand"
W, H = 6000, 500
CX, CY = 5000, 250  # centre of the picture's subject
G = "M170 46 H82 Q24 46 24 104 V134 Q24 192 82 192 H120 Q168 192 168 144 V114 H102"

DEFS = f"""
<defs>
 <linearGradient id="wall" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#04080b"/><stop offset=".6" stop-color="#0a0e14"/><stop offset="1" stop-color="#0d1218"/></linearGradient>
 <radialGradient id="haze" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ff2a4d" stop-opacity=".5"/><stop offset=".55" stop-color="#b3112b" stop-opacity=".16"/><stop offset="1" stop-color="#b3112b" stop-opacity="0"/></radialGradient>
 <radialGradient id="cyan" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#13bcf5" stop-opacity=".38"/><stop offset="1" stop-color="#13bcf5" stop-opacity="0"/></radialGradient>
 <linearGradient id="red" x1="0" y1="0" x2=".35" y2="1"><stop offset="0" stop-color="#ff5a68"/><stop offset=".5" stop-color="#e5162d"/><stop offset="1" stop-color="#8a0c1c"/></linearGradient>
 <linearGradient id="screen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3a0610"/><stop offset="1" stop-color="#12050a"/></linearGradient>
 <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#252d37"/><stop offset="1" stop-color="#0c1015"/></linearGradient>
 <linearGradient id="reveal" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".45" stop-color="#fff" stop-opacity=".25"/><stop offset=".85" stop-color="#fff" stop-opacity="1"/><stop offset="1" stop-color="#fff" stop-opacity=".6"/></linearGradient>
 <mask id="fadein" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="url(#reveal)"/></mask>
 <pattern id="hex" width="104" height="180" patternUnits="userSpaceOnUse" patternTransform="translate(0 4)">
  <path d="M52 0 L104 30 V90 L52 120 L0 90 V30 Z M52 120 V180 M0 90 L-52 120 M104 90 L156 120" fill="none" stroke="#ff2a4d" stroke-width="2" stroke-opacity=".30"/>
 </pattern>
 <filter id="blur40" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="40"/></filter>
 <filter id="blur14" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>
 <filter id="blur4" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter>
 <symbol id="mark" viewBox="0 0 400 280"><g transform="translate(10 6) skewX(-13)"><path d="{G}" fill="none" stroke="url(#red)" stroke-width="42"/></g><g transform="translate(130 78) skewX(-13)"><path d="{G}" fill="none" stroke="#04070a" stroke-width="58"/><path d="{G}" fill="none" stroke="url(#red)" stroke-width="42"/></g></symbol>
</defs>"""


def atmosphere(seed):
    """Calm, full-width backdrop: wall gradient, glow, hex grid, circuit traces and sparks."""
    r = random.Random(seed)
    parts = [f'<rect width="{W}" height="{H}" fill="url(#wall)"/>',
             f'<ellipse cx="{CX}" cy="{CY - 10}" rx="1700" ry="430" fill="url(#haze)"/>',
             f'<ellipse cx="{CX + 520}" cy="{CY + 90}" rx="900" ry="300" fill="url(#cyan)"/>',
             f'<rect width="{W}" height="{H}" fill="url(#hex)" mask="url(#fadein)"/>']
    traces = []
    for i in range(34):
        y = 20 + i * 14 + r.uniform(-4, 4)
        x = r.uniform(300, 3600)
        pts = [(x, y)]
        for _ in range(r.randint(2, 5)):
            x += r.uniform(160, 520)
            pts.append((x, pts[-1][1]))
            y = min(H - 10, max(10, pts[-1][1] + r.choice((-1, 1)) * r.uniform(24, 90)))
            pts.append((x + r.uniform(30, 80), y))
            x = pts[-1][0]
        d = "M" + " L".join(f"{px:.0f} {py:.0f}" for px, py in pts)
        tone = "#13bcf5" if i % 6 == 0 else "#ff2a4d"
        traces.append(f'<path d="{d}" fill="none" stroke="{tone}" stroke-width="2.5" opacity=".42" stroke-linejoin="round"/>'
                      f'<circle cx="{pts[-1][0]:.0f}" cy="{pts[-1][1]:.0f}" r="6" fill="{tone}" opacity=".8"/>')
    parts.append('<g mask="url(#fadein)">' + "".join(traces) + "</g>")
    sparks = "".join(
        f'<circle cx="{r.uniform(2200, 5900):.0f}" cy="{r.uniform(20, 480):.0f}" r="{r.uniform(1.5, 4):.1f}" '
        f'fill="{r.choice(("#ff8d99", "#ff5a68", "#7fd8ff"))}" opacity="{r.uniform(.25, .8):.2f}"/>' for _ in range(90))
    parts.append(sparks)
    return "".join(parts)


def halo(width=520, height=260, opacity=.55):
    return f'<ellipse cx="0" cy="10" rx="{width * .8:.0f}" ry="{height * .95:.0f}" fill="url(#haze)" opacity="{min(1, opacity * 1.1):.2f}"/>'


def hexagon(scale=1.0):
    pts = [(0, -170), (147, -85), (147, 85), (0, 170), (-147, 85), (-147, -85)]
    return "M" + " L".join(f"{x * scale:.1f} {y * scale:.1f}" for x, y in pts) + " Z"


def gear(radius, teeth, depth=0.2):
    pts = []
    for i in range(teeth * 4):
        angle = i * pi * 2 / (teeth * 4)
        step = i % 4
        rr = radius * (1 + depth) if step in (1, 2) else radius
        pts.append((rr * cos(angle), rr * sin(angle)))
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


def motif_overview():
    bars = "".join(f'<rect x="{x}" y="{170 - h}" width="34" height="{h}" rx="5" fill="url(#red)" opacity="{o}"/>'
                   for x, h, o in ((-420, 70, .5), (-370, 110, .6), (-320, 150, .7), (-270, 200, .8),
                                   (270, 190, .8), (320, 140, .7), (370, 100, .6), (420, 64, .5)))
    return (halo() + bars + f'<path d="{hexagon()}" fill="url(#metal)" stroke="url(#red)" stroke-width="10"/>'
            f'<path d="{hexagon(.8)}" fill="#07090d" stroke="#ff8d99" stroke-opacity=".4" stroke-width="3"/>'
            '<use xlink:href="#mark" x="-125" y="-88" width="250" height="175"/>')


def monitor(x, y, w, h, seed, tilt=0):
    r = random.Random(seed)
    blobs = "".join(
        f'<ellipse cx="{x + r.uniform(.12, .88) * w:.0f}" cy="{y + r.uniform(.2, .8) * h:.0f}" rx="{r.uniform(.04, .16) * w:.0f}" '
        f'ry="{r.uniform(.04, .12) * h:.0f}" fill="#ff2a4d" opacity="{r.uniform(.25, .6):.2f}"/>' for _ in range(9))
    rows = "".join(f'<rect x="{x + w * .07:.0f}" y="{y + h * (.12 + i * .1):.0f}" width="{w * r.uniform(.2, .6):.0f}" height="{h * .035:.0f}" rx="3" fill="#ff5a68" opacity=".5"/>' for i in range(6))
    return (f'<g transform="rotate({tilt} {x + w / 2} {y + h / 2})">'
            f'<rect x="{x - 12}" y="{y - 12}" width="{w + 24}" height="{h + 24}" rx="12" fill="url(#metal)"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="url(#screen)"/>{blobs}{rows}'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="none" stroke="#ff2a4d" stroke-opacity=".5" stroke-width="3"/>'
            f'<rect x="{x + w * .45}" y="{y + h + 12}" width="{w * .1}" height="{h * .2}" fill="#10151b"/></g>')


def motif_ready_room():
    return (halo(620, 240) + monitor(-420, -70, 230, 130, 1, -3) + monitor(-150, -110, 300, 170, 2) + monitor(210, -70, 230, 130, 3, 3)
            + '<rect x="-500" y="108" width="1000" height="40" fill="#0a0d11"/><rect x="-500" y="104" width="1000" height="6" fill="#ff2a4d" opacity=".6"/>'
            '<rect x="-150" y="118" width="300" height="22" rx="8" fill="#0d1117" stroke="#ff2a4d" stroke-opacity=".6" stroke-width="3"/>'
            '<path d="M-440 100 Q-440 40 -380 40 Q-320 40 -320 100" fill="none" stroke="#161c23" stroke-width="16"/>'
            '<line x1="360" y1="-190" x2="360" y2="-70" stroke="#222a33" stroke-width="4"/>'
            '<path d="M320 -70 Q360 -120 400 -70 Z" fill="#12171d" stroke="#2a323c" stroke-width="4"/>'
            '<path d="M325 -66 L270 150 L450 150 L395 -66 Z" fill="#ff8a3a" opacity=".10" filter="url(#blur14)"/>')


def motif_games():
    r = random.Random(7)
    cases = ""
    for x, rot, tone in ((-470, -9, "#2a1015"), (-370, -3, "#321218"), (330, 4, "#3a141b"), (430, 10, "#2a1015")):
        cases += (f'<g transform="rotate({rot} {x + 55} 0)"><rect x="{x}" y="-125" width="110" height="250" rx="10" fill="{tone}" stroke="#ff2a4d" stroke-opacity=".6" stroke-width="4"/>'
                  f'<rect x="{x + 9}" y="-116" width="92" height="160" rx="6" fill="url(#screen)"/>'
                  + "".join(f'<ellipse cx="{x + r.uniform(25, 85):.0f}" cy="{r.uniform(-90, 20):.0f}" rx="{r.uniform(9, 24):.0f}" ry="{r.uniform(7, 18):.0f}" fill="#ff2a4d" opacity="{r.uniform(.3, .6):.2f}"/>' for _ in range(4))
                  + f'<rect x="{x + 14}" y="60" width="82" height="9" rx="4" fill="#ff5a68" opacity=".55"/></g>')
    pad = ('<g transform="translate(-270 -150)"><path d="M120 0 H400 Q470 0 500 90 L540 230 Q560 300 500 300 Q450 300 420 240 L390 190 H130 L100 240 Q70 300 20 300 Q-40 300 -20 230 L20 90 Q50 0 120 0Z" fill="url(#metal)" stroke="url(#red)" stroke-width="8"/>'
           '<circle cx="110" cy="95" r="50" fill="#080b0f" stroke="#ff2a4d" stroke-width="5"/><path d="M110 70 V120 M85 95 H135" stroke="#ff5a68" stroke-width="10" stroke-linecap="round"/>'
           '<circle cx="410" cy="55" r="17" fill="#e5162d"/><circle cx="455" cy="97" r="17" fill="#13bcf5"/><circle cx="365" cy="97" r="17" fill="#ffb46a"/><circle cx="410" cy="140" r="17" fill="#ff8d99"/>'
           '<circle cx="190" cy="150" r="30" fill="#080b0f" stroke="#ff2a4d" stroke-opacity=".7" stroke-width="4"/><circle cx="330" cy="150" r="30" fill="#080b0f" stroke="#ff2a4d" stroke-opacity=".7" stroke-width="4"/></g>')
    return halo(620, 240) + cases + pad


def motif_mods():
    s = 105
    piece = (f'<rect x="{-s}" y="{-s}" width="{2 * s}" height="{2 * s}" rx="18"/><circle cx="0" cy="{-s - 22}" r="40"/><circle cx="{s + 22}" cy="0" r="40"/>')
    cut = f'<circle cx="{-s}" cy="0" r="40"/><circle cx="0" cy="{s}" r="40"/>'
    cubes = ""
    r = random.Random(11)
    for x, y, q in ((-380, -90, 42), (-300, 100, 30), (330, -110, 36), (410, 70, 48), (-460, 20, 26), (240, 150, 26)):
        cubes += (f'<g opacity="{r.uniform(.55, .9):.2f}"><path d="M{x} {y - q} L{x + q} {y - q / 2} V{y + q / 2} L{x} {y + q} L{x - q} {y + q / 2} V{y - q / 2} Z" fill="#12171d" stroke="#13bcf5" stroke-width="3"/>'
                  f'<path d="M{x - q} {y - q / 2} L{x} {y} L{x + q} {y - q / 2} M{x} {y} V{y + q}" fill="none" stroke="#13bcf5" stroke-opacity=".7" stroke-width="2"/></g>')
    return (halo(500, 260) + f'<g filter="url(#blur40)" opacity=".5" fill="#ff2a4d">{piece}</g><g fill="url(#red)">{piece}</g><g fill="#0b0e13">{cut}</g>'
            f'<rect x="{-s + 12}" y="{-s + 12}" width="{2 * s - 24}" height="{2 * s - 24}" rx="12" fill="none" stroke="#ff8d99" stroke-opacity=".5" stroke-width="4"/>' + cubes)


def motif_old_files():
    r = random.Random(5)
    parts = [halo(560, 240, .45)]
    for y in (-95, 15, 125):
        parts.append(f'<rect x="-420" y="{y}" width="840" height="9" fill="#1b0c10"/><rect x="-420" y="{y}" width="840" height="3" fill="#ff2a4d" opacity=".5"/>')
        x = -410
        while x < 360:
            bw, bh = r.uniform(48, 84), r.uniform(60, 96)
            tone = r.choice(("#2a1015", "#321218", "#1c0b0f", "#3a141b"))
            parts.append(f'<g opacity="{r.uniform(.75, 1):.2f}"><rect x="{x:.0f}" y="{y - bh:.0f}" width="{bw:.0f}" height="{bh:.0f}" rx="4" fill="{tone}" stroke="#ff2a4d" stroke-opacity=".35" stroke-width="3"/>'
                         f'<rect x="{x + bw * .2:.0f}" y="{y - bh * .62:.0f}" width="{bw * .6:.0f}" height="{bh * .22:.0f}" rx="3" fill="#0a0709" stroke="#ff8d99" stroke-opacity=".4" stroke-width="2"/></g>')
            x += bw + r.uniform(6, 16)
    parts.append('<circle cx="-470" cy="-130" r="44" fill="#10151b" stroke="#ff2a4d" stroke-width="6"/><path d="M-470 -130 V-160 M-470 -130 L-448 -118" stroke="#ff8d99" stroke-width="6" stroke-linecap="round"/>')
    return "".join(parts)


def motif_other_storage():
    parts = [halo(520, 250)]
    for i, y in enumerate((-115, -10, 95)):
        parts.append(f'<path d="M-170 {y} v62 a170 40 0 0 0 340 0 v-62" fill="url(#metal)" stroke="url(#red)" stroke-width="6"/>'
                     f'<ellipse cx="0" cy="{y}" rx="170" ry="40" fill="#12171d" stroke="url(#red)" stroke-width="6"/>'
                     f'<circle cx="120" cy="{y + 48}" r="7" fill="{"#30d76b" if i != 1 else "#ffb46a"}"/><rect x="-120" y="{y + 44}" width="150" height="8" rx="4" fill="#ff5a68" opacity=".45"/>')
    for x in (-340, 330):
        parts.append(f'<rect x="{x - 36}" y="-40" width="72" height="110" rx="10" fill="url(#metal)" stroke="#ff2a4d" stroke-opacity=".5" stroke-width="4"/><circle cx="{x}" cy="15" r="20" fill="#080b0f" stroke="#13bcf5" stroke-width="3"/>')
    return "".join(parts)


def motif_captures():
    return (halo(520, 250) + '<rect x="-220" y="-95" width="440" height="230" rx="34" fill="url(#metal)" stroke="url(#red)" stroke-width="8"/>'
            '<path d="M-90 -95 L-60 -140 H60 L90 -95 Z" fill="#12171d" stroke="url(#red)" stroke-width="6"/>'
            '<circle cx="0" cy="22" r="96" fill="#07090d" stroke="#ff2a4d" stroke-width="7"/><circle cx="0" cy="22" r="64" fill="url(#screen)" stroke="#ff8d99" stroke-opacity=".5" stroke-width="4"/>'
            '<circle cx="-22" cy="0" r="18" fill="#ff8d99" opacity=".5"/><circle cx="170" cy="-58" r="12" fill="#e5162d"/>'
            '<path d="M-420 -150 h-60 v60 M-420 160 h-60 v-60 M420 -150 h60 v60 M420 160 h60 v-60" fill="none" stroke="#13bcf5" stroke-width="6" opacity=".7"/>')


def motif_graveyard():
    parts = [halo(560, 250, .4), '<circle cx="0" cy="-60" r="120" fill="#ffb4b4" opacity=".08"/>']
    for x, s in ((-300, .8), (-120, 1.0), (140, 1.15), (330, .85)):
        parts.append(f'<g transform="translate({x} {90 - 20 * s}) scale({s})"><path d="M-60 90 V-30 Q-60 -105 0 -105 Q60 -105 60 -30 V90 Z" fill="#0d1117" stroke="url(#red)" stroke-width="7"/>'
                     '<path d="M0 -62 V10 M-26 -34 H26" stroke="#ff8d99" stroke-opacity=".6" stroke-width="8" stroke-linecap="round"/></g>')
    parts.append('<ellipse cx="0" cy="112" rx="560" ry="30" fill="#1a0a0e" opacity=".9"/><ellipse cx="0" cy="104" rx="500" ry="26" fill="#ff2a4d" opacity=".12" filter="url(#blur14)"/>')
    return "".join(parts)


def motif_dna():
    pts1 = [(x, 85 * sin(x / 62)) for x in range(-400, 401, 8)]
    d = lambda pts: "M" + " L".join(f"{x} {y:.1f}" for x, y in pts)
    rungs = "".join(f'<line x1="{x}" y1="{85 * sin(x / 62):.1f}" x2="{x}" y2="{-85 * sin(x / 62):.1f}" stroke="#ff8d99" stroke-opacity=".35" stroke-width="3"/>' for x in range(-390, 391, 26))
    return (halo(560, 250) + rungs + f'<path d="{d(pts1)}" fill="none" stroke="url(#red)" stroke-width="14" stroke-linecap="round"/>'
            f'<path d="{d([(x, -y) for x, y in pts1])}" fill="none" stroke="#13bcf5" stroke-width="14" stroke-linecap="round" opacity=".85"/>'
            + "".join(f'<circle cx="{x}" cy="{85 * sin(x / 62):.1f}" r="9" fill="#ff8d99"/>' for x in range(-390, 391, 78)))


def motif_undo():
    return (halo(520, 250) + '<path d="M150 0 A150 150 0 1 1 -60 -138" fill="none" stroke="url(#red)" stroke-width="34" stroke-linecap="round"/>'
            '<path d="M-130 -215 L-40 -150 L-135 -85 Z" fill="#ff5a68"/>'
            '<path d="M0 0 V-70 M0 0 L52 30" stroke="#ff8d99" stroke-width="9" stroke-linecap="round"/><circle cx="0" cy="0" r="12" fill="#ff8d99"/>'
            '<path d="M-300 0 l-60 -44 v88 Z M-390 0 l-60 -44 v88 Z M300 0 l60 -44 v88 Z" fill="#13bcf5" opacity=".55"/>')


def motif_settings():
    return (halo(520, 250) + f'<g transform="translate(-70 0)"><path d="{gear(130, 12)}" fill="url(#metal)" stroke="url(#red)" stroke-width="8"/><circle r="52" fill="#07090d" stroke="#ff8d99" stroke-opacity=".5" stroke-width="5"/></g>'
            f'<g transform="translate(180 -60) rotate(15)"><path d="{gear(76, 9)}" fill="url(#metal)" stroke="#13bcf5" stroke-width="6"/><circle r="30" fill="#07090d" stroke="#13bcf5" stroke-opacity=".6" stroke-width="4"/></g>'
            f'<g transform="translate(235 105) rotate(8)"><path d="{gear(48, 8)}" fill="url(#metal)" stroke="url(#red)" stroke-width="5"/><circle r="18" fill="#07090d"/></g>')


def motif_assistant():
    nodes = [(-350, -90), (-300, 90), (330, -110), (380, 60), (-420, 0), (260, 140)]
    lines = "".join(f'<line x1="{x}" y1="{y}" x2="{-x * .2:.0f}" y2="0" stroke="#13bcf5" stroke-opacity=".35" stroke-width="2.5"/><circle cx="{x}" cy="{y}" r="11" fill="#13bcf5" opacity=".8"/>' for x, y in nodes)
    return (halo(520, 250) + lines + '<path d="M-200 -120 H120 Q160 -120 160 -80 V20 Q160 60 120 60 H-60 L-130 120 L-120 60 H-200 Q-240 60 -240 20 V-80 Q-240 -120 -200 -120 Z" fill="url(#metal)" stroke="url(#red)" stroke-width="8"/>'
            '<circle cx="-120" cy="-30" r="14" fill="#ff8d99"/><circle cx="-40" cy="-30" r="14" fill="#ff8d99"/><circle cx="40" cy="-30" r="14" fill="#ff8d99"/>'
            '<path d="M100 20 H220 Q260 20 260 60 V130 Q260 160 230 160 H220 L225 200 L170 160 H120 Q90 160 90 130 V60" fill="#0d1117" stroke="#13bcf5" stroke-opacity=".8" stroke-width="6" transform="translate(30 10)"/>')


def motif_more_tools():
    nut = hexagon(.55)
    return (halo(520, 250) + f'<g transform="translate(-170 20)"><path d="{nut}" fill="url(#metal)" stroke="url(#red)" stroke-width="8"/><circle r="52" fill="#07090d" stroke="#ff8d99" stroke-opacity=".5" stroke-width="5"/></g>'
            '<g transform="translate(120 -10) rotate(-38)"><rect x="-210" y="-22" width="420" height="44" rx="22" fill="url(#metal)" stroke="url(#red)" stroke-width="7"/>'
            '<circle cx="-215" cy="0" r="62" fill="url(#metal)" stroke="url(#red)" stroke-width="7"/><rect x="-290" y="-22" width="70" height="44" fill="#0b0e13"/></g>'
            '<g transform="translate(220 90) rotate(32)"><rect x="-8" y="-170" width="16" height="130" rx="4" fill="#9aa5b1" opacity=".8"/><rect x="-22" y="-40" width="44" height="170" rx="16" fill="#e5162d" stroke="#ff8d99" stroke-opacity=".5" stroke-width="3"/></g>')


MOTIFS = {
    "overview": motif_overview, "ready_room": motif_ready_room, "games": motif_games, "mods": motif_mods,
    "old_files": motif_old_files, "other_storage": motif_other_storage, "captures": motif_captures,
    "graveyard": motif_graveyard, "dna": motif_dna, "undo": motif_undo, "settings": motif_settings,
    "assistant": motif_assistant, "more_tools": motif_more_tools,
}


def picture(slug, seed):
    body = atmosphere(seed) + f'<g transform="translate({CX} {CY})">{MOTIFS[slug]()}</g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'{DEFS}{body}</svg>')


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
    for i, name in enumerate(MOTIFS):
        render(name, 20 + i)
