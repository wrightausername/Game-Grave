"""Generate the HD banner art for Ready Room, Mods and Old Files. Run: python3 tools/make_banner_art.py
Needs rsvg-convert. Deterministic. Outputs opaque PNGs into gg_desktop/assets/brand/."""
from pathlib import Path
import random
import subprocess

OUT = Path(__file__).resolve().parents[1] / "gg_desktop" / "assets" / "brand"
G = "M170 46 H82 Q24 46 24 104 V134 Q24 192 82 192 H120 Q168 192 168 144 V114 H102"

DEFS = f"""
<defs>
 <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0b0f15"/><stop offset="1" stop-color="#05080b"/></linearGradient>
 <radialGradient id="haze" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ff2a4d" stop-opacity=".55"/><stop offset=".55" stop-color="#b3112b" stop-opacity=".18"/><stop offset="1" stop-color="#b3112b" stop-opacity="0"/></radialGradient>
 <radialGradient id="cyan" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#13bcf5" stop-opacity=".45"/><stop offset="1" stop-color="#13bcf5" stop-opacity="0"/></radialGradient>
 <linearGradient id="red" x1="0" y1="0" x2=".35" y2="1"><stop offset="0" stop-color="#ff5a68"/><stop offset=".5" stop-color="#e5162d"/><stop offset="1" stop-color="#8a0c1c"/></linearGradient>
 <linearGradient id="screen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3a0610"/><stop offset="1" stop-color="#12050a"/></linearGradient>
 <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#232a33"/><stop offset="1" stop-color="#0c1015"/></linearGradient>
 <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1a0a0e"/><stop offset="1" stop-color="#030507"/></linearGradient>
 <filter id="blur40" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="40"/></filter>
 <filter id="blur14" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>
 <filter id="blur4" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter>
 <filter id="fog" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".0028 .006" numOctaves="4" seed="9"/><feColorMatrix values="0 0 0 0 .75  0 0 0 0 .08  0 0 0 0 .14  0 0 0 .9 -.28"/></filter>
 <symbol id="mark" viewBox="0 0 400 280"><g transform="translate(10 6) skewX(-13)"><path d="{G}" fill="none" stroke="url(#red)" stroke-width="42"/></g><g transform="translate(130 78) skewX(-13)"><path d="{G}" fill="none" stroke="#04070a" stroke-width="58"/><path d="{G}" fill="none" stroke="url(#red)" stroke-width="42"/></g></symbol>
</defs>"""


def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{DEFS}{body}</svg>'


def monitor(x, y, w, h, seed, tilt=0):
    r = random.Random(seed)
    blobs = "".join(
        f'<ellipse cx="{x + r.uniform(.12, .88) * w:.0f}" cy="{y + r.uniform(.2, .8) * h:.0f}" rx="{r.uniform(.04, .16) * w:.0f}" '
        f'ry="{r.uniform(.04, .12) * h:.0f}" fill="#ff2a4d" opacity="{r.uniform(.25, .6):.2f}"/>' for _ in range(9))
    rows = "".join(f'<rect x="{x + w * .07:.0f}" y="{y + h * (.12 + i * .1):.0f}" width="{w * r.uniform(.2, .6):.0f}" height="{h * .035:.0f}" rx="3" fill="#ff5a68" opacity=".5"/>' for i in range(6))
    return (f'<g transform="rotate({tilt} {x + w / 2} {y + h / 2})">'
            f'<rect x="{x - 14}" y="{y - 14}" width="{w + 28}" height="{h + 28}" rx="14" fill="url(#metal)"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="url(#screen)"/>{blobs}{rows}'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="none" stroke="#ff2a4d" stroke-opacity=".5" stroke-width="3"/>'
            f'<rect x="{x + w * .45}" y="{y + h + 14}" width="{w * .1}" height="{h * .2}" fill="#10151b"/>'
            f'<rect x="{x + w * .3}" y="{y + h + h * .2 + 10}" width="{w * .4}" height="14" rx="7" fill="#161c23"/></g>'), 0


