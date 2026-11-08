"""Launch with Windows. Changes only the current user's Run entry for the installed Game Grave app."""
from __future__ import annotations

import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "GameGrave"


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


def is_enabled(registry=None) -> bool:
    if not available() and registry is None:
        return False
    reg = registry or _registry()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            value, _kind = reg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return isinstance(value, str) and value == command()


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
