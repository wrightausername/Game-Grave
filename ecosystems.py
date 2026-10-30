"""Additional game/mod ecosystem presence detectors. Detection-only, no mutation.

Path heuristics intentionally report 'found storage', never 'unused mods'. Every
location has a specific label and conservative advice. No recursive disk search.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from core import ModFolder
from mod_sources import _safe_folder, _measure, _children, MAX_FINDINGS

Cancel = Callable[[], bool] | None


def known_locations(home: Path | None = None, env: dict | None = None) -> list[tuple[str, Path, str, str]]:
    env = dict(os.environ if env is None else env)
    home = Path.home() if home is None else Path(home)
    appdata = Path(env.get("APPDATA", home / "AppData" / "Roaming"))
    local = Path(env.get("LOCALAPPDATA", home / "AppData" / "Local"))
    docs = home / "Documents"
    # WoW launcher default locations; custom installations still need user-added roots.
    program_files = Path(env.get("PROGRAMFILES(X86)", env.get("ProgramFiles(x86)", "C:/Program Files (x86)")))
    wow = program_files / "World of Warcraft"
    wow_locations = []
    for variant in ("_retail_", "_classic_", "_classic_era_", "_ptr_"):
        wow_locations.extend([
            ("World of Warcraft", wow / variant / "Interface" / "AddOns",
             "Installed WoW addons", "Addons may be enabled; manage them in the game or addon manager."),
            ("World of Warcraft", wow / variant / "WTF" / "Account",
             "Saved addon settings protected", "WoW character, account and addon settings must be preserved."),
        ])
    return wow_locations + [
        ("Thunderstore", appdata / "Thunderstore Mod Manager" / "DataFolder", "Managed profiles and downloaded mods", "Use Thunderstore to manage installed profiles; do not remove active dependencies."),
        ("r2modman", appdata / "r2modmanPlus-local", "Mod manager profile storage", "Profiles can contain active mods and configurations. Inspect in r2modman first."),
        ("Prism Launcher", appdata / "PrismLauncher" / "instances", "Minecraft instances / worlds protected", "Instances may contain unique Minecraft worlds and saves; never automatically clean."),
        ("Modrinth", appdata / "ModrinthApp" / "profiles", "Minecraft profiles / worlds protected", "Do not delete Minecraft instances or worlds without backups."),
        ("CurseForge", home / "curseforge" / "minecraft" / "Instances", "Minecraft modpacks / worlds protected", "Installed packs may contain unique worlds. Path could be customized."),
        ("CurseForge", docs / "CurseForge" / "Minecraft" / "Instances", "Minecraft instances / worlds protected", "Installed packs may contain unique worlds. Path could be customized."),
        ("Baldur's Gate 3", local / "Larian Studios" / "Baldur's Gate 3" / "Mods", "Local game mods", "Mod files may be active and referenced by load orders."),
        ("Baldur's Gate 3", local / "Larian Studios" / "Baldur's Gate 3" / "PlayerProfiles", "Player profiles / saves protected", "Player profiles may contain unique save data; do not clean automatically."),
        ("The Sims 4", docs / "Electronic Arts" / "The Sims 4" / "Mods", "Custom content", "Custom content may be irreplaceable; do not assume unused."),
        ("The Sims 4", docs / "Electronic Arts" / "The Sims 4" / "saves", "Game saves protected", "Always preserve Sims save files."),
        ("Wabbajack", local / "Wabbajack" / "downloaded_mod_lists", "Modlist metadata", "A modlist's download archives and setup files may be needed for rebuilding."),
        ("ESO", docs / "Elder Scrolls Online" / "live" / "AddOns", "Installed MMO addons", "Active ESO addon folder; never automatically remove or equate age with inactivity."),
        ("ESO", docs / "Elder Scrolls Online" / "live" / "SavedVariables", "Addon settings protected", "SavedVariables may include irreplaceable character settings; do not delete."),
        ("ESO", docs / "Elder Scrolls Online" / "liveeu" / "AddOns", "Installed MMO addons", "EU server addons may be active; review in Minion / ESO first."),
        ("ESO", docs / "Elder Scrolls Online" / "liveeu" / "SavedVariables", "Addon settings protected", "Preserve EU server addon settings."),
        ("ESO", docs / "Elder Scrolls Online" / "pts" / "AddOns", "Test server addons", "An apparently old PTS addon may be needed next test cycle."),
        ("Minion", appdata / "Minion", "Addon-manager configuration protected", "Manager setup and enabled addon locations can be customized."),
        ("RedM", local / "RedM" / "RedM.app" / "data", "Multiplayer client files", "May include active content, launcher runtime data and downloads; never clean automatically."),
        ("War Thunder", docs / "My Games" / "WarThunder", "User content and game settings", "Custom content and settings are version-dependent; review in game first."),
        ("LOTRO", docs / "The Lord of the Rings Online" / "Plugins", "MMO plugins", "Plugin settings or custom layouts may be needed; keep by default."),
        ("LOTRO", docs / "The Lord of the Rings Online" / "ui", "MMO custom interface", "Custom UI skins may be active; keep by default."),
        ("SWTOR", appdata / "SWTOR" / "swtor" / "settings", "MMO settings protected", "User interface layouts and game settings may be irreplaceable."),
        ("Guild Wars 2", docs / "Guild Wars 2", "MMO local tools and settings", "May contain active addon and configuration data; don't remove by age alone."),
        ("RuneLite", home / ".runelite", "RuneLite plugins / configuration", "Plugin data and RuneLite settings can be active; preserve by default."),
        ("Path of Exile", docs / "My Games" / "Path of Exile", "Item filters and settings", "Player filters and account preferences are important settings."),
        ("FiveM", local / "FiveM" / "FiveM.app" / "data" / "cache", "Runtime cache: review", "Do not touch while the client is running; cache removal can require redownloads."),
    ]


def find_ecosystem_storage(extra_steam_roots=None, custom_roots=None, cancel: Cancel = None,
                           home: Path | None = None, env: dict | None = None) -> list[ModFolder]:
    results = []
    seen: set[str] = set()
    for source, folder, status, advice in known_locations(home, env):
        if cancel and cancel():
            raise InterruptedError("Mod scan canceled")
        key = str(folder).casefold()
        if key in seen or not _safe_folder(folder):
            continue
        seen.add(key)
        row = _measure(folder.name, folder, source, status, advice,
                       indicators=("Known storage location", "Read-only inspection"),
                       item_count=len(_children(folder)), cancel=cancel)
        if row:
            results.append(row)
        if len(results) >= MAX_FINDINGS:
            break
    return results


def find_steam_staging(extra_steam_roots=None, games=None, cancel: Cancel = None) -> list[ModFolder]:
    from core import _steam_roots, steam_libraries
    results = []
    for library in steam_libraries(_steam_roots(extra_steam_roots)):
        steamapps = library / "steamapps"
        for folder_name, source, status, note in [
            ("shadercache", "Steam shader cache", "Shader cache: regenerates", "Steam can recreate shaders. Deletion may trigger reprocessing and stutter. Check the game and Steam first."),
            ("downloading", "Steam downloads", "Download staging: active/unknown", "Might contain active or interrupted Steam updates. Never remove during downloads."),
            ("temp", "Steam downloads", "Temporary staging: review", "Could contain active installation data. Inspect before any cleanup."),
        ]:
            root = steamapps / folder_name
            if not _safe_folder(root):
                continue
            for item in _children(root)[:250]:
                if cancel and cancel():
                    raise InterruptedError("Mod scan canceled")
                if len(results) >= MAX_FINDINGS:
                    return results
                row = _measure(item.name, item, source, status, note,
                               indicators=(folder_name, "Steam library"), cancel=cancel)
                if row:
                    results.append(row)
    return results



def find_installed_game_content(games, cancel: Cancel = None) -> list[ModFolder]:
    """Probe only confirmed install directories for known optional game content."""
    result = []
    for game in games:
        if cancel and cancel():
            raise InterruptedError("Mod scan canceled")
        name = game.name.casefold()
        if "war thunder" in name:
            names = ("UserSkins", "UserSights", "UserMissions", "UserHangar", "sound")
            source = "War Thunder"
        elif "world of warcraft" in name:
            names = ("_retail_/Interface/AddOns", "_classic_/Interface/AddOns")
            source = "World of Warcraft"
        else:
            continue
        for suffix in names:
            folder = Path(game.install_path) / suffix
            if not _safe_folder(folder):
                continue
            row = _measure(folder.name, folder, source, "Installed game: custom content",
                           "Game is installed. Custom files may be active; never remove by age alone.",
                           indicators=("Known game install", suffix), cancel=cancel)
            if row:
                result.append(row)
    return result
