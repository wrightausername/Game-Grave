"""Prove Ready Room leaves the original application shell and other screens intact.

Renders each original page using its original shell and the Ready Room integration,
then compares the actual pixels before and after visiting Ready Room. Runs on
native Windows Qt in CI and on the offscreen backend for local Linux review.
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

BASELINE = "7353eeb8f862d77b93933332cabea55df31cb7db"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    def original(path):
        return subprocess.check_output(["git", "show", BASELINE + ":" + path], cwd=root)

    probe = subprocess.run(["git", "cat-file", "-e", BASELINE], cwd=root, capture_output=True)
    if probe.returncode:
        subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", BASELINE], cwd=root, check=True)
    for path in ("gg_desktop/theme.py", "gg_desktop/screens.py", "gg_desktop/widgets.py",
                 "gg_desktop/backend.py", "gg_desktop/models.py"):
        assert (root / path).read_text(encoding="utf-8") == original(path).decode().replace("\r\n", "\n"), \
            "Changed outside Ready Room: " + path

    baseline_source = original("gg_desktop/app.py").decode()
    current_source = (root / "gg_desktop/app.py").read_text(encoding="utf-8")

    def method(source, name):
        return next(ast.dump(node, include_attributes=False) for cls in ast.parse(source).body
                    if isinstance(cls, ast.ClassDef) and cls.name == "CrimsonWindow"
                    for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)

    for name in ("_create_shell", "start_scan", "cancel_scan", "job", "closeEvent", "confirm"):
        assert method(current_source, name) == method(baseline_source, name), "Shared behavior changed: " + name

    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtGui import QCursor, QShortcut
    from PySide6.QtWidgets import QApplication
    from core import default_settings
    from gg_desktop.app import CrimsonWindow, ROUTES, ROUTE_ALIASES
    from gg_desktop.theme import STYLE

    app = QApplication.instance() or QApplication([])
    namespace = {"__name__": "gg_desktop.scope_baseline", "__file__": str(root / "gg_desktop/app.py")}
    exec(compile(baseline_source, "original_app.py", "exec"), namespace)
    namespace["load_settings"] = default_settings
    assert tuple(r for r in ROUTES if r[0] != "Ready Room") == namespace["ROUTES"]
    assert ROUTE_ALIASES == namespace["ROUTE_ALIASES"]

    def settle(window):
        window.activateWindow()
        window.centralWidget().setFocusPolicy(Qt.StrongFocus)
        window.centralWidget().setFocus()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    disk = SimpleNamespace(total=1024**4, used=256 * 1024**3, free=768 * 1024**3)
    QCursor.setPos(0, 0)
    with patch("gg_desktop.app.load_settings", side_effect=default_settings), \
            patch("gg_desktop.screens.shutil.disk_usage", return_value=disk):
        baseline = namespace["CrimsonWindow"]()
        window = CrimsonWindow()
        assert window.size() == baseline.size(), "Configured startup size changed"
        baseline.show()
        window.show()
        baseline.resize(1450, 900)
        window.resize(1450, 900)
        settle(window)
        assert window.current_route == baseline.current_route == "Overview"
        assert window.size() == baseline.size()
        assert window.windowFlags() == baseline.windowFlags()
        assert window.windowTitle() == baseline.windowTitle()
        assert window.styleSheet() == baseline.styleSheet() == STYLE
        for phase in ("before-ready-room", "after-ready-room"):
            if phase == "after-ready-room":
                window.navigate("Ready Room")
                settle(window)
            for route, _ in namespace["ROUTES"]:
                baseline.navigate(route)
                settle(baseline)
                window.navigate(route)
                settle(window)
                expected = baseline.page.grab().toImage()
                actual = window.page.grab().toImage()
                if expected != actual:
                    slug = route.lower().replace(" ", "-")
                    expected.save(str(args.output / f"scope-{slug}-original.png"))
                    actual.save(str(args.output / f"scope-{slug}-current.png"))
                    raise AssertionError("Existing page pixels changed " + phase + ": " + route)
                assert not window.page.findChildren(QShortcut)
        window.navigate("Overview")
        settle(window)
        window.grab().save(str(args.output / "restored-overview.png"))
        window.close()
        baseline.close()
        app.processEvents()
    print("PASS: original shell, window chrome, size, startup, theme, screen code and route aliases; "
          "all 9 original pages render identical pixels before and after visiting Ready Room.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
