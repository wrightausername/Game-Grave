"""On-demand, evidence-led Resurrection Kit source suggestions.

Recommendations are never automatic backup permissions. Association is limited to
a verified manager install path or a save scanner's exact game label; uncertain
content is not silently included. No network access or source modifications.
"""
from __future__ import annotations

from pathlib import Path
import os
import stat

from manager_profiles import _identity
from resurrection_v2 import _regular

MAX_CANDIDATES = 32
MAX_PROFILES = 24


def _root_safe(path) -> bool:
    try:
        p = Path(path)
        return (bool(str(p)) and _regular(p, directory=True)
                and p.resolve() not in (Path.home().resolve(), Path(p.anchor))
                and len(p.parts) >= 2)
    except (OSError, ValueError, RuntimeError):
        return False


def _same_recorded_game(game, profile) -> bool:
    expected = _identity(str(getattr(game, "install_path", "") or ""))
    found = _identity(str(profile.get("verified_install_path", "") or ""))
    return bool(expected and found and expected == found and profile.get("verified_game"))


def _mo2_ini(mod):
    for value in (getattr(mod, "indicators", ()) or ()):
        if isinstance(value, str) and value.startswith("MO2 INI: "):
            return value[9:]
    return ""


def discover_setup(game, *, mods=(), saves=(), manager_report=None) -> dict:
    """Find independently explainable sources for ONE recorded installation.

    Suggested roles are one folder each. MO2 profile/mod suggestions share a
    manager instance identity so the UI can reject accidental cross-instance kits.
    """
    installed = str(getattr(game, "install_path", "") or "")
    if not installed:
        raise ValueError("Choose a game with a recorded installation.")
    title = str(getattr(game, "name", "") or "").strip()
    if not title:
        raise ValueError("Game name missing from install inventory.")
    profiles = list((manager_report or {}).get("profiles", ()))[:MAX_PROFILES]
    candidates = []
    seen = set()

    def add(role, path, evidence, confidence, *, manager="", instance="", profile="", default=False):
        if role not in ("Saves", "Mods", "Profiles", "Configs") or not _root_safe(path):
            return
        canonical = (role, _identity(str(path)))
        if canonical in seen or len(candidates) >= MAX_CANDIDATES:
            return
        seen.add(canonical)
        candidates.append({
            "role": role, "path": str(Path(path)), "evidence": evidence,
            "confidence": confidence, "manager": manager,
            "instance": instance, "profile": profile,
            "default": bool(default), "requires_review": True,
        })

    # Save discovery knows paths but cannot certify that every item is a save.
    # Exact game-label evidence is reasonable for review, not for blind inclusion.
    for save in saves:
        if str(getattr(save, "game", "") or "").strip().casefold() == title.casefold():
            add("Saves", str(getattr(save, "path", "")),
                f"Save scanner labeled this folder {title}; individual files not verified",
                "Possible save match", default=True)

    for profile in profiles:
        if not isinstance(profile, dict) or not _same_recorded_game(game, profile):
            continue
        manager = profile.get("manager")
        source = Path(str(profile.get("source", "")))
        if manager == "Mod Organizer 2":
            folder = source.parent
            # The report's modlist is inside a single profile directory.
            if source.name.casefold() != "modlist.txt" or folder.name != profile.get("profile"):
                continue
            # Instance is correlated by its configured profiles folder.
            instance_ini = ""
            for m in mods:
                if str(getattr(m, "source", "")) != "Mod Organizer 2":
                    continue
                ini = _mo2_ini(m)
                if not ini:
                    continue
                indicators = (getattr(m, "indicators", ()) or ())
                for marker in indicators:
                    if isinstance(marker, str) and marker == "profiles_directory":
                        known_root = Path(str(getattr(m, "path", "")))
                        if _identity(str(known_root)) == _identity(str(folder.parent)):
                            instance_ini = ini
                            break
                if instance_ini:
                    break
            if not instance_ini:
                # Cannot link instance with an exact known INI and configured
                # profile location; no name-based guessing.
                continue
            if profile.get("incomplete"):
                continue
            add("Profiles", folder,
                f"Exact MO2 gamePath match; profile {folder.name} has a saved modlist",
                "Verified MO2 profile location", manager="MO2",
                instance=instance_ini, profile=folder.name, default=True)
            for m in mods:
                if (str(getattr(m, "source", "")) == "Mod Organizer 2"
                        and str(getattr(m, "status", "")) == "MO2: installed mods"
                        and _identity(_mo2_ini(m)) == _identity(instance_ini)):
                    add("Mods", getattr(m, "path"),
                        "MO2 configured installed-mod storage from the SAME instance",
                        "Verified MO2 instance path", manager="MO2",
                        instance=instance_ini, profile=folder.name, default=True)
                    break

        elif manager == "Vortex":
            if profile.get("stale") or profile.get("incomplete"):
                continue
            game_id = str(profile.get("game_hint", ""))
            if not game_id or "/" in game_id or "\\" in game_id:
                continue
            for m in mods:
                root = Path(str(getattr(m, "path", "")))
                if (str(getattr(m, "source", "")) == "Vortex"
                        and str(getattr(m, "status", "")) == "Vortex: mod staging"
                        and root.name.casefold() == "mods"
                        and root.parent.name.casefold() == game_id.casefold()):
                    add("Mods", root,
                        "Vortex saved profile has an exact installed-game path and matching staging game ID; backup state can be stale",
                        "Vortex snapshot match", manager="Vortex", default=False)
                    break
            # A Vortex snapshot is NOT live state and must not be injected into
            # LevelDB on restore. The user's archived mod folders remain portable.

    groups = {role: [c for c in candidates if c["role"] == role]
              for role in ("Saves", "Profiles", "Mods", "Configs")}
    return {
        "game": title,
        "game_path": installed,
        "groups": groups,
        "candidates": candidates,
        "count": len(candidates),
        "safe_to_delete": False,
        "note": "All choices require review. Missing sources are UNKNOWN, not safe to remove. "
                "MO2 profile and Mods roots must originate in the same manager instance.",
    }


