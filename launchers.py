"""Conservative inventory of other launcher installations.

Epic manifest and GOG registry are read-only. Unregistered folder listings are
NOT called uninstalled games. No registry cleanup or launch/uninstall automation.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

Cancel = Callable[[], bool] | None


@dataclass(frozen=True)
class LauncherGame:
    name: str
    launcher: str
    install_path: str
    app_id: str
    reported_bytes: int | None
    status: str


def _ordinary_install(raw) -> Path | None:
    """Reject blank, relative, root, symlink or junctioned launcher locations.

    A missing Epic InstallLocation formerly became Path('.'), which happened
    to exist and incorrectly promoted a bad manifest into an installed game.
    """
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 4096:
        return None
    path = Path(raw.strip())
    if not path.is_absolute() or path == Path(path.anchor):
        return None
    current = path
    try:
        while True:
            info = current.lstat()
            if current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                return None
            parent = current.parent
            if parent == current:
                break
            current = parent
        return path if path.is_dir() else None
    except (OSError, ValueError):
        return None


def epic_games(programdata: Path | None = None, cancel: Cancel = None) -> list[LauncherGame]:
    base = (Path(programdata) if programdata is not None else
            Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')))
    manifests = base / 'Epic' / 'EpicGamesLauncher' / 'Data' / 'Manifests'
    if not manifests.is_dir() or manifests.is_symlink():
        return []
    result = []
    for item in sorted(manifests.glob('*.item'))[:3000]:
        if cancel and cancel():
            raise InterruptedError('Game scan canceled')
        try:
            if item.is_symlink() or item.stat().st_size > 2_000_000:
                continue
            entry = json.loads(item.read_text(encoding='utf-8-sig'))
            if not isinstance(entry, dict):
                continue
            folder = _ordinary_install(entry.get('InstallLocation'))
            if folder is None:
                continue
            name = str(entry.get('DisplayName') or entry.get('AppName') or folder.name)[:170]
            size = entry.get('InstallSize')
            size = int(size) if isinstance(size, (float, int)) and size >= 0 else None
            result.append(LauncherGame(name, 'Epic Games', str(folder),
                                      str(entry.get('AppName') or item.stem), size,
                                      'Install location present; manifest detected'))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return result


def gog_registry(cancel: Cancel = None) -> list[LauncherGame]:
    if os.name != 'nt':
        return []
    try:
        import winreg
    except ImportError:
        return []
    results = []
    for view in (getattr(winreg, 'KEY_WOW64_64KEY', 0), getattr(winreg, 'KEY_WOW64_32KEY', 0)):
        try:
            base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\GOG.com\Games', 0,
                                  winreg.KEY_READ | view)
        except OSError:
            continue
        with base:
            i = 0
            while i < 5000:
                if cancel and cancel():
                    raise InterruptedError('Game scan canceled')
                try:
                    identifier = winreg.EnumKey(base, i)
                    i += 1
                    with winreg.OpenKey(base, identifier) as sub:
                        folder = _ordinary_install(winreg.QueryValueEx(sub, 'path')[0])
                        if folder is None:
                            continue
                        try:
                            name = winreg.QueryValueEx(sub, 'gameName')[0]
                        except OSError:
                            name = folder.name
                        results.append(LauncherGame(str(name), 'GOG', str(folder),
                                                    str(identifier), None,
                                                    'GOG registry entry; installation found'))
                except OSError:
                    break
    unique = {(g.launcher, g.install_path.casefold()): g for g in results}
    return list(unique.values())


def custom_library_folders(roots: list[str], cancel: Cancel = None) -> list[LauncherGame]:
    """Explicit locations selected by the user, labelled unverified."""
    found = []
    for raw in roots[:15]:
        if cancel and cancel():
            raise InterruptedError('Game scan canceled')
        root = _ordinary_install(raw)
        if root is None:
            continue
        try:
            folders = [f for f in root.iterdir() if _ordinary_install(str(f)) is not None]
        except OSError:
            continue
        for folder in folders[:400]:
            found.append(LauncherGame(folder.name, 'Custom library', str(folder),
                                      str(folder), None,
                                      'Folder present; game or installation status not verified'))
    return found


def find_launcher_games(custom_roots=None, cancel: Cancel = None, programdata: Path | None = None):
    found = (epic_games(programdata, cancel) + gog_registry(cancel) +
             riot_games(programdata, cancel) + vendor_registry_games(cancel) +
             blizzard_uninstall_records(cancel) +
             custom_library_folders(custom_roots or [], cancel))
    unique = {(x.launcher, x.install_path.casefold()): x for x in found}
    return sorted(unique.values(), key=lambda g: (g.launcher, g.name.casefold()))


def riot_games(programdata: Path | None = None, cancel: Cancel = None) -> list[LauncherGame]:
    """Read Riot launcher product settings; never walk arbitrary game folders."""
    import re
    base = Path(programdata or os.environ.get('PROGRAMDATA', 'C:/ProgramData'))
    metadata = base / 'Riot Games' / 'Metadata'
    if not metadata.is_dir() or metadata.is_symlink():
        return []
    items = []
    # Riot keeps small product_settings.yaml files under Metadata/<product>/.
    for manifest in sorted(metadata.glob('*/product_settings.yaml'))[:100]:
        if cancel and cancel():
            raise InterruptedError('Launcher scan canceled')
        try:
            if manifest.is_symlink() or manifest.stat().st_size > 150000:
                continue
            data = manifest.read_text(encoding='utf-8-sig', errors='replace')
            values = {}
            for line in data.splitlines():
                match = re.match(r'^([a-zA-Z_]+):\s*[\'\"]?(.*?)[\'\"]?\s*$', line)
                if match:
                    values[match.group(1)] = match.group(2).strip().strip('"\'')
            location = values.get('product_install_full_path')
            install = _ordinary_install(location)
            if install is None:
                continue
            items.append(LauncherGame(values.get('product_display_name') or manifest.parent.name,
                       'Riot Games', str(install), manifest.parent.name, None,
                       'Riot launcher product settings and installation folder found'))
        except (OSError, ValueError):
            continue
    return items


def vendor_registry_games(cancel: Cancel = None) -> list[LauncherGame]:
    """Known Ubisoft and EA Games registry keys, NOT blanket Windows uninstall entries."""
    if os.name != 'nt':
        return []
    try:
        import winreg
    except ImportError:
        return []
    roots = (
        ('Ubisoft Connect', winreg.HKEY_LOCAL_MACHINE,
         r'SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs', ('InstallDir', 'InstallLocation')),
        ('EA', winreg.HKEY_LOCAL_MACHINE,
         r'SOFTWARE\Electronic Arts\EA Games', ('Install Dir', 'InstallDir', 'InstallLocation')),
    )
    results = []
    for launcher, hive, key_path, fields in roots:
        try:
            parent = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        except OSError:
            continue
        with parent:
            for i in range(500):
                if cancel and cancel():
                    raise InterruptedError('Launcher scan canceled')
                try:
                    name = winreg.EnumKey(parent, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(parent, name) as sub:
                        install = None
                        for field in fields:
                            try:
                                install = winreg.QueryValueEx(sub, field)[0]
                                break
                            except OSError:
                                pass
                        if not isinstance(install, str):
                            continue
                        path = _ordinary_install(install)
                        if path is None:
                            continue
                        results.append(LauncherGame(name, launcher, str(path), name, None,
                                        'Launcher registry record; game name may need verification'))
                except OSError:
                    continue
    return results


def is_blizzard_install_metadata(name: str, publisher: str) -> bool:
    """Only credible installed Blizzard game entries, never the Battle.net client."""
    name = name.strip().casefold() if isinstance(name, str) else ""
    publisher = publisher.strip().casefold() if isinstance(publisher, str) else ""
    if (not name or len(name) > 170 or
            "blizzard entertainment" not in publisher or
            any(value in name for value in ("battle.net", "battle net", "launcher",
                                            "agent", "update manager"))):
        return False
    # A verified publisher alone does not prove this is a game; use a narrow
    # recognizable Blizzard product prefix instead of blindly mapping software.
    names = (
        "diablo", "overwatch", "world of warcraft", "warcraft iii",
        "warcraft ii", "starcraft", "heroes of the storm",
        "hearthstone", "warcraft rumble",
    )
    return name.startswith(names)


def blizzard_uninstall_records(cancel: Cancel = None) -> list[LauncherGame]:
    """Conservative read-only fallback for installed Battle.net/Blizzard games.

    Battle.net's Agent product.db is a private binary format; don't pretend to
    parse it. Windows installed-app publisher+known game name+existing ordinary
    InstallLocation is useful positive evidence, never proof of a missing game.
    No generic Windows uninstall program is included in the game inventory.
    """
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    keys = (
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    results = []
    for hive, parent_path in keys:
        if cancel and cancel():
            raise InterruptedError("Launcher scan canceled")
        try:
            parent = winreg.OpenKey(hive, parent_path, 0, winreg.KEY_READ)
        except OSError:
            continue
        with parent:
            for i in range(4500):
                if cancel and cancel():
                    raise InterruptedError("Launcher scan canceled")
                try:
                    name = winreg.EnumKey(parent, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(parent, name, 0, winreg.KEY_READ) as sub:
                        def text(field):
                            try:
                                value = winreg.QueryValueEx(sub, field)[0]
                                return value if isinstance(value, str) else ""
                            except OSError:
                                return ""
                        display = text("DisplayName")
                        publisher = text("Publisher")
                        if not is_blizzard_install_metadata(display, publisher):
                            continue
                        location = text("InstallLocation")
                        folder = _ordinary_install(location)
                        if folder is None:
                            continue
                        results.append(LauncherGame(
                            display[:170], "Battle.net", str(folder), name,
                            None, "Blizzard publisher and Windows installation record; "
                                  "game launch status not independently verified"))
                except OSError:
                    continue
    return results
