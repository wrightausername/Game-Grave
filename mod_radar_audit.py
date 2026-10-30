"""M2 Mod Radar evidence audit. Read-only and no deletion authorizations.

A detected addon, an old folder or even a manager's disabled marker does NOT
establish that content is safe to discard. This audit highlights ambiguity
and bounded coverage instead of inventing a numeric safety score.
"""
from __future__ import annotations

from pathlib import Path

from game_intelligence import build_game_dna

MAX_PREVIEW = 25
MAX_PROFILES = 500


def audit_mod_radar(games=(), other_games=(), mods=(), saves=(),
                    manager_profiles=()) -> dict:
    """Review already scanned records; never scan files again or change settings."""
    games = list(games)
    other_games = list(other_games)
    mods = list(mods)
    saves = list(saves)
    manager_profiles = list(manager_profiles)[:MAX_PROFILES]
    dna = build_game_dna(games, other_games, mods, saves, manager_profiles)

    associations = sum(len(game["assets"]) for game in dna["games"])
    unknowns = [item for item in dna["unresolved"]
                if item.get("kind") == "Mod or addon storage"]
    conflicts = [item for item in dna["unresolved"] if item.get("ambiguous")]
    redirected = [item for item in dna["unresolved"]
                  if "linked or redirected" in str(item.get("reason", ""))]
    stale = [p for p in manager_profiles if isinstance(p, dict) and p.get("stale")]
    partial = [p for p in manager_profiles if isinstance(p, dict) and p.get("incomplete")]
    enabled, disabled = 0, 0
    for profile in manager_profiles:
        if not isinstance(profile, dict):
            continue
        for entry in (profile.get("mods") or [])[:4000]:
            if not isinstance(entry, dict):
                continue
            if entry.get("marker") == "+":
                enabled += 1
            elif entry.get("marker") == "-":
                disabled += 1

    noteworthy = []
    for entry in dna["unresolved"]:
        noteworthy.append({
            "item": Path(str(entry.get("path", ""))).name or
                    str(entry.get("kind", "Unverified entry")),
            "reason": str(entry.get("reason", "Unverified"))[:240],
            "source": str(entry.get("source", "Unknown"))[:70],
            "requires_review": True,
        })
        if len(noteworthy) >= MAX_PREVIEW:
            break

    return {
        "schema": 1,
        "recorded_games": len(dna["games"]),
        "manager_profiles": len(manager_profiles),
        "scanned_mod_locations": len(mods),
        "scanned_save_locations": len(saves),
        "associated_mod_locations": associations,
        "unassigned_mod_locations": len(unknowns),
        "ambiguous_claims": len(conflicts),
        "redirected_locations": len(redirected),
        "stale_manager_snapshots": len(stale),
        "incomplete_manager_snapshots": len(partial),
        "enabled_profile_references": enabled,
        "disabled_profile_references": disabled,
        "unresolved_records": len(dna["unresolved"]),
        "examples": noteworthy,
        "example_count_limited": len(dna["unresolved"]) > MAX_PREVIEW,
        "removal_authorizations": 0,
        "confirmed_orphans": 0,
        "safe_to_recycle": False,
        "note": "Association means recorded path or Workshop app ID, never proof of usage. "
                "Missing installation manifests, disabled mods, or old files do NOT prove "
                "abandonment; every unresolved or ambiguous item remains protected.",
    }
