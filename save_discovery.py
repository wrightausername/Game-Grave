"""Read-only, bounded discovery of common PC game save and profile locations.

These locations are evidence-led suggestions, not proof that every file is a save.
Never removes, opens or edits discovered files. Scans only known locations and
immediate game subfolders, not entire user profiles.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SaveLocation:
    game: str
    path: str
    kind: str
    reason: str


def discover_saves(home: Path | None = None, *, local: Path | None = None,
                   roaming: Path | None = None, documents: Path | None = None,
                   steam_roots: list[Path] | None = None) -> list[SaveLocation]:
    home = Path(home or os.environ.get('USERPROFILE') or Path.home())
    local = Path(local or os.environ.get('LOCALAPPDATA') or home / 'AppData' / 'Local')
    roaming = Path(roaming or os.environ.get('APPDATA') or home / 'AppData' / 'Roaming')
    documents = Path(documents or home / 'Documents')
    found: list[SaveLocation] = []
    seen: set[str] = set()

    def add(path: Path, game: str, kind: str, reason: str):
        try:
            if not path.is_dir() or path.is_symlink():
                return
            path = path.resolve(strict=True)
            if path == home.resolve() or path == Path(path.anchor):
                return
            key = os.path.normcase(str(path)).casefold()
            if key in seen:
                return
            seen.add(key)
            found.append(SaveLocation(game[:90], str(path), kind, reason))
        except (OSError, ValueError):
            return

    def add_children(parent: Path, kind: str, reason: str, max_children=160):
        if not parent.is_dir() or parent.is_symlink():
            return
        try:
            for child in sorted(parent.iterdir(), key=lambda p: p.name.casefold())[:max_children]:
                if child.is_dir() and not child.is_symlink():
                    add(child, child.name, kind, reason)
        except OSError:
            pass

    # Windows known save folders, including common OneDrive Documents redirection.
    add_children(home / 'Saved Games', 'Game saves', 'Found in your Windows Saved Games folder.')
    for docs in dict.fromkeys([documents, home / 'OneDrive' / 'Documents']):
        add_children(docs / 'My Games', 'Possible saves and settings',
                     'Found in Documents/My Games; may also contain game settings.')
        add_children(docs / 'My Saved Games', 'Possible game saves', 'Found in Documents/My Saved Games.')
        for game in ('Elder Scrolls Online', 'War Thunder'):
            parent = docs / game
            if game == 'Elder Scrolls Online':
                for env in ('live', 'liveeu', 'pts'):
                    add(parent / env / 'SavedVariables', 'Elder Scrolls Online', 'Addon settings',
                        'ESO addon saved variables. Preserve before removing addons.')
            else:
                add(parent / 'Saves', 'War Thunder', 'Possible saves and settings',
                    'Game data folder identified, but individual file usage is unverified.')

    for game, folder, kind, reason in (
        ('Stardew Valley', roaming / 'StardewValley' / 'Saves', 'Game saves', 'Known Stardew Valley saves folder.'),
        ('Elden Ring', roaming / 'EldenRing', 'Game saves', 'Known Elden Ring local save-data folder.'),
        ('Minecraft', roaming / '.minecraft' / 'saves', 'Game worlds', 'Known Minecraft world saves folder.'),
        ('Cyberpunk 2077', local / 'CD Projekt Red' / 'Cyberpunk 2077', 'Possible game saves', 'Known game-specific local data location.'),
        ('Baldur\'s Gate 3', local / 'Larian Studios' / 'Baldur\'s Gate 3' / 'PlayerProfiles',
         'Profiles and saves', 'Game profiles, settings and saves may be here.'),
        ('The Sims 4', documents / 'Electronic Arts' / 'The Sims 4' / 'saves', 'Game saves', 'Known Sims 4 saves folder.'),
        ('The Sims 4', documents / 'Electronic Arts' / 'The Sims 4' / 'Tray', 'Game library', 'Custom library content, not necessarily saves.'),
    ):
        add(folder, game, kind, reason)

    for steam in (steam_roots or []):
        # Steam userdata has mixed configuration and sometimes cloud save data.
        # We only inventory immediate per-account folders, never treat all as disposable.
        add_children(Path(steam) / 'userdata', 'Steam user data',
                     'Steam account data may contain saves, cloud copies and settings.', max_children=25)
    return sorted(found, key=lambda s: (s.game.casefold(), s.path.casefold()))
