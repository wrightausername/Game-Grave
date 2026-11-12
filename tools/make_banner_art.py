"""Generate the panoramic HD header art, one per tab. Run: python3 tools/make_banner_art.py
Needs rsvg-convert and Pillow. Deterministic. Writes gg_desktop/assets/brand/banner_<tab>.jpg (6000x500).

Owner direction (2026-11-11): "still hd quality abstract but keep it computer and video games themed instead of just random
shapes". Each tab gets a cluster of recognisable gaming and PC objects drawn as glowing neon line art (controllers, keyboard
keys, graphics cards, chips, cartridges, floppies, pixel hearts, cameras ...) over a shared retro perspective grid with pixel
particles. No characters, no logos, no brand marks, no words.

The header crops the picture from the right and centres it vertically, so the objects sit in the right two thirds and in the
middle band; the left stays calm behind the page title. The grid floor is mirrored into a ceiling so the picture stays
balanced top to bottom.
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
CX = 4700


# ---------------------------------------------------------------- icon library (100 x 100 box, outline style)
def _p(d, c, sw, extra=""):
    fill = "" if "fill=" in extra else 'fill="none" '
    return f'<path d="{d}" {fill}stroke="{c}" stroke-width="{sw:.2f}" stroke-linecap="round" stroke-linejoin="round" {extra}/>'


def _r(x, y, w, h, rx, c, sw, fill="none", op=1.0):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" fill-opacity="{op}" stroke="{c}" '
            f'stroke-width="{sw:.2f}"/>')


def _c(x, y, r, c, sw, fill="none", op=1.0):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" fill-opacity="{op}" stroke="{c}" stroke-width="{sw:.2f}"/>'


def gamepad(c, a, sw):
    body = ("M22 34 C30 28 42 30 50 30 C58 30 70 28 78 34 C88 41 94 66 90 74 C86 82 76 80 70 70 C66 64 60 62 50 62 "
            "C40 62 34 64 30 70 C24 80 14 82 10 74 C6 66 12 41 22 34 Z")
    out = [_p(body, c, sw)]
    out.append(_p("M26 46 h10 M31 41 v10", c, sw))                                     # d-pad
    for x, y in ((70, 41), (76, 47), (64, 47), (70, 53)):
        out.append(_c(x, y, 2.6, a, sw * .8, a, .35))
    out += [_c(40, 55, 4.5, c, sw * .8), _c(60, 55, 4.5, c, sw * .8)]
    return "".join(out)


def keycaps(c, a, sw):
    out = []
    for x, y, letter, hot in ((38, 22, "W", True), (18, 50, "A", True), (38, 50, "S", True), (58, 50, "D", True),
                              (78, 50, "", False), (-2, 50, "", False)):
        out.append(_r(x, y, 22, 22, 4, a if hot else c, sw, a if hot else "none", .18 if hot else 1))
        if letter:
            out.append(f'<text x="{x + 11}" y="{y + 16}" text-anchor="middle" font-family="DejaVu Sans Mono" '
                       f'font-weight="bold" font-size="13" fill="{a}">{letter}</text>')
    out.append(_r(18, 78, 62, 14, 4, c, sw))                                           # space bar
    return "".join(out)


def mouse(c, a, sw):
    return (_p("M50 14 C70 14 76 30 76 50 C76 76 66 88 50 88 C34 88 24 76 24 50 C24 30 30 14 50 14 Z", c, sw)
            + _p("M50 14 V42 M24 42 H76", c, sw * .8) + _r(47, 22, 6, 12, 3, a, sw * .8, a, .5))


def headset(c, a, sw):
    return (_p("M18 62 C18 30 32 14 50 14 C68 14 82 30 82 62", c, sw)
            + _r(10, 56, 16, 28, 6, c, sw, a, .2) + _r(74, 56, 16, 28, 6, c, sw, a, .2)
            + _p("M18 80 C22 92 36 94 46 92", c, sw * .8) + _c(48, 92, 3, a, sw * .8, a, .6))


def monitor(c, a, sw):
    out = [_r(8, 14, 84, 54, 5, c, sw), _p("M42 68 L38 82 H62 L58 68 M30 84 H70", c, sw)]
    for i, wdt in enumerate((30, 22, 38)):
        out.append(_r(16, 22 + i * 9, wdt, 5, 2, a, sw * .6, a, .45))
    out.append(_c(74, 42, 11, a, sw * .8))
    out.append(_p("M74 31 V53 M63 42 H85", a, sw * .6))
    return "".join(out)


def cpu(c, a, sw):
    out = [_r(22, 22, 56, 56, 6, c, sw), _r(36, 36, 28, 28, 3, a, sw, a, .25)]
    for k in range(5):
        p = 30 + k * 10
        out.append(_p(f"M{p} 22 V10 M{p} 78 V90 M22 {p} H10 M78 {p} H90", c, sw * .7))
    return "".join(out)


def gpu(c, a, sw):
    out = [_r(4, 26, 92, 46, 6, c, sw), _p("M10 72 V84 H40 V72 M4 40 H0", c, sw * .8)]
    for fx in (28, 68):
        out.append(_c(fx, 49, 16, c, sw * .9))
        for k in range(6):
            ang = k * math.pi / 3
            out.append(_p(f"M{fx} 49 Q{fx + 10 * math.cos(ang + .7):.1f} {49 + 10 * math.sin(ang + .7):.1f} "
                          f"{fx + 14 * math.cos(ang):.1f} {49 + 14 * math.sin(ang):.1f}", a, sw * .55))
        out.append(_c(fx, 49, 3.5, a, sw * .6, a, .7))
    out.append(_r(80, 30, 12, 4, 2, a, sw * .5, a, .8))
    return "".join(out)


def ram(c, a, sw):
    out = [_r(4, 34, 92, 30, 3, c, sw), _p("M48 64 v6 M52 64 v6", c, sw * .6)]
    for k in range(7):
        out.append(_r(10 + k * 12, 40, 8, 14, 1.5, a, sw * .55, a, .3))
    for k in range(20):
        out.append(_p(f"M{7 + k * 4.5:.1f} 64 v4", c, sw * .4))
    return "".join(out)


def ssd(c, a, sw):
    out = [_r(6, 38, 88, 24, 3, c, sw), _p("M6 44 h-4 M6 56 h-4", c, sw * .6)]
    for k, wdt in enumerate((18, 18, 18)):
        out.append(_r(30 + k * 21, 43, wdt, 14, 2, a, sw * .55, a, .3))
    out.append(_r(12, 45, 12, 10, 2, c, sw * .55))
    return "".join(out)


def hdd(c, a, sw):
    return (_r(14, 8, 72, 84, 6, c, sw) + _c(48, 44, 26, c, sw * .9) + _c(48, 44, 6, a, sw * .7, a, .5)
            + _p("M76 80 L60 52", a, sw) + _c(76, 80, 4, a, sw * .7))


def floppy(c, a, sw):
    return (_p("M12 10 H76 L90 24 V90 H12 Z", c, sw) + _r(28, 10, 40, 26, 2, c, sw * .8)
            + _r(54, 14, 8, 18, 1, a, sw * .6, a, .6) + _r(24, 54, 52, 32, 3, a, sw * .8, a, .15)
            + _p("M30 64 H70 M30 74 H62", a, sw * .5))


def folder(c, a, sw):
    return (_p("M8 24 H40 L48 32 H92 V84 H8 Z", c, sw) + _p("M8 40 H92", c, sw * .6)
            + _r(20, 50, 22, 26, 2, a, sw * .6, a, .2) + _r(48, 50, 22, 26, 2, a, sw * .6, a, .2))


def cartridge(c, a, sw):
    return (_p("M14 10 H86 V72 L80 78 V90 H20 V78 L14 72 Z", c, sw) + _r(26, 20, 48, 34, 3, a, sw * .8, a, .2)
            + "".join(_p(f"M{28 + k * 6} 82 v8", c, sw * .5) for k in range(8)) + _p("M26 62 H74", c, sw * .5))


def disc(c, a, sw):
    return (_c(50, 50, 40, c, sw) + _c(50, 50, 9, c, sw * .8) + _c(50, 50, 3, a, sw * .6, a, .8)
            + _p("M50 18 A32 32 0 0 1 80 40", a, sw * .7) + _p("M50 26 A24 24 0 0 1 72 42", a, sw * .5))


def pixel_heart(c, a, sw, empty=False):
    rows = ["0110110", "1111111", "1111111", "0111110", "0011100", "0001000"]
    out = []
    for y, row_ in enumerate(rows):
        for x, bit in enumerate(row_):
            if bit == "1":
                out.append(_r(8 + x * 12, 16 + y * 12, 11, 11, 1, a, sw * .3, "none" if empty else a, .55))
    return "".join(out)


def coin(c, a, sw):
    return _c(50, 50, 30, a, sw, a, .15) + _c(50, 50, 22, a, sw * .7) + _p("M50 36 V64", a, sw * 1.2)


def trophy(c, a, sw):
    return (_p("M30 14 H70 V36 C70 52 60 60 50 60 C40 60 30 52 30 36 Z", c, sw)
            + _p("M30 22 H16 C16 36 22 42 32 44 M70 22 H84 C84 36 78 42 68 44", c, sw * .8)
            + _p("M50 60 V74 M34 86 H66 L62 74 H38 Z", c, sw) + _p("M44 28 l6 -6 l6 6 l-6 12 z", a, sw * .6))


def crosshair(c, a, sw):
    return (_c(50, 50, 34, c, sw) + _c(50, 50, 18, c, sw * .7) + _c(50, 50, 3, a, sw, a, .9)
            + _p("M50 4 V30 M50 70 V96 M4 50 H30 M70 50 H96", a, sw * .8))


def camera(c, a, sw):
    return (_r(8, 28, 84, 56, 8, c, sw) + _p("M32 28 L38 16 H62 L68 28", c, sw) + _c(50, 56, 18, c, sw)
            + _c(50, 56, 9, a, sw * .7, a, .3) + _c(78, 38, 4, "#ff2a4d", sw * .6, "#ff2a4d", .9))


def filmstrip(c, a, sw):
    out = [_r(4, 24, 92, 52, 2, c, sw)]
    for k in range(8):
        out += [_r(8 + k * 11.5, 28, 6, 6, 1, c, sw * .4), _r(8 + k * 11.5, 66, 6, 6, 1, c, sw * .4)]
    for k in range(3):
        out.append(_r(10 + k * 29, 38, 24, 24, 2, a, sw * .6, a, .2))
    return "".join(out)


def tombstone(c, a, sw):
    return (_p("M22 92 V40 C22 20 36 10 50 10 C64 10 78 20 78 40 V92 Z", c, sw) + _p("M10 92 H90", c, sw)
            + _r(44, 26, 12, 34, 1, a, sw * .5, a, .35) + _r(34, 36, 32, 12, 1, a, sw * .5, a, .35))


def gear(c, a, sw):
    teeth = []
    for k in range(10):
        ang = k * math.pi / 5
        x, y = 50 + 36 * math.cos(ang), 50 + 36 * math.sin(ang)
        teeth.append(f'<rect x="{x - 6:.1f}" y="{y - 6:.1f}" width="12" height="12" rx="2" fill="none" stroke="{c}" '
                     f'stroke-width="{sw * .7:.2f}" transform="rotate({math.degrees(ang):.0f} {x:.1f} {y:.1f})"/>')
    return _c(50, 50, 30, c, sw) + "".join(teeth) + _c(50, 50, 11, a, sw * .8, a, .3)


def sliders(c, a, sw):
    out = []
    for k, pos in enumerate((30, 66, 44)):
        x = 20 + k * 30
        out += [_p(f"M{x} 10 V90", c, sw * .7), _r(x - 9, pos, 18, 12, 3, a, sw * .8, a, .35)]
    return "".join(out)


def toggle(c, a, sw):
    return _r(10, 32, 80, 36, 18, a, sw, a, .2) + _c(72, 50, 13, a, sw, a, .7)


def chat(c, a, sw):
    return (_p("M10 16 H70 V56 H34 L20 70 V56 H10 Z", c, sw)
            + _p("M44 44 H90 V80 H80 V92 L68 80 H44 Z", a, sw, f'fill="{a}" fill-opacity=".12"')
            + "".join(_c(56 + k * 11, 62, 2.6, a, sw * .6, a, .9) for k in range(3)))


def network(c, a, sw):
    nodes = [(14, 30), (14, 70), (50, 16), (50, 50), (50, 84), (86, 34), (86, 66)]
    out = []
    for i, (x1, y1) in enumerate(nodes[:2]):
        for x2, y2 in nodes[2:5]:
            out.append(_p(f"M{x1} {y1} L{x2} {y2}", c, sw * .45))
    for x1, y1 in nodes[2:5]:
        for x2, y2 in nodes[5:]:
            out.append(_p(f"M{x1} {y1} L{x2} {y2}", c, sw * .45))
    for x, y in nodes:
        out.append(_c(x, y, 6, a, sw * .7, a, .4))
    return "".join(out)


def wrench(c, a, sw):
    return (_p("M70 10 C58 10 50 20 52 32 L14 70 C8 76 12 88 18 88 C24 88 26 86 30 82 L68 44 C80 46 90 38 90 26 "
               "L80 36 L68 32 L64 20 Z", c, sw) + _c(20, 80, 3, a, sw * .6, a, .8))


def screwdriver(c, a, sw):
    return (_r(58, 8, 16, 40, 6, a, sw, a, .25) + _p("M66 48 V84 M60 84 H72 L66 94 Z", c, sw)
            + _p("M62 18 H70 M62 28 H70 M62 38 H70", a, sw * .5))


def puzzle(c, a, sw):
    return _p("M14 30 H36 C34 22 38 14 46 14 C54 14 58 22 56 30 H80 V52 C88 50 94 54 94 62 C94 70 88 74 80 72 V90 "
              "H56 C58 82 54 76 46 76 C38 76 34 82 36 90 H14 V70 C22 72 26 66 26 60 C26 54 22 48 14 50 Z", c, sw,
              f'fill="{a}" fill-opacity=".10"')


def cube(c, a, sw):
    return (_p("M50 10 L86 30 V70 L50 90 L14 70 V30 Z", c, sw) + _p("M14 30 L50 50 L86 30 M50 50 V90", c, sw * .8)
            + _p("M50 50 L86 30 V70 L50 90 Z", a, sw * .3, f'fill="{a}" fill-opacity=".14"'))


def cassette(c, a, sw):
    return (_r(6, 22, 88, 58, 6, c, sw) + _r(20, 32, 60, 26, 3, a, sw * .7, a, .15) + _c(36, 45, 7, c, sw * .8)
            + _c(64, 45, 7, c, sw * .8) + _p("M26 80 L32 68 H68 L74 80", c, sw * .8))


def rewind(c, a, sw):
    return (_p("M54 20 L20 50 L54 80 Z", a, sw, f'fill="{a}" fill-opacity=".25"')
            + _p("M88 20 L54 50 L88 80 Z", a, sw, f'fill="{a}" fill-opacity=".15"') + _p("M12 20 V80", c, sw))


def clock(c, a, sw):
    return (_c(50, 50, 38, c, sw) + _p("M50 50 V24 M50 50 L68 60", a, sw)
            + "".join(_p(f"M{50 + 32 * math.cos(k * math.pi / 6):.1f} {50 + 32 * math.sin(k * math.pi / 6):.1f} "
                         f"L{50 + 36 * math.cos(k * math.pi / 6):.1f} {50 + 36 * math.sin(k * math.pi / 6):.1f}", c, sw * .6)
                      for k in range(12)))


def joystick(c, a, sw):
    return (_r(10, 66, 80, 24, 6, c, sw) + _p("M50 66 V34", c, sw * 1.4) + _c(50, 26, 12, a, sw, a, .45)
            + _c(76, 74, 5, "#ff2a4d", sw * .7, "#ff2a4d", .7) + _c(24, 74, 5, a, sw * .7, a, .5))


def helix(c, a, sw):
    out = []
    for k in range(11):
        t = k / 10
        x = 6 + t * 88
        y1 = 50 + 30 * math.sin(t * 2 * math.pi * 1.5)
        y2 = 50 - 30 * math.sin(t * 2 * math.pi * 1.5)
        out.append(_p(f"M{x:.1f} {y1:.1f} L{x:.1f} {y2:.1f}", c, sw * .5))
        out.append(_r(x - 4, y1 - 4, 8, 8, 1, a, sw * .4, a, .6))
        out.append(_r(x - 4, y2 - 4, 8, 8, 1, c, sw * .4, c, .35))
    return "".join(out)


def battery_bars(c, a, sw):
    return (_r(6, 30, 80, 40, 6, c, sw) + _r(86, 42, 8, 16, 2, c, sw * .8)
            + "".join(_r(12 + k * 18, 36, 14, 28, 2, a, sw * .5, a, .5 if k < 3 else .08) for k in range(4)))


ICONS = {f.__name__: f for f in (gamepad, keycaps, mouse, headset, monitor, cpu, gpu, ram, ssd, hdd, floppy, folder,
                                 cartridge, disc, coin, trophy, crosshair, camera, filmstrip, tombstone, gear, sliders,
                                 toggle, chat, network, wrench, screwdriver, puzzle, cube, cassette, rewind, clock,
                                 joystick, helix, battery_bars)}
ICONS["heart"] = pixel_heart
ICONS["heart_empty"] = lambda c, a, sw: pixel_heart(c, a, sw, empty=True)

# slug: (main accent, line colour, hero cluster as (icon, x, y, size, rotate, depth 0 far .. 1 near))
TABS = {
    "overview": ("#ff2a4d", "#ffd6dd", [("monitor", 4300, 250, 330, 0, 1), ("gamepad", 5050, 270, 300, -8, .9),
                                         ("heart", 3700, 200, 120, 0, .55), ("heart", 3560, 300, 90, 0, .4),
                                         ("keycaps", 5650, 250, 230, 6, .6)]),
    "ready_room": ("#ff3b30", "#ffd9c7", [("joystick", 4400, 250, 320, 0, 1), ("gamepad", 5150, 240, 280, 10, .85),
                                           ("crosshair", 3750, 250, 200, 0, .55), ("trophy", 5750, 260, 190, -6, .55),
                                           ("coin", 3400, 210, 90, 0, .35)]),
    "games": ("#ff2a4d", "#e3dcff", [("cartridge", 4250, 250, 300, -10, 1), ("disc", 4900, 260, 290, 0, .9),
                                      ("gamepad", 5600, 250, 270, 6, .75), ("cartridge", 3650, 240, 170, 12, .45),
                                      ("coin", 3300, 280, 80, 0, .3)]),
    "mods": ("#ff2a6d", "#c9fbff", [("puzzle", 4300, 250, 300, -8, 1), ("wrench", 4950, 250, 280, 20, .9),
                                     ("cube", 5600, 250, 250, 0, .75), ("puzzle", 3700, 230, 160, 14, .45),
                                     ("gear", 3350, 270, 110, 0, .3)]),
    "old_files": ("#ff7a3a", "#ffe3d2", [("floppy", 4300, 250, 290, -8, 1), ("folder", 4950, 250, 290, 4, .9),
                                          ("floppy", 5600, 250, 230, 10, .7), ("floppy", 3700, 240, 150, -14, .45),
                                          ("clock", 3350, 260, 100, 0, .3)]),
    "other_storage": ("#18c9eb", "#d6f6ff", [("hdd", 4300, 250, 300, 0, 1), ("ssd", 4980, 250, 330, -12, .9),
                                              ("folder", 5650, 250, 230, 6, .7), ("ssd", 3700, 240, 180, 14, .45),
                                              ("cube", 3350, 260, 100, 0, .3)]),
    "captures": ("#e175eb", "#fbe3ff", [("camera", 4300, 250, 310, -6, 1), ("filmstrip", 5000, 250, 320, 8, .85),
                                         ("crosshair", 5650, 250, 220, 0, .65), ("filmstrip", 3700, 250, 170, -10, .45),
                                         ("monitor", 3350, 260, 110, 0, .3)]),
    "graveyard": ("#9a6bff", "#e6dcff", [("tombstone", 4300, 260, 300, 0, 1), ("tombstone", 4850, 270, 230, 6, .8),
                                          ("heart_empty", 5450, 240, 210, 0, .75), ("cartridge", 3750, 250, 170, -14, .45),
                                          ("heart_empty", 3400, 270, 100, 0, .3)]),
    "dna": ("#ff2a4d", "#d8f7ff", [("helix", 4500, 250, 420, 0, 1), ("gamepad", 5450, 250, 260, -8, .8),
                                    ("cpu", 3700, 250, 180, 0, .45), ("helix", 3300, 250, 170, 0, .3)]),
    "hardware": ("#13bcf5", "#d9f4ff", [("gpu", 4350, 250, 340, -4, 1), ("cpu", 5050, 250, 270, 0, .9),
                                         ("ram", 5700, 250, 260, -14, .7), ("ram", 3700, 240, 180, 10, .45),
                                         ("battery_bars", 3330, 260, 100, 0, .3)]),
    "undo": ("#f2b43a", "#fff0d1", [("rewind", 4300, 250, 290, 0, 1), ("cassette", 4950, 250, 290, -6, .9),
                                     ("clock", 5600, 250, 230, 0, .7), ("rewind", 3700, 250, 150, 0, .45),
                                     ("cassette", 3350, 260, 100, 8, .3)]),
    "settings": ("#7f93ad", "#e1e9f3", [("gear", 4300, 250, 300, 0, 1), ("sliders", 4950, 250, 280, 0, .9),
                                         ("toggle", 5600, 250, 230, 0, .7), ("gear", 3700, 230, 160, 18, .45),
                                         ("keycaps", 3350, 260, 110, 0, .3)]),
    "assistant": ("#30d76b", "#d8ffe6", [("chat", 4300, 250, 300, 0, 1), ("network", 4980, 250, 300, 0, .9),
                                          ("cpu", 5650, 250, 230, 0, .7), ("chat", 3700, 240, 150, 0, .45),
                                          ("network", 3350, 260, 110, 0, .3)]),
    "more_tools": ("#ff2a4d", "#ffe8c4", [("wrench", 4300, 250, 300, -18, 1), ("keycaps", 4980, 250, 300, 0, .9),
                                           ("screwdriver", 5600, 250, 240, 20, .7), ("mouse", 3700, 250, 160, -8, .45),
                                           ("headset", 3350, 260, 110, 0, .3)]),
}


SCALE = 1.32


def place(name, x, y, size, rot, depth, color, accent):
    size *= SCALE
    s = size / 100.0
    sw = (3.6 + 2.2 * depth) / s
    body = ICONS[name](color, accent, sw)
    move = f"translate({x - 50 * s:.1f} {y - 50 * s:.1f}) scale({s:.4f}) rotate({rot} 50 50)"
    op = .30 + .70 * depth
    wide = f'<g transform="{move}" filter="url(#haze)" opacity="{op * .8:.2f}">{ICONS[name](accent, accent, sw * 2.2)}</g>'
    glow = f'<g transform="{move}" filter="url(#bloom)" opacity="{op:.2f}">{body}</g>'
    crisp = f'<g transform="{move}" opacity="{min(1, op + .1):.2f}">{body}</g>'
    return wide + glow + crisp


def ghost(name, x, y, color):
    """A huge, faint silhouette of the tab's main object behind the cluster, for depth."""
    s = 7.4
    move = f"translate({x - 50 * s:.1f} {y - 50 * s:.1f}) scale({s})"
    return f'<g transform="{move}" filter="url(#haze)" opacity=".16">{ICONS[name](color, color, 1.4)}</g>'


