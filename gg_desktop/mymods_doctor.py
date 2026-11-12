"""Mod Doctor: plain-words problems in one Mod Organizer 2 profile, each with the fix Game Grave can do. Reads files only.

Checks:
* a switched-on mod has a plugin that needs a master file nobody provides (from the plugin's own header);
  if a switched-off mod has that file, the fix is "Turn on <mod>";
* a mod in the list whose folder is gone;
* the same Nexus mod switched on twice;
* updates Mod Organizer 2 recorded from Nexus (newer version than installed);
* clashes: switched-on mods that ship the same file, and which one wins (the one lower in the list).
Nothing is changed here; fixes go through mymods_core's snapshot-and-undo writes.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import os
from pathlib import Path

from gg_desktop import mymods_core as mc

MAX_CLASH_FILES = 400_000
SKIP_FILES = {"meta.ini", "readme.txt", "readme.md", "changelog.txt", "license.txt"}
BASE_PLUGINS = {"skyrim.esm", "update.esm", "dawnguard.esm", "hearthfires.esm", "dragonborn.esm", "fallout4.esm",
                "dlcrobot.esm", "dlcworkshop01.esm", "dlccoast.esm", "dlcworkshop02.esm", "dlcworkshop03.esm",
                "dlcnukaworld.esm", "starfield.esm", "fallout3.esm", "falloutnv.esm", "oblivion.esm", "morrowind.esm"}


@dataclass(frozen=True)
class Finding:
    kind: str                 # "missing_master", "needs_mod_on", "folder_missing", "duplicate", "update", "clash"
    title: str                # one plain sentence
    detail: str = ""
    mods: tuple = ()          # mod names involved
    fix: str = ""             # "turn_on", "open_nexus", "" (no automatic fix)
    fix_label: str = ""
    fix_mods: tuple = ()
    url: str = ""


@dataclass
class Report:
    findings: list = field(default_factory=list)
    clashes: list = field(default_factory=list)   # (winner, loser, files)
    checked_plugins: int = 0
    clash_files_read: int = 0
    clash_limited: bool = False

    def of(self, *kinds):
        return [f for f in self.findings if f.kind in kinds]

    @property
    def problems(self):
        return self.of("missing_master", "needs_mod_on", "folder_missing", "duplicate")

    @property
    def updates(self):
        return self.of("update")


NEXUS_DOMAINS = {"skyrimse": "skyrimspecialedition", "skyrim special edition": "skyrimspecialedition",
                 "skyrim": "skyrim", "fallout4": "fallout4", "fallout 4": "fallout4", "starfield": "starfield",
                 "falloutnv": "newvegas", "new vegas": "newvegas", "fallout3": "fallout3", "oblivion": "oblivion",
                 "morrowind": "morrowind", "enderal": "enderal", "enderal special edition": "enderalspecialedition",
                 "cyberpunk 2077": "cyberpunk2077", "baldur's gate 3": "baldursgate3", "stardew valley": "stardewvalley",
                 "skyrimvr": "skyrimspecialedition", "fallout4vr": "fallout4"}


def nexus_url(mod: mc.Mod, game: str) -> str:
    if mod.url.startswith("https://www.nexusmods.com/"):
        return mod.url
    if not mod.nexus_id:
        return ""
    domain = NEXUS_DOMAINS.get((mod.game or game or "").casefold().strip(), "")
    return f"https://www.nexusmods.com/{domain}/mods/{mod.nexus_id}?tab=files" if domain else ""


def _data_plugins(game_path):
    if not game_path:
        return set()
    data = Path(game_path) / "Data"
    try:
        return {p.name.casefold() for p in data.iterdir() if p.suffix.lower() in mc.PLUGIN_EXT}
    except OSError:
        return set()


def diagnose(instance: mc.Instance, profile: mc.Profile, *, read_masters=mc.plugin_masters, walk=os.walk,
             base_plugins=None, clash_cap=MAX_CLASH_FILES) -> Report:
    report = Report()
    mods = [m for m in profile.mods if m.kind == "mod"]
    on = [m for m in mods if m.enabled]
    off = [m for m in mods if not m.enabled]
    provided = set(BASE_PLUGINS) | (base_plugins if base_plugins is not None else _data_plugins(instance.game_path))
    for m in on:
        provided |= {p.casefold() for p in m.plugins}
    off_owner = {}
    for m in off:
        for p in m.plugins:
            off_owner.setdefault(p.casefold(), m.name)

    # folders that are gone
    for m in mods:
        if not (instance.mods_dir / m.name).is_dir():
            report.findings.append(Finding("folder_missing", f"{m.name} is in the list but its folder is missing.",
                                           "Mod Organizer 2 will skip it. Reinstall it or remove it from the list in MO2.",
                                           (m.name,)))

    # masters
    needs_on = defaultdict(set)
    for m in on:
        for plugin in m.plugins:
            report.checked_plugins += 1
            for master in read_masters(instance.mods_dir / m.name / plugin):
                key = master.casefold()
                if key in provided:
                    continue
                if key in off_owner:
                    needs_on[off_owner[key]].add((m.name, master))
                else:
                    report.findings.append(Finding(
                        "missing_master", f"{m.name} needs {master}, and no mod here has it.",
                        "The game can crash at the main menu without it. Install the mod that provides it, or turn "
                        f"{m.name} off.", (m.name,)))
    for owner, pairs in sorted(needs_on.items()):
        users = sorted({u for u, _ in pairs})
        files = sorted({f for _, f in pairs})
        report.findings.append(Finding(
            "needs_mod_on", f"{', '.join(users[:2])}{' and others' if len(users) > 2 else ''} need{'s' if len(users) == 1 else ''} "
            f"{owner} turned on.", f"It provides {', '.join(files[:3])}.", tuple(users), "turn_on", f"Turn on {owner}",
            (owner,)))

    # duplicates
    by_id = defaultdict(list)
    for m in on:
        if m.nexus_id:
            by_id[m.nexus_id].append(m.name)
    for nexus_id, names in sorted(by_id.items()):
        if len(names) > 1:
            report.findings.append(Finding("duplicate", f"The same mod is turned on twice: {' and '.join(names[:3])}.",
                                           "Usually you want only the newer copy on.", tuple(names)))

    # updates
    for m in mods:
        if m.update:
            report.findings.append(Finding("update", f"{m.name}: update {m.version} → {m.newest}.",
                                           "Mod Organizer 2 saw this on Nexus. Download it there; MO2 installs it.",
                                           (m.name,), "open_nexus" if nexus_url(m, instance.game) else "",
                                           "See what's new", (m.name,), nexus_url(m, instance.game)))

    # clashes (bounded)
    owners = defaultdict(list)
    read = 0
    for m in on:
        root = instance.mods_dir / m.name
        for folder, _dirs, files in walk(root):
            rel_dir = os.path.relpath(folder, root)
            for f in files:
                if f.casefold() in SKIP_FILES and rel_dir == ".":
                    continue
                read += 1
                if read > clash_cap:
                    report.clash_limited = True
                    break
                owners[os.path.normcase(os.path.join(rel_dir, f))].append(m.name)
            if report.clash_limited:
                break
        if report.clash_limited:
            break
    report.clash_files_read = min(read, clash_cap)
    order = {m.name: i for i, m in enumerate(profile.mods)}
    pairs = defaultdict(int)
    for names in owners.values():
        if len(names) > 1:
            ranked = sorted(set(names), key=lambda n: order.get(n, 0))
            winner = ranked[-1]
            for loser in ranked[:-1]:
                pairs[(winner, loser)] += 1
    report.clashes = sorted(((w, l, n) for (w, l), n in pairs.items()), key=lambda t: -t[2])
    for winner, loser, n in report.clashes[:50]:
        report.findings.append(Finding("clash", f"{winner} and {loser} change the same {n} file{'s' if n != 1 else ''}.",
                                       f"{winner} wins because it's lower in the list. Drag {loser} below it if you "
                                       "want its version instead.", (winner, loser)))
    return report


def status_line(report: Report) -> tuple[str, str]:
    """(sentence, tone) for the top of the screen."""
    problems, updates, clashes = len(report.problems), len(report.updates), len(report.clashes)
    if problems:
        return (f"{problems} thing{'s' if problems != 1 else ''} need{'s' if problems == 1 else ''} you. "
                + ("Everything else looks good." if not updates else
                   f"{updates} update{'s' if updates != 1 else ''} ready too."), "warn")
    if updates:
        return f"Your mods look healthy. {updates} update{'s' if updates != 1 else ''} ready.", "info"
    return "Your mods look healthy. Nothing needs you right now.", "good"
