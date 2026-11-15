"""Download and install a Game Grave update from inside the app (Settings, or the pop-up after the launch check).
Two questions: one before downloading, one before installing. Logged as update_download and update_install.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

from gg_desktop import update_install_core as core


def _updater():
    from updater import gg_updater
    return gg_updater


def start(window):
    """Ask, then find the newest build, download it and check its SHA-256 in the background."""
    if getattr(window, "_update_busy", False):
        window.info("Already downloading", "The update is still downloading. You will be told when it is ready.")
        return
    up = _updater()
    window.status.setText("Asking GitHub for the newest build...")

    def find(progress=None):
        try:
            token = up.find_token()
            return ("ok", up.pick_release(up.list_releases(token)))
        except Exception as problem:
            return ("error", str(problem) or type(problem).__name__)

    def found(result):
        status, release = result
        if status == "error":
            window.error("Update not downloaded", release)
            return
        if not release:
            window.info("No update found", "No preview build with an installer and its checksum was found.")
            return
        size = release["setup"]["size"]
        if not window.confirm("Download the update?", core.download_question(release["tag"], size / 1048576)):
            window.status.setText("Update not downloaded.")
            return
        download(window, release)
    window.job(find, found, error_title="Update not downloaded")


def download(window, release):
    from core import config_dir, log_event
    up = _updater()
    folder = Path(config_dir()) / "updates"
    folder.mkdir(parents=True, exist_ok=True)
    need = release["setup"]["size"] * 1.2
    if shutil.disk_usage(folder).free < need:
        window.error("Not enough space", "The update needs about %.0f MB free on the drive that holds Game Grave's data."
                     % (need / 1048576))
        return
    window._update_busy = True

    def work(progress):
        token = up.find_token()
        expected = up.fetch_checksum(release, token)
        path = up.download_setup(release, token, folder, expected,
                                 lambda d, t: progress(int(d * 100 / max(1, t)), core.progress_text(d, t)))
        return str(path), expected

    def moved(percent, words):          # the job's progress signal carries (percent, sentence)
        window.status.setText(words)

    def done(result):
        window._update_busy = False
        path, digest = result
        log_event("update_download", f"Downloaded and verified Game Grave {release['tag']}", path=path,
                  size_bytes=release["setup"]["size"], result="Verified SHA-256 " + digest, source="Settings")
        window._update_ready = (path, release["tag"])
        window.status.setText(f"Game Grave {release['tag']} is downloaded and verified.")
        from gg_desktop import comfort
        comfort.notify(window, "Update ready", f"Game Grave {release['tag']} is downloaded and matches its published "
                       "SHA-256. Install it when you are ready.", "good", "Settings",
                       action=("Install now", lambda: install_now(window)))
        _sync_settings(window)

    def guarded(progress):
        try:
            return work(progress)
        except BaseException:
            window._update_busy = False   # app.job shows the reason; the next press can try again
            raise
    window.job(guarded, done, error_title="Update not downloaded", progress=moved)
    window.status.setText("Downloading the update...")


def install_now(window):
    ready = getattr(window, "_update_ready", None)
    if not ready or not Path(ready[0]).is_file():
        window.info("No update downloaded", "Download the update first (Settings > Check for Updates).")
        return
    path, tag = ready
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current scan or clean-up first, then install the update.")
        return
    if not window.confirm("Install the update?", core.install_question(tag)):
        return
    from core import log_event
    up = _updater()
    exe = sys.executable if getattr(sys, "frozen", False) else ""
    state = str(up.state_dir() / "state.json")
    script = core.install_script(path, tag, state, exe)
    if os.name != "nt":
        window.error("Not on Windows", "The installer runs on Windows only.")
        return
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-EncodedCommand", encoded], creationflags=flags, close_fds=True)
    except OSError as exc:
        window.error("Installer not started", str(exc))
        return
    log_event("update_install", f"Started the verified installer for Game Grave {tag} ({' '.join(core.INSTALL_ARGS)})",
              path=path, source="Settings")
    from gg_desktop import comfort
    comfort.quit_app(window)


def _sync_settings(window):
    from shiboken6 import isValid
    button = getattr(window, "settings_update_get", None)
    if button is not None and isValid(button):
        ready = getattr(window, "_update_ready", None)
        button.setText("Install now" if ready else "Download and install")
        button.setVisible(True)


def primary(window):
    """The Settings button: download first, install once downloaded."""
    if getattr(window, "_update_ready", None) and Path(window._update_ready[0]).is_file():
        install_now(window)
    else:
        start(window)
