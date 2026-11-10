"""Nexus Mods hand-off for Squad Sync: sign in with your own Nexus API key and, with Premium, fetch missing mods.

What is real, and what is not:
* Nexus lets a program act for you only with your own API key (nexusmods.com/settings/api-keys) or a login that Nexus
  has registered for that program, as it has for Wabbajack. Game Grave has no such registration yet, so it uses your key.
  The key is kept in Game Grave's own folder (encrypted for your Windows account where Windows allows it) and is only
  ever sent to api.nexusmods.com.
* Premium accounts can ask Nexus for a direct download link. Free accounts cannot: Nexus requires their website's own
  "Slow download" button, so for them Game Grave opens the mod's Files page instead.
* A download goes into your Mod Organizer 2 downloads folder (or a Game Grave folder) as a NEW file. Nothing is ever
  overwritten and nothing is installed; Mod Organizer 2 shows the file in its Downloads tab for you to install.
* Nothing runs by itself. Every request starts from a button press, one mod after another, never in a background loop.

Pure Python (no Qt); network access goes through an injectable opener so every rule is unit tested.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

API = "https://api.nexusmods.com/v1"
KEY_PAGE = "https://www.nexusmods.com/settings/api-keys"
APP_NAME = "Game Grave"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 4 * 1024 ** 3
CHUNK = 256 * 1024
GAME_ID = re.compile(r"^[a-z0-9_]{1,40}$")
NEXUS_REF = re.compile(r"^([a-z0-9_]{1,40})/(\d{1,9})$")
DOWNLOAD_HOSTS = ("nexus-cdn.com", "nexusmods.com")
BATCH = 10                       # mods fetched per press, to stay far inside Nexus's hourly request limit


class NexusError(Exception):
    pass


@dataclass
class Account:
    name: str
    premium: bool


@dataclass
class FileChoice:
    file_id: int
    name: str
    version: str
    size_kb: int


# ------------------------------------------------------------------ references that travel in a squad code
def clean_ref(text) -> str:
    """'skyrimspecialedition/266' or ''. Anything else is dropped, never guessed."""
    text = str(text or "").strip().lower()
    return text if NEXUS_REF.match(text) else ""


def mod_page(ref: str) -> str | None:
    match = NEXUS_REF.match(clean_ref(ref))
    return f"https://www.nexusmods.com/{match.group(1)}/mods/{match.group(2)}?tab=files" if match else None


def read_meta(path: Path) -> str:
    """The Nexus reference MO2 recorded in a mod folder's meta.ini (modid and gameName), or ''."""
    try:
        if path.stat().st_size > 200_000:
            return ""
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return ""
    values = {}
    for line in lines:
        key, found, value = line.partition("=")
        if found and key.strip().casefold() in ("modid", "gamename"):
            values[key.strip().casefold()] = value.strip()
    if not values.get("modid", "").isdigit() or int(values["modid"]) <= 0:
        return ""
    return clean_ref(f"{values.get('gamename', '')}/{values['modid']}")


# ------------------------------------------------------------------ the saved key
def key_path(root: Path | None = None) -> Path:
    if root is None:
        import core
        root = core.config_dir() / "nexus"
    return Path(root) / "key.json"


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    source = Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = Blob()
    function = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    ok = function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError("Windows would not protect the key")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def save_key(key: str, root: Path | None = None, *, protector: Callable | None = None) -> str:
    """Store the key. Returns how it was kept: 'windows' (encrypted for this account) or 'file' (plain, owner-only)."""
    key = (key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9+/=_\-]{16,400}", key):
        raise NexusError("That does not look like a Nexus API key.")
    path = key_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    protect = protector if protector is not None else (_dpapi if os.name == "nt" else None)
    how, stored = "file", key.encode("utf-8")
    if protect is not None:
        try:
            stored, how = protect(stored, True), "windows"
        except OSError as problem:
            raise NexusError(f"Windows would not encrypt the key, so Game Grave did not save it: {problem}")
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps({"how": how, "key": base64.b64encode(stored).decode("ascii")}), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    os.replace(temp, path)
    return how


def load_key(root: Path | None = None, *, protector: Callable | None = None) -> str:
    try:
        data = json.loads(key_path(root).read_text(encoding="utf-8"))
        raw = base64.b64decode(data["key"])
        if data.get("how") == "windows":
            raw = (protector if protector is not None else _dpapi)(raw, False)
        return raw.decode("utf-8")
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def forget_key(root: Path | None = None) -> bool:
    try:
        key_path(root).unlink()
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ talking to Nexus
def _headers(key: str) -> dict:
    return {"apikey": key, "Application-Name": APP_NAME, "Application-Version": "preview",
            "User-Agent": f"{APP_NAME}/preview", "Accept": "application/json"}


