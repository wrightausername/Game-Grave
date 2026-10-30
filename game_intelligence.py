"""Evidence-first Game Grave intelligence. Analysis only, never deletion authority.

The scanner owns local metadata. No uploads, telemetry, file modifications, or claims
that missing manifests, folder names, or old timestamps prove orphaned content.
"""
from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from core import config_dir

SCHEMA = 1
MAX_ROOTS = 40
MAX_ENTRIES = 4000
MAX_DEPTH = 3
PATCH_SUFFIXES = frozenset({
    ".dll", ".asi", ".esp", ".esm", ".esl", ".pak", ".archive", ".pex",
    ".ini", ".toml", ".json", ".yaml", ".yml", ".xml",
})


def _path(p) -> Path:
    return Path(str(p)).expanduser().resolve(strict=False)


def _within(child, parent) -> bool:
    """Containment uses paths, not misleading textual prefixes."""
    try:
        _path(child).relative_to(_path(parent))
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _linked_ancestor(path: str | Path) -> bool:
    """Treat symlink/junction ancestors as untrusted ownership evidence."""
    try:
        current = Path(os.path.abspath(os.fspath(path)))
        while True:
            try:
                info = current.lstat()
            except FileNotFoundError:
                info = None  # A missing child does not hide an existing linked parent.
            if info is not None and (stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                return True
            parent = current.parent
            if current == parent:
                return False
            current = parent
    except (OSError, ValueError, TypeError, RuntimeError):
        return True


def _workshop_id(p) -> str | None:
    parts = [x.casefold() for x in Path(p).parts]
    for i in range(len(parts) - 2):
        if parts[i:i + 2] == ["workshop", "content"] and parts[i + 2].isdecimal():
            return parts[i + 2]
    return None


def build_game_dna(games=(), other_games=(), mods=(), saves=(), manager_profiles=()) -> dict:
    """Build defensible per-game relationships. No name-based assignment.

    Save-location titles and manager folder names are *suggestions*, never
    strong enough to identify an owner. Unresolved content remains protected.
    """
    result = []
    for g in list(games) + list(other_games):
        install = str(getattr(g, "install_path", "") or "")
        if not install:
            continue
        launcher = str(getattr(g, "launcher", "Steam") or "Steam")
        if hasattr(g, "source") and not hasattr(g, "launcher"):
            launcher = "Steam"
        app_id = str(getattr(g, "app_id", "") or "")
        result.append({
            "id": f"{launcher}:{app_id or install}",
            "game": str(getattr(g, "name", "Unknown game")),
            "launcher": launcher,
            "app_id": app_id,
            "install_path": install,
            "install_evidence": "Manifest or inventory record; individual files may still be needed.",
            "assets": [], "manager_profiles": [],
        })
    unresolved = []
    for m in mods:
        path = str(getattr(m, "path", "") or "")
        if not path:
            continue
        owners = []
        workshop = _workshop_id(path)
        linked_path = _linked_ancestor(path)
        for game in result:
            if linked_path or _linked_ancestor(game["install_path"]):
                continue
            if _within(path, game["install_path"]):
                owners.append((game, "Within recorded game installation"))
            elif workshop and workshop == game["app_id"] and game["launcher"] == "Steam":
                owners.append((game, "Steam Workshop folder uses this game's app ID"))
        row = {
            "path": path, "kind": "Mod or addon storage",
            "source": str(getattr(m, "source", "Unknown manager")),
            "status": str(getattr(m, "status", "Unknown")),
            "apparent_bytes": max(0, int(getattr(m, "apparent_bytes", 0) or 0)),
            "protected": True,
        }
        if linked_path:
            unresolved.append({**row, "reason": "A linked or redirected ancestor prevents trusted ownership association."})
        elif len(owners) > 1:
            unresolved.append({**row, "reason": "Multiple launcher/game records claim this location; owner is ambiguous.",
                               "candidate_games": [g["game"] for g, _ in owners][:10],
                               "ambiguous": True})
        elif not owners:
            unresolved.append({**row, "reason": "Ownership unverified; retain files and profiles."})
        elif owners[0][0]["launcher"] == "Custom library":
            unresolved.append({**row, "reason": "User-added library folder is not a verified game installation.",
                               "candidate_games": [owners[0][0]["game"]],
                               "ambiguous": True})
        else:
            game, evidence = owners[0]
            game["assets"].append({**row, "evidence": evidence,
                                   "confidence": "Location / ID association only",
                                   "can_recycle": False})
    for s in saves:
        path = str(getattr(s, "path", "") or "")
        if path:
            unresolved.append({
                "path": path, "kind": "Possible save/profile",
                "source": str(getattr(s, "kind", "Save discovery")),
                "game_hint": str(getattr(s, "game", "")),
                "protected": True,
                "reason": "Save location was detected; ownership and contents are not verified.",
            })
    for profile in manager_profiles:
        if not isinstance(profile, dict):
            continue
        matched_root = str(profile.get("verified_install_path", "") or "")
        record = {
            "manager": str(profile.get("manager", "Unknown")),
            "profile": str(profile.get("profile", "Unnamed")),
            "mod_count": len(profile.get("mods", [])),
            "source": str(profile.get("source", "")),
            "protected": True,
            "stale": bool(profile.get("stale")),
            "incomplete": bool(profile.get("incomplete")),
        }
        matches = [g for g in result if matched_root
                   and g["launcher"] != "Custom library"
                   and not _linked_ancestor(g["install_path"])
                   and not _linked_ancestor(matched_root)
                   and _path(g["install_path"]) == _path(matched_root)]
        if len(matches) == 1:
            matches[0]["manager_profiles"].append({
                **record, "evidence": "Manager game path exactly matches a recorded game installation"})
        else:
            unresolved.append({
                "kind": "Unverified manager profile", "path": record["source"],
                "source": record["manager"], "profile": record["profile"],
                "protected": True,
                "reason": "Profile ownership could not be tied to a recorded game installation.",
            })
    return {
        "schema": SCHEMA, "games": result, "unresolved": unresolved,
        "note": "Relationships explain likely ownership only. Nothing here authorizes removal.",
    }


def _special(path: Path) -> bool:
    """Reject symlinks, Windows reparse points, sockets and non-regular files."""
    try:
        st = path.lstat()
        return bool(stat.S_ISLNK(st.st_mode) or
                    getattr(st, "st_file_attributes", 0) & 0x400 or
                    not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)))
    except OSError:
        return True