def ready_room():
    w, h = 4000, 600
    parts = [f'<rect width="{w}" height="{h}" fill="url(#wall)"/>',
             f'<ellipse cx="2900" cy="230" rx="1100" ry="420" fill="url(#haze)"/>',
             '<rect width="4000" height="600" filter="url(#fog)" opacity=".5"/>',
             # window with red mist behind the desk
             '<rect x="3480" y="60" width="420" height="300" rx="10" fill="#1a0509" stroke="#2a0a10" stroke-width="10"/>'
             '<rect x="3492" y="72" width="396" height="276" fill="#ff2a4d" opacity=".25" filter="url(#blur14)"/>',
             # lamp
             '<line x1="2680" y1="0" x2="2680" y2="215" stroke="#222a33" stroke-width="6"/>'
             '<path d="M2610 290 Q2680 190 2750 290 Z" fill="#12171d" stroke="#2a323c" stroke-width="5"/>'
             '<ellipse cx="2680" cy="300" rx="70" ry="14" fill="#ffb46a" filter="url(#blur4)"/>'
             '<path d="M2615 300 L2400 600 L2960 600 L2745 300 Z" fill="#ff8a3a" opacity=".12" filter="url(#blur14)"/>',
             # flag
             '<path d="M3560 120 H3860 V470 L3710 430 L3560 470 Z" fill="#7d0a19" stroke="#c91a30" stroke-width="6"/>'
             '<use xlink:href="#mark" x="3590" y="210" width="240" height="168"/>',
             # desk
             '<rect x="900" y="540" width="3100" height="60" fill="#0a0d11"/><rect x="900" y="536" width="3100" height="8" fill="#ff2a4d" opacity=".55"/>'
             '<rect x="900" y="544" width="3100" height="30" fill="#ff2a4d" opacity=".10" filter="url(#blur4)"/>']
    m1, _ = monitor(1450, 235, 440, 250, 1, -3)
    m2, _ = monitor(2010, 205, 560, 300, 2)
    m3, _ = monitor(2690, 235, 440, 250, 3, 3)
    parts += [m1, m2, m3]
    # keyboard, mouse, headset
    parts.append('<rect x="2020" y="545" width="520" height="38" rx="10" fill="#0d1117" stroke="#ff2a4d" stroke-opacity=".6" stroke-width="3"/>'
                 + "".join(f'<rect x="{2040 + i * 31}" y="553" width="24" height="9" rx="2" fill="#ff5a68" opacity=".55"/>' for i in range(15))
                 + '<ellipse cx="2680" cy="565" rx="30" ry="14" fill="#0d1117" stroke="#ff2a4d" stroke-opacity=".6" stroke-width="3"/>'
                 '<path d="M1500 560 Q1500 470 1590 470 Q1680 470 1680 560" fill="none" stroke="#161c23" stroke-width="22"/>'
                 '<rect x="1478" y="530" width="40" height="60" rx="14" fill="#12171d" stroke="#ff2a4d" stroke-opacity=".5" stroke-width="3"/>'
                 '<rect x="1662" y="530" width="40" height="60" rx="14" fill="#12171d" stroke="#ff2a4d" stroke-opacity=".5" stroke-width="3"/>')
    # chair
    parts.append('<g><path d="M3190 600 V330 Q3190 190 3330 190 Q3470 190 3470 330 V600 Z" fill="#0d1117" stroke="#e5162d" stroke-width="10"/>'
                 '<path d="M3230 600 V345 Q3230 235 3330 235 Q3430 235 3430 345 V600" fill="none" stroke="#e5162d" stroke-opacity=".5" stroke-width="5"/>'
                 '<rect x="3290" y="150" width="80" height="60" rx="20" fill="#0d1117" stroke="#e5162d" stroke-width="8"/>'
                 '<use xlink:href="#mark" x="3250" y="300" width="160" height="112"/></g>')
    parts.append('<rect width="4000" height="600" fill="#05080b" opacity="0" />')
    return svg(w, h, "".join(parts))


def mods():
    w, h = 1850, 550
    r = random.Random(4)
    parts = ['<rect x="-570" width="2420" height="550" fill="url(#wall)"/>',
             '<ellipse cx="1280" cy="260" rx="720" ry="360" fill="url(#haze)"/>',
             '<ellipse cx="1600" cy="380" rx="420" ry="260" fill="url(#cyan)" opacity=".7"/>',
             '<rect x="-570" width="2420" height="550" filter="url(#fog)" opacity=".4"/>']
    # circuit traces
    for i in range(18):
        y = 60 + i * 26
        x0 = r.uniform(520, 1000)
        pts = [(x0, y)]
        x = x0
        for _ in range(r.randint(2, 4)):
            x += r.uniform(80, 220)
            pts.append((x, pts[-1][1]))
            y2 = pts[-1][1] + r.choice((-1, 1)) * r.uniform(20, 60)
            pts.append((x + r.uniform(20, 60), y2))
            x = pts[-1][0]
        d = "M" + " L".join(f"{px:.0f} {py:.0f}" for px, py in pts)
        tone = "#13bcf5" if i % 5 == 0 else "#ff2a4d"
        parts.append(f'<path d="{d}" fill="none" stroke="{tone}" stroke-width="3" opacity=".38"/>'
                     f'<circle cx="{pts[-1][0]:.0f}" cy="{pts[-1][1]:.0f}" r="7" fill="{tone}" opacity=".7"/>')
    # big puzzle piece
    cx, cy, s = 1250, 285, 190
    piece = (f'<rect x="{cx - s}" y="{cy - s}" width="{2 * s}" height="{2 * s}" rx="26"/>'
             f'<circle cx="{cx}" cy="{cy - s - 34}" r="64"/><circle cx="{cx + s + 34}" cy="{cy}" r="64"/>')
    cutouts = f'<circle cx="{cx - s}" cy="{cy}" r="64"/><circle cx="{cx}" cy="{cy + s}" r="64"/>'
    parts.append(f'<g filter="url(#blur40)" opacity=".55" fill="#ff2a4d">{piece}</g>'
                 f'<g fill="url(#red)">{piece}</g><g fill="#0a0d12">{cutouts}</g>'
                 f'<g fill="none" stroke="#ff8d99" stroke-opacity=".55" stroke-width="5"><rect x="{cx - s + 14}" y="{cy - s + 14}" width="{2 * s - 28}" height="{2 * s - 28}" rx="18"/></g>')
    # floating cubes and hexes
    for i in range(7):
        x, y, q = r.uniform(620, 1780), r.uniform(60, 470), r.uniform(26, 56)
        if 1020 < x < 1520 and 70 < y < 500:
            continue
        parts.append(f'<g opacity="{r.uniform(.45, .85):.2f}"><path d="M{x} {y - q} L{x + q} {y - q / 2} V{y + q / 2} L{x} {y + q} L{x - q} {y + q / 2} V{y - q / 2} Z" fill="#12171d" stroke="#13bcf5" stroke-width="3"/>'
                     f'<path d="M{x - q} {y - q / 2} L{x} {y} L{x + q} {y - q / 2} M{x} {y} V{y + q}" fill="none" stroke="#13bcf5" stroke-opacity=".7" stroke-width="2"/></g>')
    return svg(2420, h, '<g transform="translate(570 0)">' + "".join(parts) + "</g>")


