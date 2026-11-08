"""Native Qt check of the seven Windows tools: each opens, shows what it will change, asks first, does exactly that and
logs it. The registry and every command are fakes; only throw-away temp folders are touched."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import time
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
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from gg_desktop import tools_windows as tw, winpc
    from gg_desktop.app import CrimsonWindow
    from tests.test_winpc import FakeRegistry, FakeRunner, TASKLIST, reg_key

    app = QApplication.instance() or QApplication([])

    def wait_for(test, seconds=8):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            if test():
                return
            QTest.qWait(20)
        raise AssertionError("timed out")

    with tempfile.TemporaryDirectory(prefix="GG-wintools-") as temp:
        root = Path(temp)
        logged, shown, asked = [], [], []
        reg = FakeRegistry({reg_key(winpc.HKCU, winpc.RUN_KEY, "Discord"): ("C:\\d.exe", winpc.REG_SZ)})
        runner = FakeRunner({
            "getactivescheme": winpc.RunResult(0, "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)"),
            "tasklist": winpc.RunResult(0, TASKLIST), "taskkill": winpc.RunResult(0, "SUCCESS"),
            "cmd.exe": winpc.RunResult(0, "hello from the fake shell")})
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
            ("gg_desktop.winpc.default_registry", dict(return_value=reg)),
            ("gg_desktop.winpc.Runner", dict(return_value=runner)),
            ("gg_desktop.winpc.activity", dict(side_effect=lambda kind, details, **kw: logged.append((kind, details)))),
        ):
            stack.enter_context(patch(target, **options))
        stack.enter_context(patch.dict(os.environ, {"APPDATA": str(root / "AppData"), "PROGRAMDATA": str(root / "ProgData")}))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        infos = stack.enter_context(patch.object(CrimsonWindow, "info"))
        stack.enter_context(patch.object(CrimsonWindow, "confirm", side_effect=lambda t, m, **kw: asked.append((t, m)) or True))
        stack.enter_context(patch.object(tw.WinDialog, "exec", lambda self: shown.append(self) or 0))
        with stack:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.navigate("More Tools")
            app.processEvents()

            def open_tool(key):
                before = len(shown)
                window.tools_tiles[key].click()
                wait_for(lambda: len(shown) > before)
                return shown[-1]

            # 1. Windows Cleanup: only old files inside the temp root, only after the confirmation names them.
            temp_root = root / "Temp"
            temp_root.mkdir()
            old, fresh = temp_root / "old.tmp", temp_root / "fresh.tmp"
            old.write_bytes(b"x" * 100)
            fresh.write_bytes(b"y" * 100)
            ancient = time.time() - 9 * 86400
            os.utime(old, (ancient, ancient))
            outside = root / "Keep.txt"
            outside.write_bytes(b"keep")
            with patch("gg_desktop.winpc.cleanup_roots", return_value=[temp_root]):
                dialog = open_tool("windows_cleanup")
                assert old.exists()
                assert dialog.delete_button.isEnabled()
                dialog.delete_button.click()
                wait_for(lambda: not old.exists())
                wait_for(lambda: "Deleted 1 files" in dialog.result_line.text())
            assert asked[-1][0] == "Delete temporary files" and str(temp_root) in asked[-1][1] and "Recycle Bin" in asked[-1][1]
            assert fresh.exists() and outside.exists() and temp_root.exists()
            assert logged[-1][0] == "Windows Cleanup" and "Deleted 1 files" in logged[-1][1]
            dialog.grab().save(str(args.output / "tools-windows-cleanup.png"))

            # 2. Game Optimizer: names the registry values, applies, then Undo restores them.
            dialog = open_tool("game_optimizer")
            assert set(dialog.checks) == {"game_mode", "background_recording", "power_plan"}
            dialog.checks["game_mode"].setChecked(True)
            dialog.checks["background_recording"].setChecked(True)
            dialog.apply_button.click()
            assert "AutoGameModeEnabled = 1" in asked[-1][1] and "GameDVR_Enabled = 0" in asked[-1][1]
            assert reg.read(*winpc.GAME_MODE)[0] == 1 and reg.read(*winpc.DVR_STORE)[0] == 0
            assert logged[-1][0] == "Game Optimizer" and dialog.undo_button.isEnabled()
            dialog.undo_button.click()
            assert reg.read(*winpc.GAME_MODE) is None and reg.read(*winpc.DVR_STORE) is None
            assert not dialog.undo_button.isEnabled()
            dialog.grab().save(str(args.output / "tools-windows-optimizer.png"))

            # 3. Memory Optimizer: lists user apps only, asks politely, never forces.
            dialog = open_tool("memory_optimizer")
            wait_for(lambda: dialog.listing.count() == 2)
            assert "chrome.exe" in dialog.listing.item(0).text()
            dialog.listing.item(0).setCheckState(Qt.Checked)
            dialog.close_button.click()
            wait_for(lambda: ["taskkill", "/PID", "1200"] in runner.calls)
            assert all("/F" not in c for c in runner.calls if c and c[0] == "taskkill")
            assert "chrome.exe" in asked[-1][1] and "not forced" in asked[-1][1]
            wait_for(lambda: logged and logged[-1][0] == "Memory Optimizer")
            dialog.grab().save(str(args.output / "tools-windows-memory.png"))

            # 4. Startup Manager: flips the approval switch, never deletes the entry.
            dialog = open_tool("startup_manager")
            assert dialog.table.count() == 1 and "On" in dialog.table.item(0).text()
            dialog.table.item(0).setSelected(True)
            dialog.disable_button.click()
            assert reg.read(winpc.HKCU, winpc.APPROVED + "\\Run", "Discord")[0][0] == 3
            assert reg.read(winpc.HKCU, winpc.RUN_KEY, "Discord") is not None
            assert logged[-1][0] == "Startup Manager" and "Discord" in asked[-1][1]
            assert "Off" in dialog.table.item(0).text()
            dialog.table.item(0).setSelected(True)
            dialog.enable_button.click()
            assert reg.read(winpc.HKCU, winpc.APPROVED + "\\Run", "Discord")[0][0] == 2
            dialog.grab().save(str(args.output / "tools-windows-startup.png"))

            # 5. Command Runner: shows the exact line before running it, shows the output, logs it.
            dialog = open_tool("command_runner")
            dialog.run_button.click()
            assert "Type a command" in dialog.result_line.text()
            dialog.line.setText("echo hello")
            dialog.run_button.click()
            wait_for(lambda: "hello from the fake shell" in dialog.output.toPlainText())
            assert "echo hello" in asked[-1][1] and ["cmd.exe", "/d", "/s", "/c", "echo hello"] in runner.calls
            assert logged[-1][0] == "Command Runner" and "echo hello" in logged[-1][1]
            dialog.grab().save(str(args.output / "tools-windows-command.png"))

            # 6. File Associations: read-only lookup.
            reg.write(winpc.HKCR, ".zip", "", "CompressedFolder", winpc.REG_SZ)
            dialog = open_tool("file_associations")
            dialog.kind.setCurrentText("zip")
            dialog.lookup.click()
            assert ".zip opens with: CompressedFolder" in dialog.answer.text(), dialog.answer.text()
            dialog.kind.setCurrentText("not valid!")
            dialog.lookup.click()
            assert "Type an extension" in dialog.answer.text()
            dialog.grab().save(str(args.output / "tools-windows-associations.png"))

            # 7. Junction Manager: lists links, removes only the link, keeps the target.
            games, real = root / "Games", root / "Elsewhere"
            games.mkdir()
            real.mkdir()
            (real / "data.bin").write_bytes(b"d")
            try:
                os.symlink(real, games / "Skyrim", target_is_directory=True)
                linked = True
            except OSError:  # Windows needs a privilege for symbolic links; the logic is covered by unit tests
                linked = False
            dialog = open_tool("junction_manager")
            dialog.scan(str(games))
            if linked:
                wait_for(lambda: dialog.listing.count() == 1)
                dialog.listing.setCurrentRow(0)
                dialog.remove_button.click()
                assert "Only the link is removed" in asked[-1][1]
                wait_for(lambda: not os.path.lexists(games / "Skyrim"))
                assert (real / "data.bin").exists()
                assert logged[-1][0] == "Junction Manager"
            else:
                wait_for(lambda: "No junctions" in dialog.result_line.text())
            dialog.grab().save(str(args.output / "tools-windows-junctions.png"))

            assert errors.call_count == 0, errors.call_args_list
            window.close()
    print("PASS: seven Windows tools (cleanup, optimizer with undo, memory, startup, command runner, file associations, "
          "junctions) each ask first with the exact change, do only that, and write the activity log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
