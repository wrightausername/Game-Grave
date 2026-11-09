"""Native Qt check of Mod Shield: the tile opens it, it lists the files that stand out in a scanned mod folder, changes
nothing, shows fingerprints, and asks before Microsoft Defender (a fake here) reports with remediation off."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root_dir))
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from gg_desktop import mod_shield as ms, tools_windows as tw, winpc
    from gg_desktop.app import CrimsonWindow

    app = QApplication.instance() or QApplication([])

    def wait_for(test, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            if test():
                return
            QTest.qWait(20)
        raise AssertionError("timed out")

    class FakeRunner:
        calls = []

        def run(self, argv, **kw):
            FakeRunner.calls.append(list(argv))
            return winpc.RunResult(0, "Scan starting...\nScan finished.\nScanning found no threats.\n")

    with tempfile.TemporaryDirectory(prefix="GG-shield-") as temp:
        root = Path(temp)
        mods = root / "Mods"
        (mods / "Cool Mod").mkdir(parents=True)
        (mods / "SKSE" / "Plugins").mkdir(parents=True)
        files = {
            mods / "Cool Mod" / "Cool.esp": b"plugin",
            mods / "Cool Mod" / "readme.txt.exe": b"MZ disguised",
            mods / "Cool Mod" / "updater.exe": b"MZ tool",
            mods / "SKSE" / "Plugins" / "po3_Tweaks.dll": b"dll",
        }
        for path, data in files.items():
            path.write_bytes(data)
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files}
        logged, asked, opened = [], [], []
        shown = []
        stack = ExitStack()
        for target, options in (
            ("core.config_dir", dict(return_value=root / "Config")),
            ("gg_desktop.tools_page.get_activity", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_activity", dict(return_value=[])),
            ("gg_desktop.undo_page.get_records", dict(return_value=[])),
            ("gg_desktop.undo_page.get_activity", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_records", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_activity", dict(return_value=[])),
            ("gg_desktop.settings_page.get_records", dict(return_value=[])),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.ready_room_services.fetch_one", dict(side_effect=OSError("offline QA"))),
            ("gg_desktop.winpc.Runner", dict(return_value=FakeRunner())),
            ("gg_desktop.winpc.activity", dict(side_effect=lambda kind, details, **kw: logged.append((kind, details)))),
            ("gg_desktop.mod_shield.find_defender", dict(return_value="C:\\Fake\\MpCmdRun.exe")),
            ("gg_desktop.tools_shield.QDesktopServices.openUrl", dict(side_effect=lambda url: opened.append(url.toString()))),
        ):
            stack.enter_context(patch(target, **options))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        stack.enter_context(patch.object(CrimsonWindow, "confirm", side_effect=lambda t, m, **kw: asked.append((t, m)) or True))
        stack.enter_context(patch.object(tw.WinDialog, "exec", lambda self: shown.append(self) or 0))
        with stack:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.navigate("More Tools")
            app.processEvents()
            window.inventory.mods = [SimpleNamespace(path=str(mods), name="Mods", source="QA", apparent_bytes=0,
                                                     file_count=4, truncated=False)]
            assert "bulk_files" not in window.tools_tiles
            tile = window.tools_tiles["mod_shield"]
            assert "not offered" not in tile.accessibleName()
            tile.click()
            wait_for(lambda: bool(shown))
            dialog = shown[-1]
            assert dialog.scan_button.isEnabled() and "(1)" in dialog.scan_button.text()
            assert dialog.defender_button.isEnabled() is False

            dialog.scan_button.click()
            wait_for(lambda: dialog.report is not None)
            report = dialog.report
            assert report.files_checked == 4, report.summary()
            assert report.count(ms.CHECK_FIRST) == 2 and report.count(ms.EXPECTED) == 1, report.summary()
            assert dialog.listing.count() == 3
            assert dialog.listing.item(0).text().startswith(ms.CHECK_FIRST)
            assert "Nothing was changed" in dialog.summary.text()
            assert logged[-1][0] == "Mod Shield"
            assert {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files} == before

            # The disguised file comes first, with its fingerprint; VirusTotal gets the fingerprint only.
            first = report.findings[0]
            assert first.kind == "Disguised name" and first.sha256 == hashlib.sha256(b"MZ disguised").hexdigest()
            assert first.sha256 in dialog.detail.text()
            assert dialog.lookup_button.isEnabled() and dialog.copy_button.isEnabled()
            dialog.copy_button.click()
            assert QApplication.clipboard().text() == first.sha256
            dialog.lookup_button.click()
            assert opened[-1] == "https://www.virustotal.com/gui/file/" + first.sha256
            dialog.listing.setCurrentRow(2)
            assert "SKSE" in dialog.detail.text() and not dialog.lookup_button.isEnabled()

            dialog.show()
            QTest.qWait(80)
            app.processEvents()
            assert dialog.grab().save(str(args.output / "tools-mod-shield.png"))

            # Defender: asks first, runs with remediation off, and reports.
            assert dialog.defender_button.isEnabled()
            dialog.defender_button.click()
            wait_for(lambda: "no threats" in dialog.defender_note.text())
            assert asked[-1][0] == "Scan with Microsoft Defender" and "does not quarantine" in asked[-1][1]
            argv = FakeRunner.calls[-1]
            assert argv[0] == "C:\\Fake\\MpCmdRun.exe" and argv[-1] == "-DisableRemediation" and str(mods) in argv
            assert logged[-1][0] == "Mod Shield" and "Defender" in logged[-1][1]
            assert {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files} == before
            QTest.qWait(80)
            app.processEvents()
            assert dialog.grab().save(str(args.output / "tools-mod-shield-defender.png"))
            dialog.hide()

            assert errors.call_count == 0, errors.call_args_list
            window.close()
    print("PASS: Mod Shield opens from its tile, lists programs, disguised names and loader plugins in a scanned mod "
          "folder, shows fingerprints, asks before a report-only Defender scan, logs both, and changes no file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
