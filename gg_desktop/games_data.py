"""Games-only filtering and user-requested launch actions. No Qt or side effects."""
from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import quote

from core import _has_reparse_component, read_vdf


def filtered_games(games, query="", launcher="All launchers", sort="Largest known size"):
    words = query.casefold().split()
    rows = [g for g in games if (launcher == "All launchers" or g.launcher == launcher)
            and all(word in (g.name + " " + g.launcher + " " + g.install_path).casefold() for word in words)]
    tie = lambda g: (g.name.casefold(), g.launcher.casefold(), g.key)
    if sort == "Name A to Z":
        rows.sort(key=tie)
    elif sort == "Launcher":
        rows.sort(key=lambda g: (g.launcher.casefold(), *tie(g)))
    elif sort in ("Recently played", "Oldest played"):
        rows.sort(key=lambda g: (g.last_played_at is None,
                                (g.last_played_at or 0) * (-1 if sort == "Recently played" else 1), *tie(g)))
    else:
        rows.sort(key=lambda g: (g.size_bytes is None,
                                (g.size_bytes or 0) * (-1 if sort == "Largest known size" else 1), *tie(g)))
    return rows


def install_directory(game):
    path = Path(game.install_path)
    if ("open_folder" not in game.capabilities or not path.is_absolute() or path == Path(path.anchor)
            or not path.is_dir() or _has_reparse_component(path)):
        raise ValueError("This installation is missing, redirected or unverified. Run Scan PC again.")
    return path


def launch_uri(game):
    if "open_folder" not in game.capabilities or len(game.claimed_by) != 1:
        return ""
    ident = str(game.app_id or "")
    if game.launcher == "Steam" and re.fullmatch(r"[1-9][0-9]{0,9}", ident):
        return "steam://rungameid/" + ident
    if game.launcher == "Epic Games" and re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", ident):
        return "com.epicgames.launcher://apps/" + quote(ident, safe="") + "?action=launch&silent=true"
    return ""


def steam_install_current(game, steam_records):
    if game.launcher != "Steam" or not re.fullmatch(r"[1-9][0-9]{0,9}", str(game.app_id or "")):
        return False
    try:
        path = install_directory(game)
        records = [g for g in steam_records if str(g.app_id) == game.app_id
                   and os.path.normcase(os.path.abspath(g.install_path)) == os.path.normcase(os.path.abspath(path))]
        if len(records) != 1:
            return False
        manifest = Path(records[0].library) / "steamapps" / ("appmanifest_" + game.app_id + ".acf")
        state = read_vdf(manifest).get("appstate", {})
        folder = str(state.get("installdir", ""))
        return (str(state.get("appid", "")) == game.app_id and int(state.get("stateflags", 0)) & 4 != 0
                and folder == path.name and not _has_reparse_component(manifest))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def chosen_executable(game, source):
    root = install_directory(game).resolve(strict=True)
    path = Path(source)
    if (not path.is_absolute() or path.suffix.casefold() != ".exe" or not path.is_file()
            or _has_reparse_component(path)):
        raise ValueError("Choose an ordinary game EXE inside this installation folder.")
    try:
        path.resolve(strict=True).relative_to(root)
    except ValueError as exc:
        raise ValueError("The chosen EXE must be inside this game's installation folder.") from exc
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("The selected file is not a Windows executable.")
    return str(path)