def grid(a, r):
    """Retro perspective floor below the middle, mirrored as a ceiling above; vanishing point near the light."""
    out = []
    horizon = 34
    vx = CX - 200
    for k in range(-40, 41):
        x_far = vx + k * 40
        x_near = vx + k * 260
        for sign in (1, -1):
            y0 = MID + sign * horizon
            y1 = MID + sign * (MID + 20)
            out.append(f'<line x1="{x_far:.0f}" y1="{y0:.0f}" x2="{x_near:.0f}" y2="{y1:.0f}" stroke="{a}" '
                       f'stroke-width="2.4" opacity=".26"/>')
    for k in range(1, 14):
        t = (k / 13) ** 2.1
        for sign in (1, -1):
            y = MID + sign * (horizon + t * (MID - horizon + 20))
            out.append(f'<line x1="0" y1="{y:.1f}" x2="{W}" y2="{y:.1f}" stroke="{a}" stroke-width="{1.2 + 2 * t:.1f}" '
                       f'opacity="{.10 + .26 * t:.2f}"/>')
    return "".join(out)


def particles(a, b, r):
    out = []
    for _ in range(260):
        x = r.uniform(2400, W)
        y = r.uniform(30, H - 30)
        size = r.choice((4, 6, 6, 8, 10))
        op = r.uniform(.15, .7) * min(1, (x - 2300) / 1600)
        col = a if r.random() < .55 else b
        out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{size}" height="{size}" fill="{col}" opacity="{op:.2f}"/>')
    # a few circuit traces drifting in from the left of the cluster
    for _ in range(14):
        y = r.choice(range(60, H - 60, 20))
        x0 = r.uniform(2600, 3400)
        x1 = x0 + r.uniform(300, 700)
        dy = r.choice((-40, -20, 20, 40))
        out.append(f'<path d="M{x0:.0f} {y} H{x1:.0f} l30 {dy} h{r.uniform(80, 240):.0f}" fill="none" stroke="{b}" '
                   f'stroke-width="3" opacity=".22"/>')
        out.append(f'<circle cx="{x0:.0f}" cy="{y}" r="6" fill="none" stroke="{b}" stroke-width="3" opacity=".3"/>')
    return "".join(out)


