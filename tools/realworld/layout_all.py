"""Every tab at 960, 1280 and 1920 pixels wide and at 100, 125 and 150 percent Windows scaling, checked for cut-off words.

Each scale runs in its own process (Qt reads the scale once). For every tab and size it saves a screenshot and records:
sideways scrolling, buttons too narrow for their words, one-line labels too narrow for their words, and controls that
stick out past the window's right edge. Sizes are real screen pixels, so 1920 at 150% is a 1280-point window.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

SIZES = ((960, 640), (1280, 720), (1920, 1080))
SCALES = ("1", "1.25", "1.5")


def cut_offs(window):
    """Words that don't fit: a control past the window's right edge, or text wider than the space it has. Text Game
    Grave shortens on purpose (ending in "…") is not counted. Buttons get 4 pixels of room for their border."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractButton, QLabel, QAbstractScrollArea
    page = window.page
    found = []
    right = window.width()
    for w in page.findChildren(QAbstractButton) + page.findChildren(QLabel):
        if not w.isVisibleTo(window) or w.width() <= 0 or w.height() <= 0:
            continue
        text = w.text() if hasattr(w, "text") else ""
        if not text or not text.strip() or "<" in text or text.rstrip().endswith("…"):
            continue
        x = w.mapTo(window, w.rect().topRight()).x()
        if x > right + 1:
            found.append({"kind": "past the edge", "text": text[:60], "by": x - right})
            continue
        if isinstance(w, QLabel) and w.wordWrap():
            continue
        metrics = w.fontMetrics()
        need = max(metrics.horizontalAdvance(line) for line in text.replace("&&", "&").split("\n"))
        room = w.contentsRect().width()
        if isinstance(w, QAbstractButton):
            room -= 4
            under = getattr(w, "toolButtonStyle", None) and w.toolButtonStyle() == Qt.ToolButtonTextUnderIcon
            if not w.icon().isNull() and not under:
                room -= w.iconSize().width() + 4
        if need > room + 1:
            found.append({"kind": type(w).__name__, "text": text[:60], "short_by": need - room})
    sideways = 0
    for area in [page] + page.findChildren(QAbstractScrollArea):
        bar = area.horizontalScrollBar() if hasattr(area, "horizontalScrollBar") else None
        if bar is not None and bar.isVisible() and bar.maximum() > 0 and area.isVisibleTo(window):
            sideways = max(sideways, bar.maximum())
    return sideways, found


def one_scale(scale, output: Path):
    os.environ["QT_SCALE_FACTOR"] = scale
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    rw.isolate("GG-rw-layout-")
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from unittest.mock import patch
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core import SteamGame, default_settings
    from gg_desktop import nav_groups
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games
    from tests.test_mods_functionality import mo2_fixture
    from tests.test_old_files_functionality import drive_fixture, old_file

    rep = rw.Report(f"layout-{scale.replace('.', '_')}", output)
    shots = output / "layout"
    shots.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="GG-layout-data-"))
    drive, _other, _home, downloads, drives = drive_fixture(root)
    mod_inventory, _storage, _profiles, _ini = mo2_fixture(root)
    steam = []
    names = ["Cyberpunk 2077", "Baldur's Gate 3", "The Witcher 3: Wild Hunt: Complete Edition", "Starfield",
             "Skyrim Special Edition", "Red Dead Redemption 2", "Warhammer 40,000: Space Marine 2 - Ultra Edition"]
    for i, name in enumerate(names):
        install = root / "Steam" / "steamapps" / "common" / str(1000 + i)
        install.mkdir(parents=True)
        steam.append(SteamGame(str(1000 + i), name, str(root / "Steam"), str(install), (i + 1) * 7 * 1024 ** 3,
                               time.time() - i * 86400 * 40, "Layout check"))
    files = [old_file(downloads / f"old-installer-{i:03}.zip") for i in range(60)]
    inventory = Inventory(steam=steam, games=merge_games(steam, []), mods=mod_inventory.mods, files=files,
                          scanned_at="2026-11-17 09:00")
    settings = default_settings()
    settings["scan_folder"] = str(downloads)
    with patch("gg_desktop.app.load_settings", return_value=settings), \
            patch("gg_desktop.old_files.local_drives", return_value=drives), \
            patch("gg_desktop.old_files_data.local_drives", return_value=drives), \
            patch("core.save_settings"), patch("gg_desktop.old_files.save_settings"), \
            patch("gg_desktop.game_artwork._request", side_effect=OSError("no network in this check")), \
            patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error"), \
            patch.object(CrimsonWindow, "confirm", return_value=False):
        window = CrimsonWindow()
        window.inventory = inventory
        window.show()
        ratio = float(scale)
        for px, py in SIZES:
            width, height = round(px / ratio), round(py / ratio)
            window.resize(width, height)
            rw.pump(0.3)
            if window.width() > width + 2:
                rep.note("the window can't get this narrow", wanted=width, got=window.width(), screen_px=px)
            for route in nav_groups.routes():
                try:
                    window.navigate(route)
                    rw.pump(0.35)
                    sideways, found = cut_offs(window)
                except Exception as exc:
                    rep.check(f"{route} at {px}px {int(ratio * 100)}%", False, error=f"{type(exc).__name__}: {exc}")
                    continue
                name = f"{route.replace(' ', '-').lower()}-{px}-{int(ratio * 100)}.png"
                window.grab().save(str(shots / name))
                rep.check(f"{route} at {px}px {int(ratio * 100)}%", not sideways and not found,
                          sideways=sideways, cut_off=found[:8], more=max(0, len(found) - 8), shot=name)
        window.close()
    return rep.finish()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_ci_temp/realworld"))
    parser.add_argument("--scale", choices=SCALES)
    args = parser.parse_args()
    if args.scale:
        return one_scale(args.scale, args.output)
    codes = [subprocess.call([sys.executable, __file__, "--output", str(args.output), "--scale", s]) for s in SCALES]
    return 0 if not any(codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
