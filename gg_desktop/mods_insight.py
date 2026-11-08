"""Read-only views over the Mods catalog: statuses, load order, profiles, conflicts, coverage.

Nothing here touches Qt, the network, a mod manager's state or any mod file. Every value is
derived from the bounded catalog and conflict report already built by mods_data/mod_conflicts,
plus the manager's own saved update fields (MO2 meta.ini). When evidence is missing the value
is "unknown", never a guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import time

from gg_desktop.mods_data import identity, ordinary, plain
from mod_sources import _read_ini

MAX_UPDATE_READS = 4000
NON_MOD_GRAVEYARD = {"Old game recording", "Old game screenshot", "Neglected installed game", "Manual review"}


@dataclass(frozen=True)
class Status:
    text: str
    kind: str  # green, amber, muted
    detail: str


def selected_profile_keys(catalog):
    return {p.key for p in catalog.profiles if p.selected}


def entry_status(entry, catalog) -> Status:
    """Activation as saved by the mod manager. Locations are storage, not individual mods."""
    if entry.kind != "mod":
        return Status("Protected", "muted", "Protected mod storage; individual activation is not established for a whole location.")
    known = {p.key: p for p in catalog.profiles}
    marks = {k: m for k, m in entry.profiles.items() if k in known}
    if not marks:
        return Status("Unknown", "muted", "No saved profile established whether this mod is enabled.")
    active = selected_profile_keys(catalog) & set(marks)
    pool = {k: marks[k] for k in active} if active else marks
    values = set(pool.values())
    scope = "the profile selected when it was inspected" if active else "every saved profile that lists it"
    if values == {"+"}:
        return Status("Enabled", "green", f"Enabled in {scope}.")
    if values == {"-"}:
        return Status("Disabled", "muted", f"Disabled in {scope}.")
    if "+" in values and "-" in values:
        return Status("Mixed", "amber", f"Enabled in some saved profiles and disabled in others ({scope}).")
    return Status("Unknown", "muted", "Saved profiles list this mod without an enabled or disabled marker.")


# ---- update evidence (MO2 meta.ini only: what the manager itself last recorded)
@dataclass(frozen=True)
class UpdateInfo:
    installed: str
    newest: str
    outdated: bool | None  # None: not comparable
    note: str


def _numbers(value: str):
    match = re.fullmatch(r"\s*v?(\d+(?:\.\d+){0,5})\s*", str(value))
    return tuple(int(x) for x in match[1].split(".")) if match else None


def compare_versions(installed: str, newest: str) -> bool | None:
    """True when newest is strictly newer. Only plain numeric versions are compared."""
    a, b = _numbers(installed), _numbers(newest)
    if a is None or b is None:
        return None
    width = max(len(a), len(b))
    return b + (0,) * (width - len(b)) > a + (0,) * (width - len(a))


def read_update_info(entry) -> UpdateInfo | None:
    """What MO2 saved about updates for one mod folder. No network; bounded; read-only."""
    if entry.kind != "mod" or entry.source != "Mod Organizer 2":
        return None
    meta = Path(entry.path) / "meta.ini"
    if not ordinary(meta):
        return None
    cfg = _read_ini(meta)
    if cfg is None or not cfg.has_section("General"):
        return None
    general = cfg["General"]
    installed = plain(general.get("version"), 100)
    newest = plain(general.get("newestVersion"), 100)
    ignored = plain(general.get("ignoredVersion"), 100)
    if not newest:
        return UpdateInfo(installed, "", None, "MO2 has not recorded a newer version for this mod.")
    if ignored and ignored == newest:
        return UpdateInfo(installed, newest, False, "MO2 records this newer version as ignored.")
    result = compare_versions(installed, newest)
    if result is None:
        return UpdateInfo(installed, newest, None, "The installed and newest versions use a format Game Grave cannot compare.")
    return UpdateInfo(installed, newest, result,
                      "MO2's saved update check lists a newer version." if result else "Matches MO2's newest recorded version.")


def scan_updates(entries, canceled=lambda: False):
    result = {}
    for entry in entries[:MAX_UPDATE_READS]:
        if canceled():
            break
        info = read_update_info(entry)
        if info:
            result[entry.key] = info
    return result


# ---- references
def referenced_by_saved_profiles(entry, catalog):
    """True/False when profile coverage is complete for this mod's instance, otherwise None."""
    if entry.kind != "mod" or entry.source != "Mod Organizer 2" or not entry.manager_folder:
        return None
    base = identity(entry.manager_folder).rstrip("/\\")
    same = [p for p in catalog.profiles if p.manager == "Mod Organizer 2" and identity(p.source).startswith(base)]
    if not same or any(p.incomplete or p.stale for p in same):
        return None
    return any(entry.key in p.members for p in same)


def unreferenced(catalog):
    return [e for e in catalog.entries if referenced_by_saved_profiles(e, catalog) is False]


# ---- metric tiles
def metrics(catalog, report, updates):
    mods = [e for e in catalog.entries if e.kind == "mod"]
    statuses = [entry_status(e, catalog) for e in mods]
    out = {
        "total": len(mods) or len(catalog.entries),
        "total_label": "Total Mods" if mods else "Mod Locations",
        "enabled": sum(s.text == "Enabled" for s in statuses),
        "mixed": sum(s.text == "Mixed" for s in statuses),
        "disabled": sum(s.text == "Disabled" for s in statuses),
        "outdated": None if not updates else sum(bool(i.outdated) for i in updates.values()),
        "conflicts": None if report is None else len(report.findings),
        "conflicts_limited": bool(report and report.limited),
        "unreferenced": None,
    }
    judged = [referenced_by_saved_profiles(e, catalog) for e in mods]
    if any(v is not None for v in judged):
        out["unreferenced"] = sum(v is False for v in judged)
    return out


