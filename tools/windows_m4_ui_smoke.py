"""M4 non-destructive Windows Tk integration smoke in an isolated CI user profile.

Exercises real widgets: navigation, Graveyard Protect/Unprotect buttons, canceled
Delete confirmation, Game DNA plain-language/advanced panels and DPI layouts.
This cannot replace human Windows 10/11 usability or screen-reader testing.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


def main() -> int:
    if (os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GG_M4_QA_DISPOSABLE") != "YES"):
        print("REFUSED: M4 interactive smoke runs only with opt-in on ephemeral Windows CI.")
        return 2
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    scratch = workspace / "_ci_temp"
    scratch.mkdir(exist_ok=True)
    report_path = scratch / "m4-ui-smoke.json"
    results: list[dict] = []

    def check(label, action):
        try:
            action()
            results.append({"test": label, "state": "PASS"})
        except Exception as exc:
            results.append({"test": label, "state": "FAIL",
                            "reason": type(exc).__name__})

    with tempfile.TemporaryDirectory(prefix="GG-M4-UI-", dir=scratch) as temp:
        # Use only an ephemeral settings directory and fabricated archive fixture.
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "LocalAppData")
        os.environ["APPDATA"] = str(Path(temp) / "Roaming")
        os.makedirs(os.environ["LOCALAPPDATA"], exist_ok=True)
        os.makedirs(os.environ["APPDATA"], exist_ok=True)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import tkinter as tk
        from core import OldFile, load_settings
        from ui import GameGraveApp

        dummy = Path(temp) / "skyrim-mod-fixture.zip"
        dummy.write_bytes(b"Game Grave disposable UI fixture")
        stamp = time.time() - 800 * 86400
        os.utime(dummy, (stamp, stamp))
        app = None
        try:
            app = GameGraveApp()
            app.withdraw()
            app.settings["scan_on_launch"] = False
            app.settings["graveyard_days"] = 365
            app.old_files = [OldFile(str(dummy), dummy.stat().st_size, dummy.stat().st_mtime)]
            app.last_scan = "M4 QA"

            def navigation():
                assert len(app.nav_buttons) <= 10
                assert "The Graveyard" in app.nav_buttons
                assert "Game DNA" in app.nav_buttons
                assert "Undo Center" in app.nav_buttons
                for page in ("Overview", "Steam Games", "Game Mods",
                             "Old Files", "The Graveyard", "Game DNA",
                             "Settings", "The Graveyard"):
                    app.show_page(page)
                    app.update_idletasks()
                    assert app.active == page
                    assert app.content.winfo_exists()
                assert dummy.exists()

            check("Simple navigation and all critical pages open repeatedly", navigation)

            def protection():
                app.show_page("The Graveyard")
                rows = app.grave_tree.get_children()
                assert rows, "Fake old archive must appear"
                key = rows[0]
                app.grave_tree.selection_set(key)
                app._grave_sync_actions()
                assert app.grave_delete_button.cget("state") == "normal"
                assert app.grave_protection_button.cget("text") == "Protect selected"
                with patch("ui.messagebox.showinfo"):
                    app.grave_protection_button.invoke()
                assert str(dummy) in app.settings["never_touch"]
                app.grave_tree.selection_set(key)
                app._grave_sync_actions()
                assert app.grave_delete_button.cget("state") == "disabled"
                assert app.grave_protection_button.cget("text") == "Unprotect selected"
                with patch("ui.messagebox.askyesno", return_value=True), \
                     patch("ui.messagebox.showinfo"):
                    app.grave_protection_button.invoke()
                assert str(dummy) not in app.settings["never_touch"]
                app.grave_tree.selection_set(key)
                app._grave_sync_actions()
                assert app.grave_delete_button.cget("state") == "normal"
                assert dummy.read_bytes() == b"Game Grave disposable UI fixture"
                assert load_settings()["never_touch"] == []

            check("Actual Graveyard Protect and Unprotect buttons persist and refresh", protection)

            def cancel_delete():
                app.show_page("The Graveyard")
                key = app.grave_tree.get_children()[0]
                app.grave_tree.selection_set(key)
                app._grave_sync_actions()
                with patch("ui.messagebox.askyesno", return_value=False) as confirmation, \
                     patch("ui.threading.Thread") as background:
                    app.grave_delete_button.invoke()
                confirmation.assert_called_once()
                background.assert_not_called()
                assert dummy.is_file() and app.cleanup_running is False

            check("Canceled Delete never starts a worker or touches a file", cancel_delete)

            def game_dna():
                app.show_page("Game DNA")
                assert "Run Scan PC" in app.dna_explanation_var.get()
                assert not app.dna_advanced_panel.winfo_manager()
                app._dna_toggle_advanced()
                assert app.dna_advanced_panel.winfo_manager()
                app._dna_toggle_advanced()
                assert not app.dna_advanced_panel.winfo_manager()
                app.show_page("The Graveyard")
                assert not app.grave_extra_filters.winfo_manager()
                app._grave_toggle_advanced()
                assert app.grave_extra_filters.winfo_manager()
                app._grave_toggle_advanced()
                assert not app.grave_extra_filters.winfo_manager()

            check("Game DNA beginner view, optional advanced tools and Graveyard filters", game_dna)

            def scaling():
                for factor in (1.0, 1.25, 1.5, 2.0):
                    app.tk.call("tk", "scaling", 1.16 * factor)
                    for page in ("Game DNA", "The Graveyard", "Settings"):
                        app.show_page(page)
                        app.update_idletasks()
                        assert app.content_canvas.bbox("all") is not None
                        assert app.content_scrollbar.winfo_exists()
                assert dummy.exists()

            check("Critical pages render with scroll containment at 100/125/150/200 percent", scaling)
        finally:
            if app is not None:
                app.destroy()

    report = {
        "schema": 1, "test_family": "M4 disposable Windows Tk widget smoke",
        "checks": results,
        "all_passed": bool(results) and all(item["state"] == "PASS" for item in results),
        "real_game_files_used": False,
        "deletion_performed": False,
        "screen_reader_verified": False,
        "manual_desktop_accepted": False,
        "limitations": "Ephemeral hosted Windows desktop; not physical DPI/screen reader or nontechnical-user testing.",
    }
    with report_path.open("x", encoding="utf-8") as out:
        json.dump(report, out, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
