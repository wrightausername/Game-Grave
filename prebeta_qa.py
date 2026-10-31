"""Path-free, fail-closed local Windows 1.0 pre-beta QA summary.

This never approves a release. Local scans and disposable integrity tests
provide evidence a human may compare to actual launcher/manager UI results.
No usernames, filenames, game names, mod names or source paths enter output.
"""
from __future__ import annotations

from collections import Counter

from tools.m2_real_pc_qa import LAUNCHER_CATEGORIES, MOD_CATEGORIES

SCHEMA = 1
BETA_READY = False
CATEGORIES = {
    "games_by_launcher": (*LAUNCHER_CATEGORIES, "Other"),
    "mod_roots_by_source": (*MOD_CATEGORIES, "Other"),
}
RESULTS = {"PASS", "FAIL", "NOT_RUN"}


def _count(value: object) -> int:
    return value if type(value) is int and 0 <= value <= 100000 else 0


def _safe_categories(section: object, names: tuple[str, ...]) -> dict:
    records = section if isinstance(section, dict) else {}
    return {name: _count(records.get(name, 0)) for name in names}


def build_prebeta_report(
    *,
    os_release: str,
    os_build: str,
    m2_report: dict | None,
    m3_report: dict | None,
    m1_status: str,
    errors: dict[str, str] | None = None,
) -> dict:
    """Whitelisted aggregate evidence. Human acceptance is always false."""
    if m1_status not in RESULTS:
        raise ValueError("Unrecognized disposable Undo QA status")
    tests = (m3_report or {}).get("checks", []) if isinstance(m3_report, dict) else []
    # Tests are hardcoded in the local disposable suite, but even so, do not
    # export their messages or names into this aggregate.
    statuses = Counter(item.get("status") for item in tests if isinstance(item, dict))
    raw = m2_report or {}
    error_classes = errors or {}
    allowed_errors = {"M1", "M2", "M3"}
    return {
        "schema": SCHEMA,
        "purpose": "Game Grave local 1.0 pre-beta diagnostic",
        "privacy": "Counts/statuses only. No game, mod, profile, path, filename or account names.",
        "windows_release": os_release if os_release in ("Windows 10", "Windows 11")
                           else "Unknown Windows",
        "windows_build": os_build if isinstance(os_build, str) and os_build.isdecimal()
                         and len(os_build) <= 10 else "unknown",
        "m1_disposable_recycle_undo": m1_status,
        "m1_windows_10_11_human_acceptance": False,
        "m2_read_only_scan": "PASS" if m2_report is not None else "FAIL",
        "m2_games_by_launcher": _safe_categories(
            raw.get("games_by_launcher"), CATEGORIES["games_by_launcher"]),
        "m2_mod_roots_by_source": _safe_categories(
            raw.get("mod_roots_by_source"), CATEGORIES["mod_roots_by_source"]),
        "m2_manager_profiles": _count(raw.get("recorded_manager_profiles")),
        "m2_conflicting_ownership_claims": _count(raw.get("conflicting_ownership_claims")),
        "m2_unresolved_mod_locations": _count(raw.get("unresolved_locations")),
        "m2_stale_manager_snapshots": _count(raw.get("stale_manager_snapshots")),
        "m2_incomplete_manager_snapshots": _count(raw.get("incomplete_manager_snapshots")),
        "m2_human_launcher_comparison": False,
        "m3_disposable_tests": {
            "passed": _count(statuses["PASS"]),
            "failed": _count(statuses["FAIL"]),
            "executed": _count(len(tests)),
            "all_passed": bool((m3_report or {}).get("all_passed") and
                               statuses["FAIL"] == 0 and statuses["PASS"] > 0),
            "real_mod_manager_tested": False,
        },
        "m4_physical_dpi_and_accessibility_verified": False,
        "m5_signed_installer_and_paid_entitlements_verified": False,
        "error_kinds": {name: error_classes[name] if error_classes[name] in
                        ("OSError", "ValueError", "RuntimeError",
                         "InterruptedError", "PermissionError", "SafetySelfCheckError")
                        else "Other"
                        for name in ("M1", "M2", "M3")
                        if name in error_classes and name in allowed_errors},
        "automatic_delete_authorized": False,
        "m6_beta_authorized": False,
        "m7_1_0_release_approved": False,
        "limitations": (
            "Local counts and synthetic recoveries only. Compare against real launcher "
            "and mod-manager screens and complete physical Windows 10/11, backup, "
            "accessibility, signed installer, privacy, payments and closed-beta QA. "
            "No acceptance gate is automatically passed."
        ),
    }
