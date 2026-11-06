"""Evidence checks for saved mod profiles; never edits or activates mods."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations
import os
from pathlib import Path
import re
import time

from gg_desktop.mods_data import Catalog, ordinary

MAX_PATHS = 100000
MAX_MOD_PATHS = 10000
MAX_DEPTH = 12
MAX_FINDINGS = 2000
HOST_IDS = {"base", "minecraft", "java", "fabricloader", "forge", "neoforge", "smapi",
            "stardewvalley", "skse", "skse64", "f4se", "obse", "nvse"}
IGNORED = {"meta.ini", "manifest.json", "modinfo.json", "info.json", "fabric.mod.json", "project.json",
           "__folder_managed_by_vortex", "vortex.deployment.json"}


@dataclass
class Finding:
    kind: str
    profile: str
    mods: tuple[str, ...]
    detail: str
    paths: list[str] = field(default_factory=list)
    count: int = 0


@dataclass
class ConflictReport:
    checked_at: int
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    profiles_checked: int = 0
    mods_checked: int = 0
    paths_checked: int = 0
    limited: bool = False

    def for_mod(self, key):
        return [f for f in self.findings if key in f.mods]

    def summary(self):
        coverage = "Limited coverage. " if self.limited else ""
        return (f"{coverage}{len(self.findings)} findings in {self.profiles_checked} saved profiles; "
                f"{self.mods_checked} enabled mod folders and {self.paths_checked} file paths inspected. "
                "Runtime compatibility and load-order winners are unverified.")

    def export(self, catalog):
        return {
            "format": "Game Grave Mod Radar evidence report v1",
            "scope": "Read-only local metadata and saved profiles; runtime compatibility is unverified. "
                     "File overlaps may be intentional overrides. No deletion or repair is authorized by this report.",
            "report": asdict(self),
            "catalog_inspected_at": catalog.inspected_at,
            "catalog_limited": catalog.limited,
            "catalog_warnings": catalog.warnings,
            "mods": [{**asdict(e), "identifiers": sorted(e.identifiers)} for e in catalog.entries],
            "profiles": [asdict(p) for p in catalog.profiles],
        }


def version_satisfies(installed, requirement):
    """Only compare simple numeric versions; unknown syntax stays unverified."""
    if not requirement or requirement == "*":
        return True
    actual = re.fullmatch(r"v?(\d+(?:\.\d+){0,4})", installed.strip())
    wanted = re.fullmatch(r"\s*(>=|<=|==|!=|>|<|=)?\s*v?(\d+(?:\.\d+){0,4})\s*", requirement)
    if not actual or not wanted:
        return None
    left, right = (tuple(int(x) for x in value.split(".")) for value in (actual[1], wanted[2]))
    width = max(len(left), len(right))
    left, right = left + (0,) * (width - len(left)), right + (0,) * (width - len(right))
    return {">=": left >= right, "<=": left <= right, "==": left == right,
            "=": left == right, "!=": left != right, ">": left > right, "<": left < right}[wanted[1] or "="]


def inspect_conflicts(catalog: Catalog, canceled=lambda: False, progress=lambda *_: None):
    report = ConflictReport(int(time.time()), warnings=list(catalog.warnings), limited=catalog.limited)
    entries = {e.key: e for e in catalog.entries}
    cache, visited = {}, [0]

    def check():
        if canceled():
            raise InterruptedError("Conflict inspection canceled; previous report retained.")

    def add(kind, profile, mods, detail, paths=None, count=0):
        if len(report.findings) >= MAX_FINDINGS:
            report.limited = True
            if "Finding limit reached." not in report.warnings:
                report.warnings.append("Finding limit reached.")
            return
        report.findings.append(Finding(kind, profile.key, tuple(mods), detail, paths or [], count))

    def files(node):
        if node.key in cache:
            return cache[node.key]
        check()
        found = set()
        cache[node.key] = found
        root = Path(node.path)
        if not ordinary(root, True):
            report.limited = True
            return found
        report.mods_checked += 1
        stack, mod_paths = [(root, 0)], 0
        incomplete = False
        while stack:
            check()
            folder, depth = stack.pop()
            try:
                with os.scandir(folder) as stream:
                    for item in stream:
                        check()
                        mod_paths += 1
                        visited[0] += 1
                        if mod_paths > MAX_MOD_PATHS or visited[0] > MAX_PATHS:
                            incomplete = True
                            stack.clear()
                            break
                        path = Path(item.path)
                        if item.name.casefold() == "fomod":
                            continue
                        if item.is_dir(follow_symlinks=False) and ordinary(path, True):
                            if depth < MAX_DEPTH:
                                stack.append((path, depth + 1))
                            else:
                                incomplete = True
                        elif item.is_file(follow_symlinks=False) and ordinary(path):
                            name = item.name.casefold()
                            if (name in IGNORED or name.startswith(("readme", "license", "changelog"))
                                    or name.endswith((".mohidden", ".vortex_backup"))):
                                continue
                            found.add(path.relative_to(root).as_posix().casefold())
                            report.paths_checked += 1
                        else:
                            incomplete = True
            except OSError:
                incomplete = True
            if visited[0] > MAX_PATHS:
                break
        if incomplete:
            report.limited = True
            report.warnings.append(node.name + ": linked, unreadable or bounded content was skipped.")
        return found

    total = max(1, len(catalog.profiles))
    for index, profile in enumerate(catalog.profiles):
        check()
        progress(int(index * 100 / total), "Inspecting saved profile: " + profile.name)
        if profile.source_mtime_ns:
            try:
                source = Path(profile.source)
                if not ordinary(source):
                    raise ValueError("Profile source unavailable")
                info = source.stat()
                if (info.st_mtime_ns, info.st_size) != (profile.source_mtime_ns, profile.source_size):
                    raise ValueError("Profile source changed")
            except (OSError, ValueError):
                report.limited = True
                report.warnings.append(profile.name + ": source changed or became unavailable after inspection. Refresh details before checking this profile.")
                continue
        report.profiles_checked += 1
        if profile.stale:
            report.warnings.append(profile.name + ": Vortex snapshot is older than seven days; state may have changed.")
            report.limited = True
        if profile.incomplete:
            report.limited = True
        available = [entries[k] for k in profile.members if k in entries]
        enabled = [e for e in available if profile.members[e.key] == "+"]
        unknown = [e for e in available if profile.members[e.key] == "?"]
        if unknown:
            report.limited = True
            report.warnings.append(profile.name + ": some activation markers are unknown and were excluded from overlap checks.")
        by_id = {}
        for entry in available:
            for name in entry.identifiers | {entry.name, Path(entry.path).name}:
                by_id.setdefault(name.casefold(), []).append(entry)
        deployed = {}
        for node in enabled:
            check()
            if not ordinary(node.path, True):
                add("Enabled folder unavailable", profile, [node.key],
                    "Recorded enabled in this saved profile, but the ordinary staging folder is missing, unreadable or redirected.")
                report.limited = True
            for dependency in node.dependencies:
                check()
                if dependency.optional:
                    continue
                name = dependency.name.casefold()
                if name in HOST_IDS or name.endswith((".esm", ".esp", ".esl", ".dll")):
                    add("Requirement unverified", profile, [node.key],
                        "Declared game, loader or plugin requirement: " + dependency.name + " " + dependency.version)
                    continue
                matches = by_id.get(name, [])
                active = list({e.key: e for e in matches if profile.members[e.key] == "+"}.values())
                if dependency.incompatible:
                    if active:
                        verdicts = [version_satisfies(e.version, dependency.version) for e in active]
                        if True in verdicts or None in verdicts:
                            add("Declared incompatibility" if True in verdicts else "Incompatibility version unverified",
                                profile, [node.key, *[e.key for e in active]],
                                "Local metadata declares incompatibility with " + dependency.name + " " + dependency.version +
                                "; both are recorded enabled. Review the declared version condition.")
                elif not active:
                    uncertain = any(profile.members[e.key] == "?" for e in matches)
                    add("Requirement unverified" if uncertain else "Required dependency not enabled", profile, [node.key],
                        "Local metadata requires " + dependency.name + " " + dependency.version +
                        "; it is not recorded enabled in this saved profile. Review its manager and plugin requirements.")
                elif dependency.version:
                    verdicts = [version_satisfies(e.version, dependency.version) for e in active]
                    if True not in verdicts:
                        add("Version requirement unverified" if None in verdicts else "Dependency version mismatch", profile,
                            [node.key, *[e.key for e in active]], "Declared requirement: " + dependency.name + " " + dependency.version +
                            "; recorded versions: " + ", ".join(e.version for e in active))
            for path in files(node):
                deployed.setdefault(path, []).append(node.key)
        for rule in profile.rules:
            check()
            owner, target = rule["owner"], rule["target"]
            if profile.members.get(owner) != "+":
                continue
            if rule["kind"] == "conflicts" and profile.members.get(target) == "+":
                add("Declared manager incompatibility", profile, [owner, target],
                    "The saved Vortex JSON snapshot declares a conflict rule between these enabled mods.")
            elif rule["kind"] == "requires" and profile.members.get(target) != "+":
                add("Required dependency not enabled", profile, [owner],
                    "The saved Vortex JSON snapshot requires " + (entries[target].name if target in entries else "mod ID " + target) +
                    "; it is not recorded enabled in this saved profile.")
        pairs = {}
        for path, owners in deployed.items():
            check()
            owners = sorted(set(owners))
            for pair in combinations(owners, 2):
                check()
                if pair not in pairs and len(pairs) >= MAX_FINDINGS:
                    report.limited = True
                    break
                count, paths = pairs.setdefault(pair, [0, []])
                pairs[pair][0] = count + 1
                if len(paths) < 10:
                    paths.append(path)
        for pair, (count, paths) in pairs.items():
            add("File overlap — review load order", profile, pair,
                f"{count} relative file paths occur in both enabled mod folders. An override can be intentional; "
                "the effective winner and in-game compatibility have not been established.", paths, count)
    unprofiled = sum(e.kind == "mod" and not e.profiles for e in catalog.entries)
    if unprofiled or not catalog.profiles:
        report.warnings.append(f"{unprofiled} individual mods have no saved profile state. Their activation and overlaps were not inferred.")
        report.limited = True
    report.warnings = list(dict.fromkeys(report.warnings))[:200]
    progress(100, "Saved profile checks complete")
    return report