def capture_mod_observation(mods, max_entries: int = MAX_ENTRIES) -> dict:
    """Bounded, on-demand metadata snapshot of recognized mod folders only.

    Not a snapshot of full game installations; hashes/content are deliberately
    excluded. A comparison is not proof that a game was ever known-good.
    """
    if not 1 <= int(max_entries) <= MAX_ENTRIES:
        raise ValueError("Choose a valid observation limit.")
    sources = list(mods)
    roots = []
    entries = {}
    truncated = False
    skipped_roots = 0
    for m in sources[:MAX_ROOTS]:
        root = Path(str(getattr(m, "path", "")))
        if (not root.is_dir() or _special(root) or
                _path(root) in (Path.home().resolve(), Path(_path(root).anchor))):
            skipped_roots += 1
            continue
        if _linked_ancestor(root):
            skipped_roots += 1
            continue
        roots.append(str(_path(root)))
        for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False):
            directory = Path(current)
            depth = len(directory.relative_to(root).parts)
            dirs[:] = [] if depth >= MAX_DEPTH else [
                name for name in dirs if not _special(directory / name)
            ]
            for name in filenames:
                item = directory / name
                if len(entries) >= max_entries:
                    truncated = True
                    break
                if _special(item):
                    continue
                try:
                    info = item.stat()
                    if not stat.S_ISREG(info.st_mode):
                        continue
                    entries[str(_path(item))] = [info.st_size, info.st_mtime_ns]
                except OSError:
                    continue
            if truncated:
                break
        if truncated:
            break
    return {
        "schema": SCHEMA,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "roots": sorted(set(roots)),
        "entries": entries,
        "truncated": truncated or len(sources) > MAX_ROOTS or skipped_roots > 0,
        "skipped_roots": skipped_roots,
        "limitations": "Metadata-only, bounded to recognized mod roots, max 3 levels; skipped/linked roots make coverage incomplete; no game launch verification.",
    }


def compare_observations(before: dict, after: dict) -> dict:
    """Review observed changes without predicting crashes or assigning blame."""
    if before.get("schema") != SCHEMA or after.get("schema") != SCHEMA:
        raise ValueError("Unsupported observation schema.")
    old = before.get("entries", {})
    new = after.get("entries", {})
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError("Invalid observation entries.")
    # Never call an item gone when scans used different roots or hit entry
    # caps: "missing" can simply mean it was outside the observed subset.
    partial = (bool(before.get("truncated") or after.get("truncated"))
               or set(before.get("roots", [])) != set(after.get("roots", [])))
    names = sorted(set(old) | set(new))
    changes = []
    for name in names:
        if name not in old:
            kind = "possibly added (incomplete comparison)" if partial else "added"
        elif name not in new:
            kind = "not observed (incomplete comparison)" if partial else "missing from observation"
        elif old[name] != new[name]:
            kind = "metadata changed"
        else:
            continue
        changes.append({"path": name, "change": kind,
                        "patch_sensitive": Path(name).suffix.casefold() in PATCH_SUFFIXES})
    return {
        "changes": changes, "count": len(changes),
        "patch_review": sum(x["patch_sensitive"] for x in changes),
        "scope_changed": set(before.get("roots", [])) != set(after.get("roots", [])),
        "incomplete": partial,
        "unreliable_missing_inference": partial,
        "note": "Coverage gaps or changed roots make missing/added labels uncertain. File differences do not prove crashes or abandoned mods.",
    }


