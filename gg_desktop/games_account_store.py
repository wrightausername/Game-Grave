"""Games-only private account, library and session files.

Windows credentials are encrypted with DPAPI for the current Windows user.
Other platforms can use session-only connections; no plaintext token fallback.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
import threading

from gg_desktop.game_artwork import _atomic
from gg_desktop import game_artwork as _art_storage
from core import _has_reparse_component, _settings_no_duplicate_keys

PROVIDERS = ("Steam", "Epic Games", "EA", "GOG")
LIMIT = 16 * 1024 * 1024
_lock = threading.RLock()
_session_secrets = {}


def artwork_dir():
    return _art_storage.artwork_dir()


def read_document(name, default):
    path = artwork_dir()/name
    try:
        if (_has_reparse_component(path) or not path.is_file() or path.stat().st_size > LIMIT):
            return default
        with path.open("rb") as stream:
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            return default
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_settings_no_duplicate_keys)
        return value if isinstance(value, dict) else default
    except (OSError, ValueError, UnicodeError, RecursionError):
        return default


def write_document(name, value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    if len(raw) > LIMIT:
        raise ValueError("The Games library exceeds its local storage limit.")
    with _lock:
        _atomic(artwork_dir()/name, raw)
        if os.name != "nt":
            os.chmod(artwork_dir()/name, 0o600)


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(raw, decrypt=False):
    if os.name != "nt":
        raise ValueError("Saved account connections use Windows account encryption.")
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source = _Blob(len(raw), buffer)
    result = _Blob()
    api = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = api.CryptUnprotectData if decrypt else api.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ValueError("Windows could not unlock this account connection. Connect it again.")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


def save_secret(provider, value):
    if provider not in PROVIDERS or not isinstance(value, dict):
        raise ValueError("Unsupported account provider.")
    raw = json.dumps(value, separators=(",", ":")).encode()
    if len(raw) > 512 * 1024:
        raise ValueError("The account connection exceeded its size limit.")
    if os.name != "nt":
        with _lock:
            _session_secrets[(str(artwork_dir()), provider)] = raw
        return
    encrypted = base64.b64encode(_crypt(raw)).decode("ascii")
    with _lock:
        data = read_document("connections.private.json", {})
        data[provider] = encrypted
        write_document("connections.private.json", data)


def load_secret(provider):
    if os.name != "nt":
        with _lock:
            return json.loads(_session_secrets.get((str(artwork_dir()), provider), b"{}"))
    value = read_document("connections.private.json", {}).get(provider)
    if not isinstance(value, str) or len(value) > 800000:
        return {}
    try:
        data = json.loads(_crypt(base64.b64decode(value, validate=True), decrypt=True))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError, UnicodeError):
        return {}


def update_secret_if_current(provider, value, connection_id):
    """Keep a rotated token across tab changes without resurrecting sign-out."""
    with _lock:
        current = load_secret(provider)
        if (not current or not connection_id or current.get("connection_id") != connection_id
                or current.get("account_id") != value.get("account_id")):
            return False
        save_secret(provider, value)
        return True


def forget(provider):
    with _lock:
        _session_secrets.pop((str(artwork_dir()), provider), None)
        private = read_document("connections.private.json", {})
        private.pop(provider, None)
        if os.name == "nt":
            write_document("connections.private.json", private)
        snapshots = read_document("libraries.json", {})
        snapshots.pop(provider, None)
        write_document("libraries.json", snapshots)


def load_snapshots():
    data = read_document("libraries.json", {})
    return {key: value for key, value in data.items() if key in PROVIDERS and isinstance(value, dict)
            and isinstance(value.get("items"), list) and len(value["items"]) <= 10000
            and value.get("provider") == key
            and load_secret(key).get("account_id") == value.get("account_id")}


def save_snapshot(provider, snapshot):
    if provider not in PROVIDERS or not isinstance(snapshot, dict) or snapshot.get("provider") != provider or len(snapshot.get("items", [])) > 10000:
        raise ValueError("Unsupported library snapshot.")
    with _lock:
        data = load_snapshots()
        data[provider] = snapshot
        write_document("libraries.json", data)