def _get_json(path: str, key: str, opener=None):
    request = urllib.request.Request(API + path, headers=_headers(key))
    try:
        with (opener or urllib.request.urlopen)(request, timeout=20) as response:
            raw = response.read(MAX_JSON_BYTES + 1)
    except urllib.error.HTTPError as problem:
        if problem.code in (401, 403):
            raise NexusError("Nexus did not accept that. The key may be wrong, or this needs a Premium account.") from None
        if problem.code == 429:
            raise NexusError("Nexus says too many requests were made. Wait an hour and try again.") from None
        if problem.code == 404:
            raise NexusError("Nexus has no such mod or file.") from None
        raise NexusError(f"Nexus answered with an error ({problem.code}).") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise NexusError("Could not reach Nexus. Check your connection.") from None
    if len(raw) > MAX_JSON_BYTES:
        raise NexusError("Nexus sent back more than expected, so Game Grave ignored it.")
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise NexusError("Nexus sent back something Game Grave could not read.") from None


def validate(key: str, opener=None) -> Account:
    data = _get_json("/users/validate.json", key, opener)
    if not isinstance(data, dict) or not str(data.get("name", "")).strip():
        raise NexusError("Nexus did not accept that key.")
    return Account(str(data["name"])[:60], bool(data.get("is_premium")))


def main_file(ref: str, key: str, opener=None) -> FileChoice:
    match = NEXUS_REF.match(clean_ref(ref))
    if not match:
        raise NexusError("That mod has no Nexus reference.")
    game, mod = match.groups()
    data = _get_json(f"/games/{game}/mods/{mod}/files.json?category=main", key, opener)
    files = [f for f in (data.get("files") if isinstance(data, dict) else None) or []
             if isinstance(f, dict) and isinstance(f.get("file_id"), int)]
    if not files:
        raise NexusError("That mod has no main file on Nexus.")
    files.sort(key=lambda f: (bool(f.get("is_primary")), int(f.get("uploaded_timestamp") or 0)), reverse=True)
    top = files[0]
    return FileChoice(int(top["file_id"]), safe_name(str(top.get("file_name") or f"{mod}-{top['file_id']}.zip")),
                      str(top.get("version") or "")[:40], int(top.get("size_kb") or 0))


def download_url(ref: str, file_id: int, key: str, opener=None) -> str:
    """A direct link. Only Premium accounts get one; the host is checked so a surprise address is never followed."""
    match = NEXUS_REF.match(clean_ref(ref))
    if not match:
        raise NexusError("That mod has no Nexus reference.")
    game, mod = match.groups()
    data = _get_json(f"/games/{game}/mods/{mod}/files/{int(file_id)}/download_link.json", key, opener)
    for item in data if isinstance(data, list) else []:
        url = str(item.get("URI", "")) if isinstance(item, dict) else ""
        if trusted_host(url):
            return url
    raise NexusError("Nexus gave no download link. Direct downloads need a Premium account.")


def trusted_host(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in DOWNLOAD_HOSTS)


def safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(name).name).strip(" .")
    return cleaned[:120] or "mod-download.zip"


def download(url: str, folder: Path, name: str, *, expected_kb: int = 0, progress: Callable | None = None,
             opener=None) -> Path:
    """Save to `folder/name` as a NEW file (a numbered name if it exists). Never overwrites. Returns the path."""
    if not trusted_host(url):
        raise NexusError("That download address is not one Game Grave trusts.")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(safe_name(name)).stem, Path(safe_name(name)).suffix
    target, number = folder / safe_name(name), 1
    while target.exists():
        number += 1
        target = folder / f"{stem} ({number}){suffix}"
    part = target.with_name(target.name + ".part")
    limit = min(MAX_DOWNLOAD_BYTES, max(expected_kb * 1024 * 2, 50 * 1024 * 1024)) if expected_kb else MAX_DOWNLOAD_BYTES
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/preview"})
    total = 0
    try:
        with (opener or urllib.request.urlopen)(request, timeout=30) as response, part.open("xb") as out:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise NexusError("The download was larger than Nexus said, so Game Grave stopped it.")
                out.write(chunk)
                if progress:
                    progress(total)
        os.replace(part, target)
    except NexusError:
        _drop(part)
        raise
    except (urllib.error.URLError, OSError, TimeoutError) as problem:
        _drop(part)
        raise NexusError(f"The download did not finish: {problem}") from None
    return target


def _drop(part: Path) -> None:
    """Remove only our own half-finished temporary file."""
    try:
        if part.name.endswith(".part"):
            part.unlink()
    except OSError:
        pass


def downloads_folder(mo2_instance: Path | None, fallback: Path) -> Path:
    """Where fetched files go: the Mod Organizer 2 downloads folder when it can be read, else Game Grave's own."""
    if mo2_instance is not None:
        chosen = ""
        try:
            for line in (Path(mo2_instance) / "ModOrganizer.ini").read_text(encoding="utf-8-sig", errors="replace").splitlines():
                if line.casefold().startswith("download_directory="):
                    chosen = line.split("=", 1)[1].strip().replace("%BASE_DIR%", str(mo2_instance))
        except OSError:
            pass
        return Path(chosen) if chosen else Path(mo2_instance) / "downloads"
    return fallback