def ghost_watch(previous: dict | None, current: dict) -> dict:
    """A user-triggered Ghost Watch report, not a background filesystem monitor."""
    if previous is None:
        return {"first_observation": True, "count": 0,
                "message": "First baseline recorded. Compare after a later manual scan."}
    report = compare_observations(previous, current)
    report["first_observation"] = False
    report["message"] = "Review changes. Storage growth and causality are not independently verified."
    return report


def what_broke_my_game(report: dict) -> list[str]:
    """Plain-language investigation prompts, NEVER an automatic repair."""
    lines = []
    if report.get("scope_changed") or report.get("incomplete"):
        lines.append("Comparison is incomplete: scan coverage differed or was capped.")
    if report.get("patch_review"):
        lines.append(f"{report['patch_review']} changed mod/configuration files merit review after a game update.")
    if report.get("count"):
        lines.append(f"{report['count']} file observations changed; this does not establish why a game failed.")
    else:
        lines.append("No changes were observed in the tracked mod folders; other causes remain possible.")
    lines.append("Confirm game version and mod-manager state before restoring any files.")
    return lines


def patch_fallout(report: dict) -> dict:
    """Candidate patch impact, no unsupported compatibility prediction."""
    candidates = [row for row in report.get("changes", []) if row.get("patch_sensitive")]
    return {
        "review_files": candidates[:100],
        "total_review": len(candidates),
        "compatibility_verified": False,
        "note": "Possible mod/config changes only; version-specific incompatibility is not established.",
    }


def regret_calculator(suggestions, dna: dict | None = None) -> list[dict]:
    """Explain recovery effort for existing Make Room candidates.

    Archive names alone never prove association, and all suggestions still require
    independent Graveyard checks and explicit user approval.
    """
    active_roots = [
        asset["path"]
        for game in (dna or {}).get("games", [])
        for asset in game.get("assets", [])
    ]
    rows = []
    for candidate in suggestions:
        path = str(getattr(candidate, "path", "") or "")
        if not path:
            continue
        attached = any(_within(path, root) or _within(root, path) for root in active_roots)
        reason = ("Overlaps identified mod storage; do not remove manually." if attached else
                  "Recovery availability and repurchase/download effort are unknown.")
        rows.append({
            "path": path, "apparent_bytes": max(0, int(getattr(candidate, "apparent_bytes", 0))),
            "recovery_cost": "Potentially high" if attached else "Unknown",
            "reason": reason, "approved": False,
            "verified_reclaimable_bytes": 0,
        })
    return rows


def exodus_plan(dna: dict) -> dict:
    """Read-only transfer checklist; excludes claims of launcher-portable installs."""
    games = []
    for game in dna.get("games", []):
        games.append({
            "name": game["game"], "launcher": game["launcher"],
            "install_path": game["install_path"],
            "related_storage": [asset["path"] for asset in game.get("assets", [])],
            "action": "Reinstall/verify through the official launcher; preserve saves and mod profiles separately.",
        })
    return {
        "schema": SCHEMA, "games": games,
        "unresolved_count": len(dna.get("unresolved", [])),
        "copy_executed": False,
        "note": "Checklist only. No game, mod, license, save, or file was moved.",
    }


def community_rule_draft(ecosystem: str, category: str, extension: str) -> dict:
    """Anonymous-category local draft, never auto-uploaded or trusted as a rule."""
    allowed_categories = {"mod_archive", "manager_staging", "save_profile", "addon_descriptor"}
    if category not in allowed_categories:
        raise ValueError("Unrecognized rule category.")
    if not ecosystem or len(ecosystem) > 70 or any(x in ecosystem for x in "/\\:"):
        raise ValueError("Use a short ecosystem name, not a filesystem path.")
    extension = extension.casefold().strip()
    if extension and (len(extension) > 12 or not extension.startswith(".") or
                      not extension[1:].isalnum()):
        raise ValueError("Use a simple file extension.")
    return {
        "schema": SCHEMA, "ecosystem": ecosystem, "category": category,
        "extension": extension, "raw_paths": False,
        "approved": False, "uploaded": False,
        "notice": "Review before any future opt-in contribution; this draft is not a cleanup rule.",
    }


def _state_file() -> Path:
    return config_dir() / "game_intelligence_snapshot.json"


def load_observation() -> dict | None:
    try:
        path = _state_file()
        if path.stat().st_size > 2_000_000:
            return None
        state = json.loads(path.read_text(encoding="utf-8"))
        if (isinstance(state, dict) and state.get("schema") == SCHEMA
                and isinstance(state.get("entries"), dict)):
            return state
    except (OSError, ValueError, TypeError):
        pass
    return None


def save_observation(snapshot: dict) -> None:
    """Only a user-directed capture writes locally. Never writes into game roots."""
    if snapshot.get("schema") != SCHEMA or len(snapshot.get("entries", {})) > MAX_ENTRIES:
        raise ValueError("Invalid observation.")
    file = _state_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix(".tmp")
    temp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    temp.replace(file)