# ---- tab rows
def load_order(catalog, profile_key):
    """Relative order inside one saved profile. MO2 stores modlist.txt highest priority first, so
    the list is reversed to read like MO2's left pane (position 1 loads first, higher overrides)."""
    profile = next((p for p in catalog.profiles if p.key == profile_key), None)
    if profile is None:
        return [], "Choose a saved profile."
    lookup = {e.key: e for e in catalog.entries}
    if profile.manager != "Mod Organizer 2":
        rows = [(None, lookup[k], m) for k, m in profile.members.items() if k in lookup]
        return rows, ("Load order is not established for this manager's saved snapshot. "
                      "Open the manager to read or change it.")
    keys = [k for k in profile.members if k in lookup]
    rows = [(pos, lookup[k], profile.members[k]) for pos, k in enumerate(reversed(keys), 1)]
    note = ("Order read from this profile's modlist.txt. Position 1 loads first and a higher position overrides "
            "lower ones. Separators and base-game entries are not counted, so positions are relative.")
    if profile.stale:
        note += " The saved list is more than seven days old."
    return rows, note


def profile_rows(catalog, report):
    findings = {}
    if report:
        for f in report.findings:
            findings[f.profile] = findings.get(f.profile, 0) + 1
    rows = []
    for p in catalog.profiles:
        marks = list(p.members.values())
        rows.append({"profile": p, "enabled": marks.count("+"), "disabled": marks.count("-"),
                     "unknown": len(marks) - marks.count("+") - marks.count("-"),
                     "findings": findings.get(p.key, 0) if report else None})
    return rows


def conflict_rows(catalog, report, profile_key=""):
    if report is None:
        return []
    lookup = {e.key: e.name for e in catalog.entries}
    names = {p.key: p.name for p in catalog.profiles}
    rows = []
    for f in report.findings:
        if profile_key and f.profile != profile_key:
            continue
        rows.append({"finding": f, "profile": names.get(f.profile, "Unknown profile"),
                     "mods": [lookup.get(k, "Unknown mod") for k in f.mods]})
    return rows


def radar_rows(catalog, report, inventory, extra_roots):
    """Plain coverage facts, one per line."""
    when = lambda value: time.strftime("%Y-%m-%d %H:%M", time.localtime(value)) if value else "never"
    mods = [e for e in catalog.entries if e.kind == "mod"]
    rows = [("Inventory", f"{len(inventory.mods)} scanned locations, {len(mods)} individual mods read", "info"),
            ("Saved profiles", f"{len(catalog.profiles)} read" + (" (partial coverage)" if catalog.limited else ""),
             "warn" if catalog.limited else "info")]
    if report:
        rows.append(("Conflict check", report.summary() + " Completed " + when(report.checked_at) + ".",
                     "warn" if report.limited else "info"))
    else:
        rows.append(("Conflict check", "Not run yet. Choose Check Conflicts.", "warn"))
    rows += [("Coverage note", w, "warn") for w in (list(catalog.warnings) + (list(report.warnings) if report else []))[:40]]
    return rows


def source_rows(inventory, extra_roots):
    rows = [{"name": m.name, "path": str(m.path), "kind": m.source, "state": m.status, "custom": False} for m in inventory.mods]
    known = {identity(r["path"]) for r in rows}
    for root in extra_roots:
        rows.append({"name": str(root).rstrip("/\\").rsplit("\\", 1)[-1].rsplit("/", 1)[-1] or str(root), "path": str(root),
                     "kind": "Added by you", "state": "Scanned on the next Scan for Mods" if identity(root) not in known else "Included in the last scan",
                     "custom": True})
    return rows


def cleanup_rows(catalog, inventory):
    """Review items only. Nothing here removes anything; removal stays in Graveyard and Old Files."""
    rows = []
    for e in inventory.graveyard:
        if e.category in NON_MOD_GRAVEYARD:
            continue
        rows.append({"name": e.name, "path": e.path, "kind": e.category, "size": e.apparent_bytes,
                     "note": e.finding, "removable": bool(e.can_recycle), "source": "graveyard"})
    for e in unreferenced(catalog):
        rows.append({"name": e.name, "path": e.path, "kind": "Not in any saved profile", "size": e.apparent_bytes,
                     "note": "Installed in the manager's mod folder but absent from every saved profile of that instance. "
                             "That does not show it is unused; review in your mod manager.",
                     "removable": False, "source": "unreferenced"})
    return rows


def export_selection(entries, catalog, report, updates):
    profiles = {p.key: p.name for p in catalog.profiles}
    items = []
    for e in entries:
        s = entry_status(e, catalog)
        u = updates.get(e.key)
        items.append({"name": e.name, "path": e.path, "manager": e.source, "version": e.version, "author": e.author,
                      "status": s.text, "status_detail": s.detail,
                      "profiles": {profiles.get(k, "Unknown"): m for k, m in e.profiles.items()},
                      "newest_recorded": u.newest if u else "", "outdated": u.outdated if u else None,
                      "findings": [{"kind": f.kind, "detail": f.detail} for f in (report.for_mod(e.key) if report else [])]})
    return {"format": "Game Grave selected mods v1",
            "scope": "Read-only local evidence. No file was changed. Runtime compatibility is unverified.",
            "count": len(items), "mods": items}


def dumps(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2)