def picture(slug, seed):
    a, line_col, cluster = TABS[slug]
    r = random.Random(seed)
    hero = max(cluster, key=lambda t: t[5])
    icons = ghost(hero[0], CX + 250, MID, a) + "".join(
        place(name, x, y, size, rot, depth, line_col, a) for name, x, y, size, rot, depth in sorted(cluster, key=lambda t: t[5]))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
 <linearGradient id="wall" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#03060a"/><stop offset=".5" stop-color="#060a10"/><stop offset="1" stop-color="#0a1018"/></linearGradient>
 <radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{a}" stop-opacity=".34"/><stop offset=".45" stop-color="{a}" stop-opacity=".10"/><stop offset="1" stop-color="{a}" stop-opacity="0"/></radialGradient>
 <radialGradient id="core" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ffffff" stop-opacity=".10"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>
 <linearGradient id="reveal" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".40" stop-color="#fff" stop-opacity=".18"/><stop offset=".62" stop-color="#fff" stop-opacity="1"/></linearGradient>
 <linearGradient id="vfade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity=".55"/><stop offset=".22" stop-color="#000" stop-opacity="0"/><stop offset=".78" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></linearGradient>
 <mask id="fadein" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="url(#reveal)"/></mask>
 <filter id="bloom" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7"/></filter>
 <filter id="haze" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="22"/></filter>
</defs>
<rect width="{W}" height="{H}" fill="url(#wall)"/>
<ellipse cx="{CX}" cy="{MID}" rx="1900" ry="560" fill="url(#glow)"/>
<ellipse cx="{CX}" cy="{MID}" rx="900" ry="300" fill="url(#core)"/>
<g mask="url(#fadein)">{grid(a, r)}</g>
<rect x="2600" y="{MID - 2}" width="{W - 2600}" height="4" fill="{a}" opacity=".35" filter="url(#bloom)"/>
<g mask="url(#fadein)">{particles(a, line_col, r)}</g>
<g mask="url(#fadein)">{icons}</g>
<rect width="{W}" height="{H}" fill="url(#vfade)"/>
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
    import sys
    only = set(sys.argv[1:])
    for i, name in enumerate(TABS):
        if not only or name in only:
            render(name, 40 + i)
