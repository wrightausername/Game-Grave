"""Launch with Windows. Changes only the current user's Run entry for the installed Game Grave app.

This is the one start-up entry: Settings > General and the tray menu both use it. Older builds of the tray menu wrote a
second value named "Game Grave"; it is read as on and removed whenever the switch is changed, so the app never starts twice.
"""
from __future__ import annotations

import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "GameGrave"
LEGACY_NAME = "Game Grave"   # written by older tray menus with --minimized


def _registry():
    import winreg
    return winreg


def available() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def reason() -> str:
    if sys.platform != "win32":
        return "Only available on Windows."
    if not getattr(sys, "frozen", False):
        return "Only available in the installed Game Grave app."
    return ""


def command() -> str:
    return '"' + sys.executable + '"'


def _ours(value) -> bool:
    return isinstance(value, str) and (value == command() or value == command() + " --minimized")


def _read(reg, name):
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            value, _kind = reg.QueryValueEx(key, name)
    except OSError:
        return None
    return value


def has_legacy(registry=None) -> bool:
    """True when an older tray menu's second entry for this same Game Grave is still in the Run key."""
    if not available() and registry is None:
        return False
    return _ours(_read(registry or _registry(), LEGACY_NAME))


def is_enabled(registry=None) -> bool:
    if not available() and registry is None:
        return False
    reg = registry or _registry()
    return _read(reg, VALUE_NAME) == command() or _ours(_read(reg, LEGACY_NAME))


def set_enabled(on: bool, registry=None) -> None:
    """Raises OSError when Windows refuses the change."""
    if not available() and registry is None:
        raise OSError(reason())
    reg = registry or _registry()
    with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
        if on:
            reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command())
        else:
            try:
                reg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        if _ours(_read(reg, LEGACY_NAME)):        # only our own old entry; another program's value is left alone
            try:
                reg.DeleteValue(key, LEGACY_NAME)
            except FileNotFoundError:
                pass
