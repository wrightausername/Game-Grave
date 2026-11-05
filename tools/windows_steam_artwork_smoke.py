"""Native Windows smoke of public Steam cover download, rendering and offline reuse."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time


def main():
    if os.name != "nt" or os.environ.get("GG_CRIMSON_QA_DISPOSABLE") != "YES":
        print("Refusing outside disposable native Windows QA.")
        return 2
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from PySide6.QtWidgets import QApplication
    from core import SteamGame
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.artwork import load_artwork
    from gg_desktop.models import merge_games
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="GG-Steam-Artwork-", dir=root / "_ci_temp") as temp:
        isolated = Path(temp)
        os.environ["LOCALAPPDATA"] = str(isolated / "Local")
        os.environ["APPDATA"] = str(isolated / "Roaming")
        game = SteamGame("620", "Portal 2", str(isolated / "Steam"), str(isolated / "Portal 2"),
                         1000, None, "Synthetic library fixture; real public Steam artwork")
        window = CrimsonWindow()
        try:
            window.inventory.steam = [game]
            window.inventory.games = merge_games([game], [])
            window.inventory.scanned_at = "Synthetic library · real Steam artwork"
            window.status.setText("SYNTHETIC LIBRARY · REAL STEAM ARTWORK")
            window.resize(1440, 900)
            window.show()
            window.navigate("Games")
            deadline = time.monotonic() + 40
            while ("620", "cover") not in window.artwork.images and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            assert ("620", "cover") in window.artwork.images, str(window.artwork.states)
            target = window.artwork.cache_root / "620-cover.png"
            assert target.is_file(), "Downloaded Steam cover was not cached"
            image, status = load_artwork("620", "cover", [], window.artwork.cache_root, False, lambda: False)
            assert not image.isNull() and status == "Cached", "Steam artwork not available offline"
            app.processEvents()
            output = root / "_ci_temp/crimson-steam-artwork-1440.png"
            assert window.grab().save(str(output)), "Steam artwork screenshot failed"
            print("PASS: real public Steam artwork (Portal 2, app 620) downloads, renders in Games and reloads offline.")
            print("Cached image SHA256:", hashlib.sha256(target.read_bytes()).hexdigest())
        finally:
            window.close()
            deadline = time.monotonic() + 10
            while window.artwork.active and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
