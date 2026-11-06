"""Bounded, read-only Mods catalog and local descriptions.

Only accepted scan locations and their declared manager profiles are inspected.
This catalog never changes the shared inventory, manager state or load order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import urlsplit, parse_qs
from xml.etree import ElementTree

from core import MOD_INDICATOR_DIRS, _has_reparse_component
from mod_sources import _read_ini, _resolve_mo_path
from manager_profiles import _read_modlist, _identity

MAX_METADATA = 128 * 1024
MAX_SNAPSHOT = 32 * 1024 * 1024
MAX_MODS = 12000
MAX_CHILDREN = 3500
MAX_PROFILES = 100


def plain(value, limit=2000):
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v.get("name", "")) if isinstance(v, dict) else str(v) for v in value[:30])
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]*>|\|c[0-9a-fA-F]{6,8}|\|r", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def identity(path):
    return _identity(str(path))


def ordinary(path, directory=False):
    try:
        path = Path(path)
        info = path.lstat()
        return (not _has_reparse_component(path) and
                (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)))
    except (OSError, ValueError):
        return False


def text_file(path, limit=MAX_METADATA):
    path = Path(path)
    if not ordinary(path) or path.stat().st_size > limit:
        raise ValueError("Metadata unavailable, redirected or above the inspection limit.")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Metadata exceeded the inspection limit.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeError:
        return raw.decode("cp1252", errors="replace")


def mod_page(value):
    try:
        url = urlsplit(str(value))
        allowed = ("nexusmods.com", "steamcommunity.com", "curseforge.com", "modrinth.com", "thunderstore.io", "github.com")
        workshop = (url.hostname == "steamcommunity.com" and url.path.rstrip("/") == "/sharedfiles/filedetails"
                    and set(parse_qs(url.query)) == {"id"}
                    and len(parse_qs(url.query)["id"]) == 1 and parse_qs(url.query)["id"][0].isdecimal())
        if (url.scheme == "https" and url.hostname and not url.username and not url.password
                and url.port in (None, 443) and (not url.query or workshop) and not url.fragment
                and any(url.hostname == host or url.hostname.endswith("." + host) for host in allowed)):
            return url.geturl()
    except ValueError:
        pass
    return ""


@dataclass(frozen=True)
class Dependency:
    name: str
    version: str = ""
    optional: bool = False
    incompatible: bool = False


@dataclass
class ModEntry:
    key: str
    name: str
    path: str
    source: str
    state: str
    apparent_bytes: int | None = None
    description: str = "No description is declared in the inspected local metadata."
    author: str = "Unknown"
    version: str = "Unknown"
    page: str = ""
    metadata_source: str = "Scan evidence only"
    identifiers: set[str] = field(default_factory=set)
    dependencies: list[Dependency] = field(default_factory=list)
    profiles: dict[str, str] = field(default_factory=dict)
    game_key: str = ""
    manager_folder: str = ""
    root_key: str = ""
    kind: str = "location"
    warnings: list[str] = field(default_factory=list)


@dataclass
class Profile:
    key: str
    name: str
    manager: str
    source: str
    game_key: str = ""
    selected: bool | None = None
    stale: bool = False
    incomplete: bool = False
    members: dict[str, str] = field(default_factory=dict)
    rules: list[dict] = field(default_factory=list)
    source_mtime_ns: int = 0
    source_size: int = 0


@dataclass
class Catalog:
    entries: list[ModEntry] = field(default_factory=list)
    profiles: list[Profile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limited: bool = False
    inspected_at: int = 0


PURPOSES = {
    "Mod Organizer 2": "MO2 instance storage. Profiles declare enabled and disabled mods; saves, profiles and installed mods remain protected.",
    "Vortex": "Vortex managed staging or downloads. Saved JSON snapshots can describe profiles; the live database is not opened.",
    "Steam Workshop": "Steam Workshop subscription content or pending downloads. A missing manifest entry does not establish that an item is unused.",
    "Steam game folder": "Potential mod files inside a recorded game installation. Individual purpose and compatibility require mod metadata or manager review.",
    "Custom mod storage": "A user-selected mod storage location. Ownership, activation and deletion safety are not inferred from its name or age.",
}


def _game_for(path, inventory, within=False):
    target = identity(path)
    if not target:
        return ""
    matches = []
    for game in inventory.games:
        root = identity(game.install_path)
        if (len(game.claimed_by) == 1 and game.launcher != "Custom library" and "open_folder" in game.capabilities
                and ordinary(game.install_path, True)
                and root and (target == root or within and target.startswith(root.rstrip("/\\") + ("\\" if ":" in root[:3] else os.sep)))):
            matches.append(game.key)
    return matches[0] if len(matches) == 1 else ""


def base_catalog(inventory):
    result = Catalog(inspected_at=int(time.time()))
    for item in inventory.mods:
        path, source = str(getattr(item, "path", "")), str(getattr(item, "source", "Unknown"))
        key = "location:" + source + ":" + identity(path)
        entry = ModEntry(key, str(getattr(item, "name", Path(path).name)), path, source,
                         str(getattr(item, "status", "Protected")), getattr(item, "apparent_bytes", None),
                         description=PURPOSES.get(source, "Detected mod or addon storage. Local metadata can explain its contents; activation and compatibility are not inferred."),
                         game_key=_game_for(path, inventory, True), root_key=key)
        if getattr(item, "advice", ""):
            entry.description += " " + plain(item.advice, 500)
        if getattr(item, "truncated", False):
            entry.warnings.append("The original storage measurement was incomplete.")
        if source == "Steam Workshop":
            matches = [g.key for g in inventory.games if g.launcher == "Steam" and len(g.claimed_by) == 1
                       and any(identity(path) == identity(Path(s.library) / "steamapps" / "workshop" / "content" / str(s.app_id))
                               and identity(s.install_path) == identity(g.install_path) for s in inventory.steam)]
            if len(matches) == 1:
                entry.game_key = matches[0]
        result.entries.append(entry)
    return result


def _dependency(value, optional=False):
    text = plain(value, 180)
    if not text:
        return None
    prefix = re.match(r"^(\(\?\)|[?!~])\s*", text)
    incompatible = bool(prefix and prefix.group(1) == "!")
    optional = optional or bool(prefix and prefix.group(1) in ("?", "(?)", "~"))
    if prefix:
        text = text[prefix.end():]
    match = re.match(r"^([^<>=]+?)\s*([<>=].*)?$", text)
    return Dependency(match.group(1).strip(), (match.group(2) or "").strip(), optional, incompatible) if match else None


def inspect_metadata(entry):
    folder = Path(entry.path)
    entry.identifiers.update({entry.name, folder.name})
    if not ordinary(folder, directory=True):
        if ordinary(folder):
            entry.description = "Installed mod package. Packed contents and in-game behavior have not been inspected."
        else:
            entry.warnings.append("The mod folder is missing, unreadable or redirected.")
        return
    for filename in ("manifest.json", "modinfo.json", "info.json", "fabric.mod.json", "project.json"):
        target = folder / filename
        if not target.exists():
            continue
        try:
            data = json.loads(text_file(target))
            if not isinstance(data, dict):
                continue
            data = {str(k).casefold(): v for k, v in data.items()}
            entry.name = plain(data.get("title") or data.get("name") or entry.name, 200)
            entry.description = plain(data.get("description")) or entry.description
            entry.author = plain(data.get("author") or data.get("authors"), 200) or entry.author
            entry.version = plain(data.get("version") or data.get("version_number"), 100) or entry.version
            entry.page = mod_page(data.get("website_url") or data.get("homepage") or data.get("website")) or entry.page
            for name in (data.get("id"), data.get("uniqueid"), data.get("name"), data.get("full_name")):
                if isinstance(name, str):
                    entry.identifiers.add(name)
            if isinstance(data.get("author"), str) and isinstance(data.get("name"), str):
                entry.identifiers.add(data["author"] + "-" + data["name"])
            dependencies = data.get("dependencies", data.get("depends", []))
            if isinstance(dependencies, dict):
                entry.dependencies.extend(Dependency(plain(k, 180), plain(v, 100)) for k, v in list(dependencies.items())[:100])
                dependencies = []
            if isinstance(dependencies, list):
                for raw in dependencies[:100]:
                    if isinstance(raw, str):
                        # Thunderstore's declared Author-Name-Version reference.
                        value = re.sub(r"-\d+(?:\.\d+){1,3}$", "", raw) if filename == "manifest.json" else raw
                        dependency = _dependency(value)
                        if dependency:
                            entry.dependencies.append(dependency)
                    elif isinstance(raw, dict):
                        declared = {str(k).casefold(): v for k, v in raw.items()}
                        name = declared.get("uniqueid") or declared.get("id")
                        if isinstance(name, str):
                            version = declared.get("minimumversion", "")
                            entry.dependencies.append(Dependency(plain(name, 180), ">=" + str(version) if version else "",
                                                                 declared.get("isrequired") is False))
            for raw in list(data.get("breaks", {}))[:100] if isinstance(data.get("breaks"), dict) else []:
                entry.dependencies.append(Dependency(plain(raw, 180), plain(data["breaks"][raw], 100), incompatible=True))
            entry.metadata_source = str(target)
            break
        except (OSError, ValueError, TypeError):
            entry.warnings.append(filename + " could not be safely read.")
    meta = folder / "meta.ini"
    if meta.exists():
        try:
            text_file(meta)
            cfg = _read_ini(meta)
            if cfg is not None and cfg.has_section("General"):
                general = cfg["General"]
                entry.version = plain(general.get("version"), 100) or entry.version
                entry.author = plain(general.get("author"), 200) or entry.author
                entry.description = plain(general.get("description") or general.get("comments") or general.get("notes")) or entry.description
                entry.page = mod_page(general.get("url") or general.get("website")) or entry.page
                nexus_games = {"skyrimspecialedition": "skyrimspecialedition", "skyrim": "skyrim", "fallout4": "fallout4",
                               "falloutnewvegas": "newvegas", "oblivion": "oblivion", "starfield": "starfield"}
                game_name = re.sub(r"[^a-z0-9]", "", general.get("gameName", "").casefold())
                mod_id = general.get("modid", "")
                if not entry.page and game_name in nexus_games and mod_id.isdecimal() and int(mod_id) > 0:
                    entry.page = "https://www.nexusmods.com/" + nexus_games[game_name] + "/mods/" + mod_id
                entry.metadata_source = str(meta)
        except (OSError, ValueError):
            entry.warnings.append("MO2 mod metadata could not be safely read.")
    info = folder / "fomod" / "info.xml"
    if info.exists():
        try:
            raw = text_file(info)
            if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
                raise ValueError("XML declarations are not supported")
            document = ElementTree.fromstring(raw)
            fields = {node.tag.rsplit("}", 1)[-1].casefold(): " ".join(node.itertext()) for node in document}
            entry.name = plain(fields.get("name"), 200) or entry.name
            entry.description = plain(fields.get("description")) or entry.description
            entry.author = plain(fields.get("author"), 200) or entry.author
            entry.version = plain(fields.get("version"), 100) or entry.version
            entry.page = mod_page(fields.get("website")) or entry.page
            entry.metadata_source = str(info)
        except (OSError, ValueError, ElementTree.ParseError):
            entry.warnings.append("FOMOD description could not be safely read.")
    for suffix in (".toc", ".txt"):
        descriptor = folder / (folder.name + suffix)
        if not descriptor.exists():
            continue
        try:
            fields = {}
            for line in text_file(descriptor).splitlines()[:500]:
                if line.startswith("##") and ":" in line:
                    key, value = line[2:].split(":", 1)
                    fields[key.strip().casefold()] = value.strip()
            if not fields:
                continue
            entry.name = plain(fields.get("title"), 200) or entry.name
            entry.description = plain(fields.get("notes") or fields.get("description")) or entry.description
            entry.author = plain(fields.get("author"), 200) or entry.author
            entry.version = plain(fields.get("version"), 100) or entry.version
            for raw in re.split(r"[,\s]+", fields.get("dependencies", fields.get("dependson", fields.get("requireddeps", "")))):
                dependency = _dependency(raw)
                if dependency:
                    entry.dependencies.append(dependency)
            entry.metadata_source = str(descriptor)
            break
        except (OSError, ValueError):
            entry.warnings.append("Addon descriptor could not be safely read.")
    if entry.description.startswith("No description"):
        for filename in ("README.md", "README.txt", "readme.md", "readme.txt"):
            path = folder / filename
            if not path.exists():
                continue
            try:
                lines = [line.strip() for line in text_file(path, 64 * 1024).splitlines()
                         if line.strip() and not line.lstrip().startswith(("#", "![", "```"))]
                if lines:
                    entry.description = "Local documentation: " + plain(" ".join(lines[:8]), 1200)
                    entry.metadata_source = str(path)
                    break
            except (OSError, ValueError):
                entry.warnings.append("Local documentation could not be safely read.")
    entry.identifiers.add(entry.name)


def build_catalog(inventory, canceled=lambda: False):
    result = base_catalog(inventory)
    entries = {e.key: e for e in result.entries}
    roots = {e.key: e for e in result.entries}
    game_claims = {}
    scanned = list(zip(inventory.mods, result.entries))
    def check():
        if canceled():
            raise InterruptedError("Mod inspection canceled")
    def child(root, path, name=None):
        check()
        key = "mod:" + root.source + ":" + identity(path)
        if key in entries:
            return entries[key]
        if len(entries) >= MAX_MODS:
            result.limited = True
            return None
        node = ModEntry(key, name or Path(path).name, str(path), root.source, "Profile state not recorded",
                        root_key=root.key, kind="mod", game_key=root.game_key, manager_folder=root.manager_folder)
        inspect_metadata(node)
        entries[key] = node
        return node
    def children(folder, limit=MAX_CHILDREN):
        try:
            paths = list(islice(Path(folder).iterdir(), limit + 1))
            if len(paths) > limit:
                result.limited = True
                result.warnings.append("Directory inspection limit reached: " + str(folder))
            for path in sorted(paths[:limit], key=lambda p: p.name.casefold()):
                check()
                try:
                    info = path.lstat()
                    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                        result.limited = True
                        result.warnings.append("Linked or redirected content skipped: " + str(path))
                        continue
                except OSError:
                    result.limited = True
                    result.warnings.append("Directory entry became unavailable: " + str(path))
                    continue
                yield path
        except OSError:
            result.limited = True
            result.warnings.append("Directory could not be fully listed: " + str(folder))
    ini_roots = {}
    for raw, root in scanned:
        check()
        if root.source == "Mod Organizer 2":
            for indicator in getattr(raw, "indicators", ()):
                if indicator.startswith("MO2 INI: "):
                    ini_roots.setdefault(indicator[9:], []).append(root)
    if len(ini_roots) > 30:
        result.limited = True
        result.warnings.append("MO2 instance inspection limit reached.")
    for raw_ini, locations in list(ini_roots.items())[:30]:
        check()
        ini = Path(raw_ini)
        try:
            text_file(ini, 5 * 1024 * 1024)
            cfg = _read_ini(ini)
            if cfg is None or not cfg.has_section("Settings"):
                raise ValueError("MO2 instance settings unavailable")
            settings = cfg["Settings"]
            base = _resolve_mo_path(settings.get("base_directory", str(ini.parent)), ini.parent, ini.parent)
            storage = _resolve_mo_path(settings.get("mod_directory", "%BASE_DIR%/mods"), base, ini.parent)
            profiles = _resolve_mo_path(settings.get("profiles_directory", "%BASE_DIR%/profiles"), base, ini.parent)
            storage_row = next((r for r in locations if identity(r.path) == identity(storage)), None)
            profile_row = next((r for r in locations if identity(r.path) == identity(profiles)), None)
            if storage_row is None:
                raise ValueError("MO2 paths changed or were not present in the accepted scan. Scan PC again.")
            if not ordinary(storage, True):
                raise ValueError("MO2 storage is unavailable or redirected.")
            game_key = _game_for(cfg.get("General", "gamePath", fallback=""), inventory)
            selected = cfg.get("General", "selected_profile", fallback="").removeprefix("@ByteArray(").removesuffix(")")
            for location in locations:
                location.game_key, location.manager_folder = game_key, str(ini.parent)
                game_claims.setdefault(location.key, set()).add(game_key)
            for path in children(storage):
                check()
                if ordinary(path, True):
                    child(storage_row, path)
            if profile_row is None or not ordinary(profiles, True):
                result.warnings.append("MO2 profiles are unavailable or changed since the accepted scan; activation was not inferred.")
                result.limited = True
                continue
            for folder in children(profiles, MAX_PROFILES):
                check()
                if len(result.profiles) >= MAX_PROFILES:
                    result.limited = True
                    break
                if not ordinary(folder, True):
                    continue
                source = folder / "modlist.txt"
                if not ordinary(source):
                    result.warnings.append("MO2 profile has no readable modlist.txt: " + folder.name)
                    continue
                items, issue = _read_modlist(source)
                profile = Profile("MO2:" + identity(source), folder.name, "Mod Organizer 2", str(source),
                                  game_key, folder.name == selected if selected else None, incomplete=bool(issue))
                info = source.stat()
                profile.source_mtime_ns, profile.source_size = info.st_mtime_ns, info.st_size
                if issue:
                    result.warnings.append(folder.name + ": " + issue)
                for item in items:
                    if item["marker"] == "*":
                        continue
                    node = child(storage_row, storage / item["name"], item["name"])
                    if node:
                        profile.members[node.key] = item["marker"]
                        node.profiles[profile.key] = item["marker"]
                result.profiles.append(profile)
        except (OSError, ValueError, TypeError) as exc:
            result.warnings.append("MO2 inspection incomplete: " + str(exc))
            result.limited = True
    vortex = [(raw, root) for raw, root in scanned if root.source == "Vortex" and "staging" in root.state.casefold()]
    for raw, root in vortex:
        check()
        storage = Path(root.path)
        manager = storage.parent.parent
        root.manager_folder = str(manager)
        try:
            if not ordinary(storage, True) or manager.name.casefold() != "vortex":
                raise ValueError("Vortex staging root is unavailable or not verified")
            for path in children(storage):
                if ordinary(path, True):
                    child(root, path)
            backups = [manager / "temp" / "state_backups_full" / name for name in ("manual.json", "startup.json", "hourly.json")]
            backups = [p for p in backups if ordinary(p) and p.stat().st_size <= MAX_SNAPSHOT]
            if not backups:
                raise ValueError("No readable Vortex JSON snapshot; live State.v2 was not opened.")
            source = max(backups, key=lambda p: p.stat().st_mtime)
            data = json.loads(text_file(source, MAX_SNAPSHOT))
            persistent = data.get("persistent", data)
            profiles, mods = persistent.get("profiles", {}), persistent.get("mods", {})
            settings = data.get("settings", {})
            game_id = storage.parent.name
            discovered = settings.get("gameMode", {}).get("discovered", {}).get(game_id, {})
            root.game_key = _game_for(discovered.get("path", ""), inventory)
            rows = mods.get(game_id, {})
            if len(rows) > MAX_CHILDREN or len(profiles) > MAX_PROFILES:
                result.limited = True
            nodes = {}
            for mod_id, record in islice(rows.items(), MAX_CHILDREN):
                check()
                if not isinstance(record, dict):
                    continue
                leaf = record.get("installationPath", mod_id)
                if not isinstance(leaf, str) or leaf in ("", ".", "..") or any(c in leaf for c in ("/", "\\", ":")):
                    continue
                node = child(root, storage / leaf)
                if node is None:
                    continue
                node.game_key, node.manager_folder = root.game_key, str(manager)
                attrs = record.get("attributes", {})
                if isinstance(attrs, dict):
                    node.name = plain(attrs.get("modName") or attrs.get("name"), 200) or node.name
                    node.version = plain(attrs.get("version"), 100) or node.version
                    node.author = plain(attrs.get("author"), 200) or node.author
                    node.description = plain(attrs.get("description")) or node.description
                node.identifiers.add(str(mod_id))
                nodes[str(mod_id)] = (node, record.get("rules", []))
            for profile_id, record in islice(profiles.items(), MAX_PROFILES):
                check()
                if not isinstance(record, dict) or record.get("gameId") != game_id:
                    continue
                if len(result.profiles) >= MAX_PROFILES:
                    result.limited = True
                    break
                states = record.get("modState", {})
                if not isinstance(states, dict):
                    raise ValueError("Invalid Vortex profile state")
                active = settings.get("profiles", {}).get("activeProfileId")
                profile = Profile("Vortex:" + identity(source) + ":" + str(profile_id), plain(record.get("name") or profile_id, 140),
                    "Vortex", str(source), root.game_key, str(active) == str(profile_id) if active is not None else None,
                    source.stat().st_mtime < time.time() - 7 * 86400)
                info = source.stat()
                profile.source_mtime_ns, profile.source_size = info.st_mtime_ns, info.st_size
                if any(str(key) not in nodes for key, state in states.items()
                       if isinstance(state, dict) and state.get("enabled") is True):
                    profile.incomplete = True
                    result.warnings.append(profile.name + ": enabled mod IDs are absent from this snapshot's mod records.")
                for mod_id, (node, rules) in nodes.items():
                    state_record = states.get(mod_id, {})
                    state = state_record.get("enabled") if isinstance(state_record, dict) else None
                    marker = "+" if state is True else "-" if state is False else "?"
                    profile.members[node.key] = marker
                    node.profiles[profile.key] = marker
                    if isinstance(rules, list):
                        for rule in rules[:100]:
                            if isinstance(rule, dict) and rule.get("type") in ("requires", "conflicts") and isinstance(rule.get("reference"), dict):
                                target = rule["reference"].get("id")
                                if isinstance(target, str):
                                    profile.rules.append({"owner": node.key, "target": nodes[target][0].key if target in nodes else target,
                                        "kind": rule["type"], "source": str(source)})
                result.profiles.append(profile)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            result.warnings.append("Vortex inspection incomplete: " + str(exc))
            result.limited = True
    for raw, root in scanned:
        check()
        if root.source in {"Mod Organizer 2", "Vortex"}:
            continue
        folder = Path(root.path)
        if not ordinary(folder, True):
            root.warnings.append("Location unavailable or redirected.")
            result.limited = True
            continue
        inspect_metadata(root)
        status = root.state.casefold()
        if root.source == "Steam game folder":
            allowed = {"/".join(parts).casefold() for parts in MOD_INDICATOR_DIRS}
            for indicator in getattr(raw, "indicators", ()):
                if not isinstance(indicator, str) or indicator.casefold() not in allowed:
                    continue
                target = folder
                for part in indicator.split("/"):
                    target = next((p for p in children(target) if p.name.casefold() == part.casefold() and ordinary(p, True)), None)
                    if target is None:
                        break
                if target is None:
                    continue
                if target.name.casefold() == "bepinex":
                    target = next((p for p in children(target) if p.name.casefold() == "plugins" and ordinary(p, True)), None)
                    if target is None:
                        continue
                for path in children(target):
                    if ordinary(path, True) or path.suffix.casefold() in {".jar", ".pak", ".dll", ".asi", ".esp", ".esl", ".esm", ".archive"} and ordinary(path):
                        child(root, path)
        elif root.source == "Steam Workshop" and "pending" not in status:
            for path in children(folder):
                check()
                if path.name.isdecimal() and ordinary(path, True):
                    node = child(root, path)
                    if node:
                        node.page = "https://steamcommunity.com/sharedfiles/filedetails/?id=" + path.name
        elif root.source not in {"Steam game folder", "Steam Workshop"} and not any(word in status for word in ("download", "cache", "profile", "save")):
            for path in children(folder):
                check()
                if ordinary(path, True):
                    child(root, path)
    for key, claims in game_claims.items():
        if len(claims) > 1:
            roots[key].game_key = ""
            roots[key].warnings.append("Multiple MO2 instance game paths claim this storage; ownership is unverified.")
    unique_profiles = {}
    for profile in result.profiles:
        prior = unique_profiles.get(profile.key)
        if prior and prior.game_key != profile.game_key:
            prior.game_key, prior.incomplete = "", True
        elif prior is None:
            unique_profiles[profile.key] = profile
    result.profiles = list(unique_profiles.values())
    for entry in entries.values():
        if entry.kind == "mod":
            root = roots.get(entry.root_key)
            if root:
                entry.game_key = root.game_key
            enabled = sum(v == "+" for v in entry.profiles.values())
            disabled = sum(v == "-" for v in entry.profiles.values())
            if entry.profiles:
                entry.state = f"{enabled} enabled / {disabled} disabled profile references"
    result.entries = list(entries.values())
    for entry in result.entries:
        if entry.warnings:
            result.limited = True
            result.warnings.extend(entry.name + ": " + warning for warning in entry.warnings)
    result.warnings = list(dict.fromkeys(result.warnings))[:100]
    result.limited = result.limited or any(p.incomplete for p in result.profiles) or len(entries) >= MAX_MODS
    return result
