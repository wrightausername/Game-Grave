"""Game Grave's local-only, read-only file relationship and safety explanations.

A known location/manifest can establish *association*, not whether an item is
needed, unused, or safe to delete. Never converts evidence into delete authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core import is_protected_path
from addon_metadata import inspect_addon_metadata
from game_intelligence import _linked_ancestor


@dataclass(frozen=True)
class FileVerdict:
    headline: str
    game: str
    confidence: str
    explanation: str
    evidence: tuple[str, ...]
    next_step: str
    protected: bool = True


def _relative(path: Path, parent: Path) -> bool:
    """Only associate ordinary ancestry; a junction is not trusted game evidence."""
    if _linked_ancestor(path) or _linked_ancestor(parent):
        return False
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _parts(path: Path) -> list[str]:
    return [p.casefold() for p in path.parts]


def investigate(path: str | Path, games: Iterable = (), other_games: Iterable = (),
                mods: Iterable = (), never_touch: list[str] | None = None) -> FileVerdict:
    """Explain a path using available inventory records, without any mutation.

    Does not make network requests, run file content, or inspect active processes.
    """
    target = Path(path)
    name = target.name or str(target)
    known_games = list(games) + list(other_games)
    for game in known_games:
        root = str(getattr(game, 'install_path', '')).strip()
        if root and _relative(target, Path(root)):
            if getattr(game, 'launcher', '') == 'Custom library':
                return FileVerdict(
                    "Possible game folder", str(game.name), "User-added folder only",
                    "This is inside a folder you added as a game library. Game Grave "
                    "has not confirmed a launcher installation or whether its files are active.",
                    (f"User-added library: {root}", "No verified launcher record"),
                    "Review this location manually. Keep mods, saves, and settings until you are sure.")
            return FileVerdict(
                "Part of an installed game", str(game.name), "Known game location",
                f"This location sits inside the installation of {game.name}. "
                "Files here may be needed by the game or its mods.",
                (f"{getattr(game, 'launcher', 'Steam')} installation: {root}",
                 "Folder relationship confirmed; individual file usage unknown."),
                "Keep it. To remove the game, use its launcher. Never manually clean its mod folders.")

    for mod in mods:
        root = str(getattr(mod, 'path', '')).strip()
        if not root or not _relative(target, Path(root)):
            continue
        status = str(getattr(mod, 'status', 'Unknown status'))
        source = str(getattr(mod, 'source', 'Mod storage'))
        evidence = [f"Found in {source} storage: {root}", f"Scanner note: {status}"]
        evidence.extend(str(s) for s in (getattr(mod, 'indicators', ()) or ())[:4])
        addon = inspect_addon_metadata(target)
        if addon:
            evidence.extend(addon.evidence)
        return FileVerdict(
            "Mod or addon storage found", str(getattr(mod, 'name', 'Unknown game')),
            "Known storage location", "This belongs to a location identified by Game Grave's "
            "mod scanner. A folder can still be in use even if its game is not shown as installed.",
            tuple(evidence), "Check the mod manager or game before changing anything. Keep profiles, "
            "saves, and settings. Age alone does not mean abandoned.")

    for game in games:
        app_id = str(getattr(game, 'app_id', ''))
        parts = _parts(target)
        if app_id.isdecimal() and app_id in parts:
            try:
                ix = parts.index('workshop')
                if ix + 2 < len(parts) and parts[ix+1] == 'content' and parts[ix+2] == app_id:
                    return FileVerdict(
                        "Steam Workshop content", str(game.name), "Likely game match",
                        f"The Workshop folder uses {game.name}'s Steam app ID. "
                        "Subscriptions and cached downloads may still be active.",
                        (f"Steam Workshop app ID {app_id}", f"Installed Steam game: {game.name}"),
                        "Manage subscriptions in Steam. Do not delete Workshop folders by hand.")
            except ValueError:
                pass

    addon = inspect_addon_metadata(target)
    if addon:
        return FileVerdict(
            "Recognized addon descriptor", addon.ecosystem, "Local descriptor evidence",
            f"The {addon.ecosystem} addon folder contains a recognizable descriptor "
            f"for {addon.title}. This does not establish whether the addon is enabled, "
            "used recently, or safe to remove.",
            addon.evidence, "Check the game or addon manager. Preserve saved settings and dependencies.")

    if is_protected_path(target, never_touch):
        return FileVerdict(
            "Protected file or folder", "Not confirmed", "Protected location",
            "This location matches a built-in safety rule or your Never Touch list.",
            ("Protected path check matched",), "Keep it. Check your protection settings if needed.")

    # Relationship by name is a clue only, even if names happen to match exactly.
    needle = name.casefold()
    for game in known_games:
        game_name = str(getattr(game, 'name', '')).casefold().strip()
        if len(game_name) >= 5 and game_name in needle:
            return FileVerdict(
                "Possible game-related file", str(game.name), "Name match only",
                f"The name resembles {game.name}, but Game Grave cannot verify that it "
                "belongs to this game or that it is safe to delete.",
                ("Name resembles a game in the current scan", "No folder or manager link confirmed"),
                "Open the file's folder and check it yourself. No deletion is recommended.")

    return FileVerdict(
        "Origin not confirmed", "Unknown", "Not enough evidence",
        "Game Grave cannot prove which game or mod manager created this. "
        "An old date or unfamiliar filename does not mean it is unnecessary.",
        ("No verified matching game or mod-manager location",),
        "Inspect the folder manually. Keep anything related to saves, profiles, or active mods.")


def friendly_report(verdict: FileVerdict, path: str | Path) -> str:
    proof = "\n".join("• " + line for line in verdict.evidence)
    return (f"{verdict.headline}\n\nFile or folder: {Path(path).name}\n"
            f"Related game: {verdict.game}\nEvidence strength: {verdict.confidence}\n\n"
            f"What we know:\n{verdict.explanation}\n\nEvidence:\n{proof}\n\n"
            f"What to do:\n{verdict.next_step}\n\n"
            "No files were changed. Game Grave cannot certify that a file is safe to delete.")
