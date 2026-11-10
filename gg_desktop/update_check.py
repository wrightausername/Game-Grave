"""Manual "Check for Updates" for Settings.

Runs only when the owner presses the button. It asks the GitHub releases list whether a newer preview
installer exists and reports it in words. It downloads nothing and installs nothing; the separate
GameGrave-Updater.exe (or the releases page) does that, after its own confirmation.
"""
from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

REPO = "wrightausername/Game-Grave"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
SETUP_NAME = "GameGrave-Crimson-Preview-Setup.exe"
SUM_NAME = "GameGrave-Crimson-Preview-Setup.sha256"
UPDATER_NAME = "GameGrave-Updater.exe"
MAX_SETUP_BYTES = 600 * 1024 * 1024


class UpdateCheckError(Exception):
    pass


def state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "Game Grave Updater"


def installed_tag() -> str:
    """The build the updater last installed. Empty when the updater never installed one."""
    try:
        data = json.loads((state_dir() / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    value = data.get("installed_tag") if isinstance(data, dict) else ""
    return value if isinstance(value, str) else ""


def find_token() -> str:
    for name in ("GG_UPDATE_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    try:
        return (state_dir() / "token.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _open(url: str, headers: dict):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20)


def list_releases(token: str = "", opener=None) -> list:
    headers = {"User-Agent": "GameGrave/1", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        response = (opener or _open)(API, headers)
        body = response.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as problem:
        if problem.code in (401, 403, 404):
            raise UpdateCheckError("GitHub would not show the preview builds (error %d). They are private drafts, "
                                   "so the Updater's GitHub token button is needed." % problem.code)
        raise UpdateCheckError("GitHub answered with error %d." % problem.code)
    except (urllib.error.URLError, OSError, http.client.HTTPException) as problem:
        raise UpdateCheckError("Could not reach GitHub: %s" % getattr(problem, "reason", problem))
    try:
        data = json.loads(body.decode("utf-8"))
    except ValueError:
        raise UpdateCheckError("GitHub sent an answer that could not be read.")
    if not isinstance(data, list):
        raise UpdateCheckError("GitHub sent an unexpected answer.")
    return data


def newest_build(releases: list) -> dict | None:
    """Newest release that carries both the installer and its checksum file."""
    best = None
    for item in releases:
        if not isinstance(item, dict):
            continue
        assets = {a.get("name"): a for a in item.get("assets") or [] if isinstance(a, dict)}
        setup = assets.get(SETUP_NAME)
        size = setup.get("size") if setup else None
        if not setup or SUM_NAME not in assets or type(size) is not int or not 0 < size <= MAX_SETUP_BYTES:
            continue
        tag = str(item.get("tag_name") or "")
        created = str(item.get("created_at") or "")
        if tag and (best is None or created > best["created"]):
            best = {"tag": tag, "created": created, "megabytes": size / (1024 * 1024)}
    return best


def describe(build: dict | None, installed: str) -> tuple[str, str]:
    """(kind, sentence): none / current / available / unknown."""
    if build is None:
        return "none", "No preview build with an installer was found."
    size = "%.0f MB" % build["megabytes"]
    if installed and installed == build["tag"]:
        return "current", "You have the newest build (%s)." % build["tag"]
    if installed:
        return "available", "Newer build available: %s (%s). Installed by the Updater: %s." % (build["tag"], size, installed)
    return "unknown", "Newest build: %s (%s). This PC has no record of which build is installed, so open the Updater to compare." % (build["tag"], size)


def check(opener=None) -> tuple[str, str]:
    return describe(newest_build(list_releases(find_token(), opener)), installed_tag())


def updater_path(app_folder: Path | None = None) -> Path | None:
    for folder in (app_folder, state_dir()):
        if folder and (Path(folder) / UPDATER_NAME).is_file():
            return Path(folder) / UPDATER_NAME
    return None
