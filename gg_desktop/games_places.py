"""Where a game's files are, for the Games tab's Open buttons and right-click menu (owner, 2026-11-14: "in the games tab there
needs to be an option to go straight to where the games / files are stored"). Pure: no Qt, no file access.

Only proven places are offered: the install folder the launcher reported (when the record allows opening it), the library
folder that holds it, and save folders the save scanner labeled with this exact game. A save folder is never matched by a
similar name.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath


@dataclass(frozen=True)
class Place:
    label: str
    path: str
    why: str


def _norm(text):
    return " ".join(str(text or "").casefold().split())


def install_place(game):
    if "open_folder" not in getattr(game, "capabilities", ()) or not getattr(game, "install_path", ""):
        return None
    return Place("Install folder", game.install_path, f"Where {game.launcher} installed {game.name}.")


def library_place(game):
    install = install_place(game)
    if install is None:
        return None
    parent = PureWindowsPath(install.path).parent
    if str(parent) in ("", ".", parent.anchor):
        return None
    return Place("Library folder", str(parent), f"The {game.launcher} folder that holds {game.name} and your other games there.")


def save_places(game, saves):
    """Save folders the save scanner labeled with exactly this game's name."""
    name = _norm(getattr(game, "name", ""))
    out, seen = [], set()
    for loc in saves or ():
        if name and _norm(getattr(loc, "game", "")) == name and loc.path not in seen:
            seen.add(loc.path)
            out.append(Place("Save folder", loc.path, getattr(loc, "reason", "") or "Found by the save scanner."))
    return out


def places(game, saves=()):
    """Every place to open for this game, in the order a person looks for them."""
    found = [p for p in (install_place(game),) if p] + save_places(game, saves)
    library = library_place(game)
    if library:
        found.append(library)
    return found


def short(path, limit=46):
    """A long path shortened in the middle so the start (drive) and the end (folder name) both show."""
    text = str(path)
    if len(text) <= limit:
        return text
    keep = (limit - 1) // 2
    return text[:keep] + "…" + text[-(limit - keep - 1):]
