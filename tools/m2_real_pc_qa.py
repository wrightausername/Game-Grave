"""Read-only, privacy-limited M2 evidence report for real gaming PCs.

Run manually on your own Windows system, never in the background. The output
contains aggregates only, not game titles, usernames, profile identifiers,
installation paths or content. A complete report is NOT M2 release sign-off:
human verification against actual launcher and manager UIs is required.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


LAUNCHER_CATEGORIES = (
    "Steam", "Epic Games", "GOG", "Riot Games",
    "EA", "Ubisoft Connect", "Custom library",
)
MOD_CATEGORIES = (
    "Steam Workshop", "Steam game folder", "Mod Organizer 2", "Vortex",
    "World of Warcraft", "Elder Scrolls Online", "FiveM", "RedM",
    "Thunderstore", "r2modman", "Prism Launcher", "Modrinth",
)


def aggregate_results(games, other_games, mods, manager_report) -> dict:
    """Whitelist category totals; no raw paths or game/profile names can escape."""
    from mod_radar_audit import audit_mod_radar
    games = list(games)
    other_games = list(other_games)
    mods = list(mods)
    profiles = list((manager_report or {}).get("profiles", []))
    audit = audit_mod_radar(games, other_games, mods, (), profiles)
    launcher_count = Counter({"Steam": len(games)})
    for item in other_games:
        launcher = str(getattr(item, "launcher", ""))
        launcher_count[launcher if launcher in LAUNCHER_CATEGORIES else "Other"] += 1
    mod_count = Counter()
    for item in mods:
        source = str(getattr(item, "source", ""))
        mod_count[source if source in MOD_CATEGORIES else "Other"] += 1
    return {
        "schema": 1,
        "purpose": "Game Grave M2 local evidence QA",
        "privacy": "Aggregate counts only; no raw paths, game titles or mod names.",
        "games_by_launcher": dict(sorted(launcher_count.items())),
        "mod_roots_by_source": dict(sorted(mod_count.items())),
        "recorded_manager_profiles": len(profiles),
        "unresolved_locations": audit["unresolved_records"],
        "conflicting_ownership_claims": audit["ambiguous_claims"],
        "stale_manager_snapshots": audit["stale_manager_snapshots"],
        "incomplete_manager_snapshots": audit["incomplete_manager_snapshots"],
        "truncated_mod_scan_results": sum(bool(getattr(m, "truncated", False)) for m in mods),
        "confirmed_orphan_mods": 0,
        "automatic_cleanup_authorized": False,
        "scan_only": True,
        "manually_verified_against_launchers": False,
        "m2_release_accepted": False,
        "limitations": (
            "Read-only presence evidence. Human must compare Steam/Epic/GOG and "
            "MO2/Vortex profiles against their real apps on Windows 10/11. "
            "Missing manifests, unindexed Workshop items, disabled mods, old "
            "timestamps and redirected paths do not prove abandoned data."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Game Grave M2 local QA aggregate report.")
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly authorize on-demand local launcher/mod metadata reads.")
    parser.add_argument("--report", type=Path,
                        help="New JSON report path. Existing reports are never overwritten.")
    args = parser.parse_args(argv)
    if not args.execute or os.name != "nt":
        print("REFUSED: Windows and --execute are required. No scan performed.",
              file=sys.stderr)
        return 2
    from core import find_games, find_all_mod_storage
    from launchers import find_launcher_games
    from manager_profiles import inspect_manager_profiles
    try:
        print("Scanning installed launcher records and known mod locations read-only...",
              flush=True)
        games = find_games()
        other = find_launcher_games()
        mods = find_all_mod_storage(games=games)
        profiles = inspect_manager_profiles(mods, games, other)
        result = aggregate_results(games, other, mods, profiles)
        result["operating_system"] = {
            "release": platform.win32_ver()[0],
            "build": platform.win32_ver()[1],
        }
        data = json.dumps(result, indent=2, ensure_ascii=False)
        if args.report:
            target = args.report.resolve(strict=False)
            if target.exists() or target.is_symlink():
                raise FileExistsError("Report exists; choose a new filename.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as stream:
                stream.write(data + "\n")
        print(data)
        print("Report is not a certificate. Compare scan results with game launchers and managers.")
        return 0
    except KeyboardInterrupt:
        print("Scan canceled. Nothing deleted.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, InterruptedError) as exc:
        print(f"Read-only scan incomplete: {type(exc).__name__}. M2 remains OPEN.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