def old_files():
    w, h = 1850, 550
    r = random.Random(5)
    parts = ['<rect x="-570" width="2420" height="550" fill="url(#wall)"/>',
             '<ellipse cx="1150" cy="200" rx="760" ry="340" fill="url(#haze)"/>',
             '<rect x="-570" width="2420" height="550" filter="url(#fog)" opacity=".45"/>']
    # shelves of archive boxes
    for shelf, y in enumerate((170, 330, 490)):
        parts.append(f'<rect x="560" y="{y}" width="1290" height="12" fill="#1b0c10"/><rect x="560" y="{y}" width="1290" height="3" fill="#ff2a4d" opacity=".45"/>')
        x = 580 + r.uniform(0, 40)
        while x < 1780:
            bw, bh = r.uniform(70, 130), r.uniform(90, 140)
            tone = r.choice(("#2a1015", "#321218", "#1c0b0f", "#3a141b"))
            parts.append(f'<g opacity="{r.uniform(.75, 1):.2f}"><rect x="{x:.0f}" y="{y - bh:.0f}" width="{bw:.0f}" height="{bh:.0f}" rx="5" fill="{tone}" stroke="#ff2a4d" stroke-opacity=".35" stroke-width="3"/>'
                         f'<rect x="{x + bw * .2:.0f}" y="{y - bh * .62:.0f}" width="{bw * .6:.0f}" height="{bh * .22:.0f}" rx="3" fill="#0a0709" stroke="#ff8d99" stroke-opacity=".4" stroke-width="2"/>'
                         f'<rect x="{x + bw * .3:.0f}" y="{y - bh * .55:.0f}" width="{bw * .4:.0f}" height="6" rx="3" fill="#ff5a68" opacity=".5"/></g>')
            x += bw + r.uniform(6, 24)
    # a lone glowing folder and a clock
    parts.append('<g transform="translate(1180 120)"><path d="M0 40 H70 L90 70 H300 V250 H0 Z" fill="url(#red)" opacity=".92"/><path d="M0 100 H300 V250 H0 Z" fill="#7d0a19" opacity=".9"/>'
                 '<rect x="0" y="100" width="300" height="5" fill="#ff8d99" opacity=".5"/></g>'
                 '<g filter="url(#blur40)" opacity=".5"><rect x="1180" y="160" width="300" height="210" fill="#ff2a4d"/></g>')
    parts.append('<circle cx="760" cy="90" r="62" fill="#10151b" stroke="#ff2a4d" stroke-width="7"/><path d="M760 90 V50 M760 90 L790 108" stroke="#ff8d99" stroke-width="7" stroke-linecap="round"/>')
    return svg(2420, h, '<g transform="translate(570 0)">' + "".join(parts) + "</g>")


def render(name, text, width):
    src = OUT / (name + ".svg")
    src.write_text(text)
    png = OUT / (name + ".png")
    subprocess.run(["rsvg-convert", "-w", str(width), str(src), "-o", str(png)], check=True)
    src.unlink()
    print("wrote", png)


if __name__ == "__main__":
    render("banner_ready_room", ready_room(), 4000)
    render("banner_mods", mods(), 2420)
    render("banner_old_files", old_files(), 2420)
