"""Real Windows Tk preview smoke with disposable PNG and no cleanup.

Runs only under explicit ephemeral GitHub Actions permission. This proves
preview can render without reading, moving or changing user files.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


def main() -> int:
    if (os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GG_SCREENSHOT_QA_DISPOSABLE") != "YES"):
        print("REFUSED: only opt-in ephemeral Windows UI fixture is supported.")
        return 2
    base = Path(os.environ["GITHUB_WORKSPACE"]) / "_ci_temp"
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="GG-ScreenshotUI-", dir=base) as tmp:
        root = Path(tmp)
        os.environ["LOCALAPPDATA"] = str(root / "Local")
        os.environ["APPDATA"] = str(root / "Roaming")
        Path(os.environ["LOCALAPPDATA"]).mkdir()
        Path(os.environ["APPDATA"]).mkdir()
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from PIL import Image
        from core import OldFile
        from ui import GameGraveApp
        import tkinter as tk

        capture = root / "Captures"
        capture.mkdir()
        photo = capture / "GameGrave_Disposable_Screenshot.png"
        Image.new("RGB", (600, 330), (45, 87, 122)).save(photo)
        timestamp = time.time() - 900 * 86400
        os.utime(photo, (timestamp, timestamp))
        state = photo.stat()
        fixture_bytes = photo.read_bytes()
        old = OldFile(str(photo), state.st_size, state.st_mtime, state.st_dev,
                      state.st_ino, state.st_mtime_ns, state.st_nlink)

        app = GameGraveApp()
        app.withdraw()
        try:
            app.settings["scan_on_launch"] = False
            app.settings["graveyard_days"] = 365
            app.screenshots = [old]
            app.show_page("The Graveyard")
            rows = app.grave_tree.get_children()
            assert len(rows) == 1, "Screenshot must be visible in the Graveyard"
            key = rows[0]
            entry = app.graveyard_lookup[key]
            assert entry.category == "Old game screenshot"
            assert not entry.can_recycle
            assert app.grave_tree.set(key, "decision") == "Preview individually"
            app.grave_tree.selection_set(key)
            app._grave_sync_actions()
            assert app.grave_delete_button.cget("state") == "disabled"

            with patch("ui.messagebox.showwarning") as blocked, \
                 patch("ui.messagebox.askyesno") as approved, \
                 patch("ui.recycle_file") as recycler:
                app._grave_recycle_ids([key])
                blocked.assert_called_once()
                approved.assert_not_called()
                recycler.assert_not_called()

            # Uses the actual background Pillow decoder and real Tk image widget.
            app._grave_preview_screenshot()
            windows = []
            for _attempt in range(120):
                app.update()
                windows = [child for child in app.winfo_children()
                           if isinstance(child, tk.Toplevel) and child.winfo_exists()]
                if windows and hasattr(windows[0], "_gg_screenshot_photo"):
                    break
                time.sleep(0.05)
            assert windows and hasattr(windows[0], "_gg_screenshot_photo"), (
                "Expected a real in-app screenshot preview Toplevel")
            for window in windows:
                window.destroy()
            assert photo.read_bytes() == fixture_bytes
            assert app.cleanup_running is False
            print("PASS: native Windows PNG preview displayed; bulk cleanup denied; "
                  "disposable image unchanged; no files recycled.")
        finally:
            app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
