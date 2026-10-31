"""Run one bounded, opt-in, local Windows pre-beta engineering diagnostic.

NEVER approves release gates or tests real game restore. All temporary kit files
are fabricated, inside a user-selected ordinary folder. M1 Recycle Bin test is
a separate explicit opt-in using only a uniquely owned disposable test file.

Example:
    python tools/windows_prebeta_qa.py --execute --folder C:\\GameGraveQA \\
        --report C:\\GameGraveQA\\local-qa.json --run-undo-check
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    args_parser = argparse.ArgumentParser(
        description="Game Grave read-only/synthetic Windows 1.0 pre-beta QA")
    args_parser.add_argument("--execute", action="store_true",
                             help="Explicitly approve local metadata scan and synthetic kit QA")
    args_parser.add_argument("--folder", type=Path, required=True,
                             help="Existing ordinary local folder for disposable test work")
    args_parser.add_argument("--report", type=Path, required=True,
                             help="New JSON report filename inside --folder; never overwritten")
    args_parser.add_argument("--run-undo-check", action="store_true",
                             help="Separately opt in to ONE disposable Windows Recycle Bin/Undo test")
    args = args_parser.parse_args(argv)

    if os.name != "nt" or not args.execute:
        print("REFUSED: interactive Windows and --execute are required.", file=sys.stderr)
        return 2
    from core import safe_scan_root, is_protected_path, find_games, find_all_mod_storage
    from launchers import find_launcher_games
    from manager_profiles import inspect_manager_profiles
    from tools.m2_real_pc_qa import aggregate_results
    from tools.windows_m3_disposable_qa import run_disposable_suite
    from prebeta_qa import build_prebeta_report
    from safety_selftest import check_disposable_undo

    root = args.folder.expanduser().absolute()
    output = args.report.expanduser().absolute()
    if (not safe_scan_root(root) or is_protected_path(root)
            or output.parent != root or
            output.suffix.casefold() != ".json" or
            output.exists() or output.is_symlink()):
        print("REFUSED: choose an ordinary unprotected folder and a NEW JSON report "
              "filename directly inside it. Nothing tested.", file=sys.stderr)
        return 2

    m1 = "NOT_RUN"
    m2 = None
    m3 = None
    errors = {}
    if args.run_undo_check:
        print("Checking only a Game Grave-owned tiny disposable test file...")
        try:
            check_disposable_undo(root)
            m1 = "PASS"
        except (OSError, ValueError, RuntimeError) as exc:
            m1 = "FAIL"
            errors["M1"] = type(exc).__name__
            print("Disposable Windows recovery check incomplete; do not bypass "
                  "recycling safeguards.")

    print("Reading existing launcher, game and mod-manager metadata; no cleanup...")
    try:
        games = find_games()
        other = find_launcher_games()
        mods = find_all_mod_storage(games=games)
        profiles = inspect_manager_profiles(mods, games, other)
        m2 = aggregate_results(games, other, mods, profiles)
        print("Read-only game and Mod Radar metadata scan completed.")
    except (OSError, ValueError, RuntimeError, InterruptedError) as exc:
        errors["M2"] = type(exc).__name__
        print("Read-only launcher/mod inventory incomplete; no deletion attempted.")

    print("Running isolated synthetic Save/Mods/Profile archive restoration tests...")
    try:
        m3 = run_disposable_suite(root)
        print("Synthetic kit tests complete; no personal save was opened or changed.")
    except (OSError, ValueError, RuntimeError, InterruptedError) as exc:
        errors["M3"] = type(exc).__name__
        print("Synthetic kit QA incomplete; no personal files selected.")

    win = platform.win32_ver()
    build = win[1]
    edition = platform.win32_edition()
    # Hosted Windows Server build numbers overlap consumer Windows 10/11.
    # Report them as unknown, never as a passed consumer-desktop test.
    major = ("Unknown Windows" if "server" in edition.casefold() else
             "Windows 11" if build.isdecimal() and int(build) >= 22000 else
             "Windows 10" if build.isdecimal() and int(build) > 0 else
             "Unknown Windows")
    report = build_prebeta_report(
        os_release=major, os_build=build,
        m1_status=m1, m2_report=m2, m3_report=m3, errors=errors)
    try:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError:
        print("Unable to create a new path-free report. Prior reports unchanged.",
              file=sys.stderr)
        return 2
    print("Aggregate report saved. Contains counts/status only, not names or paths. "
          "Manual M1–M5 Windows acceptance remains REQUIRED.")
    if report["m2_read_only_scan"] != "PASS" or not report["m3_disposable_tests"]["all_passed"]:
        return 1
    if args.run_undo_check and m1 != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