def select_sources(discovery: dict, selected: list[dict]) -> tuple[dict, dict]:
    """Validate UI choices and produce portable (path-free) restore hints."""
    allowed = { (row["role"], _identity(row["path"])): row
                for row in discovery["candidates"] }
    sources, chosen = {}, []
    for row in selected:
        key = (str(row.get("role")), _identity(str(row.get("path", ""))))
        original = allowed.get(key)
        if original is None:
            raise ValueError("Source selection no longer matches scan evidence.")
        role = original["role"]
        if role in sources:
            raise ValueError(f"Only one {role} folder can be selected per kit.")
        if not _root_safe(original["path"]):
            raise ValueError("A selected folder is no longer available or safe to inspect.")
        sources[role] = Path(original["path"])
        chosen.append(original)
    if not sources:
        raise ValueError("Choose at least one folder to preserve.")
    manager_rows = [x for x in chosen if x["manager"]]
    mo2 = [x for x in manager_rows if x["manager"] == "MO2"]
    if mo2 and len({_identity(x["instance"]) for x in mo2}) != 1:
        raise ValueError("MO2 sources belong to different manager instances.")
    if {x["manager"] for x in manager_rows} == {"Vortex", "MO2"}:
        raise ValueError("Do not mix MO2 and Vortex sources in one game kit.")
    metadata = {"kind": "unknown", "auto_discovered": True,
                "source_count": len(chosen)}
    if mo2:
        profile = next((x["profile"] for x in mo2 if x["role"] == "Profiles"), "")
        metadata = {"kind": "MO2", "profile": profile,
                    "auto_discovered": True, "source_count": len(chosen)}
    elif any(x["manager"] == "Vortex" for x in chosen):
        metadata = {"kind": "Vortex", "auto_discovered": True,
                    "source_count": len(chosen)}
    return sources, metadata
