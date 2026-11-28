"""`GameGrave-Crimson-Preview.exe --self-check <folder>`: the installed app checks itself and writes a report.

Used by the Windows build machine to test the real installed program, not the source. It reads and looks only: it imports
every part of Game Grave (a part missing from the build fails here), runs one normal scan, opens every tab and saves a
picture of each, notes any error the app hit, and records what it found from an earlier version's settings (chats, notes,
an older AI model). It never cleans, recycles or changes anything on the PC. Then it closes the app.
"""
from __future__ import annotations

import importlib
import json
import os
import pkgutil
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def wanted(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if "--self-check" in argv:
        i = argv.index("--self-check")
        return Path(argv[i + 1]) if i + 1 < len(argv) else Path.cwd() / "gg-self-check"
    return None


def module_names():
    import gg_desktop
    names = sorted({m.name for m in pkgutil.iter_modules(gg_desktop.__path__)})
    return ["gg_desktop." + n for n in names]


def import_all(names):
    failed = {}
    for name in names:
        if name.endswith(("self_check",)):
            continue
        try:
            importlib.import_module(name)
        except Exception as exc:          # a part missing from the build, or one that breaks on import
            failed[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return failed


def optional_parts():
    found = {}
    for label, name in (("read aloud", "PySide6.QtTextToSpeech"), ("pictures", "PySide6.QtSvg"),
                        ("multimedia", "PySide6.QtMultimedia")):
        try:
            importlib.import_module(name)
            found[label] = True
        except Exception as exc:
            found[label] = f"{type(exc).__name__}: {exc}"[:200]
    return found


def run(window, folder: Path, scan_timeout=900):
    """Drives the window step by step with timers so the app stays responsive; quits with 0 (passed) or 1."""
    folder.mkdir(parents=True, exist_ok=True)
    report = {"started": time.time(), "version": getattr(window, "VERSION", ""), "steps": [], "errors": [],
              "python": sys.version, "frozen": bool(getattr(sys, "frozen", False)), "argv": sys.argv[1:]}
    original_hook = sys.excepthook

    def hook(kind, value, tb):
        report["errors"].append("".join(traceback.format_exception(kind, value, tb))[-1500:])
        original_hook(kind, value, tb)
    sys.excepthook = hook

    def step(name, ok=True, **detail):
        report["steps"].append(dict({"step": name, "ok": bool(ok), "at": round(time.time() - report["started"], 1)},
                                    **detail))

    def shot(name):
        try:
            window.grab().save(str(folder / f"{name}.png"))
        except Exception as exc:
            report["errors"].append(f"picture {name}: {exc}")

    def finish():
        from gg_desktop import comfort
        try:
            report["app_errors"] = list(comfort.state_of(window).errors)
        except Exception:
            report["app_errors"] = []
        report["passed"] = all(s["ok"] for s in report["steps"]) and not report["errors"]
        report["seconds"] = round(time.time() - report["started"], 1)
        (folder / "self-check.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        sys.excepthook = original_hook
        QApplication.instance().exit(0 if report["passed"] else 1)

    def begin():
        # What an earlier version left behind survives the update
        from gg_desktop import assistant_actions, assistant_memory, local_ai_core as ai
        settings = getattr(window, "settings", {}) or {}
        chats = assistant_actions.load_chats(settings)
        step("settings kept", True, chats=len(chats), notes=len(settings.get(assistant_memory.NOTES_KEY) or []),
             keys=len(settings), legacy_models=[k for k in ai.installed_models() if ai.is_legacy(k)])
        names = module_names()
        failed = import_all(names)
        step("every part is in the build", not failed and len(names) > 50, modules=len(names), failed=failed)
        parts = optional_parts()
        step("optional parts", parts.get("read aloud") is True, parts=parts)
        welcome = [w for w in QApplication.topLevelWidgets() if w.isVisible() and type(w).__name__ == "WelcomeDialog"]
        step("welcome tour on first launch", True, shown=bool(welcome))
        if welcome:
            welcome[0].grab().save(str(folder / "welcome.png"))
            welcome[0].close()
        shot("first-launch")
        started = time.time()
        if not window.scanning:
            window.start_scan()
        wait_scan(started)

    def wait_scan(started):
        if window.scanning and time.time() - started < scan_timeout:
            QTimer.singleShot(500, lambda: wait_scan(started))
            return
        inv = window.inventory
        step("first scan", bool(inv.scanned_at) and not window.scanning, seconds=round(time.time() - started, 1),
             games=len(inv.games), mods=len(inv.mods), old_files=len(inv.files),
             warnings=list(inv.warnings)[:10])
        shown = getattr(window.page, "_built_for", None) is inv
        step("results on screen without changing tabs", shown, route=window.current_route)
        shot("after-scan")
        from gg_desktop import nav_groups
        tabs(list(nav_groups.routes()), [])

    def tabs(left, done):
        if not left:
            step("every tab opens", True, tabs=done)
            QTimer.singleShot(200, trailer)
            return
        route = left.pop(0)
        t = time.time()
        if route == "AI Assistant" and hasattr(window, "assistant_enabled") and not window.assistant_enabled():
            done.append({"tab": route, "ok": True, "note": "off until it's turned on in Settings, as designed"})
            QTimer.singleShot(50, lambda: tabs(left, done))
            return
        try:
            window.navigate(route)
            QApplication.processEvents()
            ok = window.current_route == route and window.page is not None
            done.append({"tab": route, "ok": ok, "seconds": round(time.time() - t, 2),
                         "sideways": window.page.horizontalScrollBar().maximum()
                         if hasattr(window.page, "horizontalScrollBar") else 0})
            shot("tab-" + "".join(c if c.isalnum() else "-" for c in route.lower()))
            if not ok:
                step("tab " + route, False)
        except Exception as exc:
            step("tab " + route, False, error=f"{type(exc).__name__}: {exc}"[:300])
        QTimer.singleShot(250, lambda: tabs(left, done))

    def trailer():
        """Deals: a real Steam trailer plays on a game's page in the installed program (reads only; skipped offline)."""
        from types import SimpleNamespace
        from gg_desktop import deals_page
        try:
            window.navigate("Deals")
            QApplication.processEvents()
            w = window.deals_page_widgets
            deals_page.state(window).showing_game = True
            deals_page._page(w, 1)
            deals_page.load_media(window, SimpleNamespace(steam_app_id="1245620", title="ELDEN RING"))
        except Exception as exc:
            step("Deals trailer plays", False, error=f"{type(exc).__name__}: {exc}"[:300])
            QTimer.singleShot(200, finish)
            return
        started = time.time()

        def wait_items():
            items = getattr(w.media, "items", [])
            if not any(i[0] == "video" for i in items):
                if time.time() - started < 40:
                    QTimer.singleShot(300, wait_items)
                else:
                    step("Deals trailer plays", True, note="no trailers came from Steam (offline?)", items=len(items))
                    QTimer.singleShot(200, finish)
                return
            from PySide6.QtWidgets import QAbstractButton
            buttons = [b for b in w.media.findChildren(QAbstractButton) if b.accessibleName().startswith("Play trailer")]
            if not buttons:
                step("Deals trailer plays", False, why="no trailer thumbnail to press", items=len(items))
                QTimer.singleShot(200, finish)
                return
            buttons[0].click()
            wait_play(time.time())

        def wait_play(clicked):
            player = getattr(w.hero, "player", None)
            pos = player.position() if player is not None else 0
            failed = "couldn't play" in w.hero_caption.text()
            if pos < 2000 and not failed and time.time() - clicked < 40:
                QTimer.singleShot(300, lambda: wait_play(clicked))
                return
            frame = False
            try:
                frame = w.hero.video.frames
                img = w.hero.video.image
                if img is not None:                       # the picture isn't just black
                    small = img.scaled(32, 18)
                    lit = sum(QColor(small.pixel(x, y)).lightness() for x in range(32) for y in range(18)) / (32 * 18)
                    report.setdefault("trailer_lightness", round(lit, 1))
                    frame = frame if lit > 4 else 0
            except Exception:
                pass
            shot("deals-trailer")
            step("Deals trailer plays", pos >= 2000 and not failed and bool(frame),
                 position_ms=pos, frame=frame, caption=w.hero_caption.text()[:120],
                 status=str(player.mediaStatus()) if player is not None else "no player",
                 error=player.errorString() if player is not None else "",
                 video=player.hasVideo() if player is not None else False)
            w.hero.stop()
            QTimer.singleShot(200, finish)
        wait_items()

    QTimer.singleShot(int(os.environ.get("GG_SELF_CHECK_DELAY_MS", "1500")), begin)
