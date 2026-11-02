"""Windows integration checks for real process enumeration and game deferral.

Safe on CI: launches a copied system cmd.exe inside a disposable games folder.
Never touches a real game installation or deletes any files.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from performance_guard import GameActivityDetector


@unittest.skipUnless(os.name == "nt", "Windows process integration test")
@unittest.skipUnless(importlib.util.find_spec("psutil"), "psutil required")
class WindowsGameProcessIntegrationTests(unittest.TestCase):
    def test_detects_real_running_windowed_executable_under_game_library(self):
        source = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        if not Path(source).is_file():
            self.skipTest("Windows command interpreter unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Games" / "DisposableTestGame"
            game_dir.mkdir(parents=True)
            exe = game_dir / "GameProcess.exe"
            shutil.copyfile(source, exe)
            proc = subprocess.Popen(
                [str(exe), "/c", "ping -n 15 127.0.0.1 >NUL"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                detector = GameActivityDetector(
                    refresh_seconds=0.1, fullscreen=lambda: False)
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and proc.poll() is None:
                    if detector.active():
                        break
                    time.sleep(0.1)
                else:
                    self.fail("Running disposable windowed game-like EXE not detected")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=4)


if __name__ == "__main__":
    unittest.main()
