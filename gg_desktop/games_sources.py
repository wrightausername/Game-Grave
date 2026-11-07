"""Games-only launcher presentation and additional registered installations.

The accepted shared inventory and the other tabs are never modified here.
"""
from __future__ import annotations

from gg_desktop.library_models import launcher_bucket as shared_bucket
from gg_desktop.models import _path_key, merge_games
from launchers import LauncherGame, _ordinary_install


LAUNCHERS = (
    ("Steam", "steam", "#13a7ef"), ("Epic", "epic", "#e2e4e7"),
    ("EA", "ea", "#fa284a"), ("Rockstar", "rockstar", "#ffc329"),
    ("Battle.net", "battlenet", "#3ba9ed"), ("Ubisoft", "ubisoft", "#d9e2f0"),
    ("Xbox (PC)", "xbox", "#33d34d"), ("GOG", "gog", "#bc64ee"),
    ("Other", "plus", "#dadfe6"),
)


def launcher_bucket(value):
    if " / " not in value and "rockstar" in value.casefold():
        return "Rockstar"
    return shared_bucket(value)


def launcher_symbol(value):
    return next(symbol for bucket, symbol, _ in LAUNCHERS if bucket == launcher_bucket(value))


def combine_games(existing, additional):
    """Keep accepted identities; count a registered install directory once."""
    rows = list(existing)
    seen = {_path_key(game.install_path) for game in rows}
    for game in merge_games([], additional):
        key = _path_key(game.install_path)
        if key not in seen:
            rows.append(game)
            seen.add(key)
    return sorted(rows, key=lambda game: (game.name.casefold(), game.key))


def registered_games(*, registry=None, canceled=lambda: False):
    """Read only game-specific Rockstar / legacy EA keys, in both views.

    No broad uninstall sweep, folder-name guessing, registry writes or guessed
    launch protocols. A missing/redirected installation is not a game.
    """
    if registry is None:
        try:
            import winreg as registry
        except ImportError:
            return []
    roots = (("Rockstar Games", r"SOFTWARE\Rockstar Games"),
             ("EA", r"SOFTWARE\EA Games"),
             ("EA", r"SOFTWARE\Electronic Arts\EA Games"))
    found = {}
    for launcher, key_path in roots:
        for hive in (registry.HKEY_LOCAL_MACHINE, registry.HKEY_CURRENT_USER):
            for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
                if canceled():
                    return []
                try:
                    parent = registry.OpenKey(hive, key_path, 0, registry.KEY_READ | view)
                except OSError:
                    continue
                with parent:
                    for index in range(300):
                        if canceled():
                            return []
                        try:
                            name = registry.EnumKey(parent, index)
                        except OSError:
                            break
                        if any(word in name.casefold() for word in ("launcher", "social club", "socialclub", "online services")):
                            continue
                        try:
                            with registry.OpenKey(parent, name) as child:
                                for field in ("InstallFolder", "Install Dir", "InstallDir", "InstallLocation"):
                                    try:
                                        path = _ordinary_install(registry.QueryValueEx(child, field)[0])
                                    except OSError:
                                        continue
                                    if path is not None:
                                        found[_path_key(str(path))] = LauncherGame(
                                            name[:170], launcher, str(path), name[:170], None,
                                            "Game-specific launcher registry record and existing installation directory")
                                        break
                        except OSError:
                            continue
    return list(found.values())
