"""Optional read-only game mod storage integrations for Game Grave.

Never edits Steam, Nexus/Vortex or MO2 metadata; never uninstalls, unlinks, or
moves files. These are storage *findings*, not delete recommendations.
"""
from __future__ import annotations

import configparser
import os
import re
from pathlib import Path
from typing import Callable

from core import (ModFolder, SteamGame, _is_reparse_point, _measured_files,
                  _steam_roots, read_vdf, steam_libraries)


Cancel = Callable[[], bool] | None
MAX_FILES_PER_FINDING = 75_000
MAX_FINDINGS = 750


def _safe_folder(p: Path) -> bool:
    """Never inventory a disk root, system directory, symlink, or junction."""
    try:
        if _is_reparse_point(p) or not p.is_dir():
            return False
        resolved = p.resolve()
        return (resolved != Path(resolved.anchor) and resolved != Path.home().resolve()
                and resolved.name.casefold() not in {"windows", "system32", "$recycle.bin"})
    except OSError:
        return False


def _children(folder: Path) -> list[Path]:
    try:
        return sorted((p for p in folder.iterdir() if _safe_folder(p)), key=lambda p: p.name.casefold())
    except OSError:
        return []


def _measure(name: str, folder: Path, source: str, status: str,
             advice: str, indicators: tuple[str, ...] = (), item_count: int = 0,
             cancel: Cancel = None) -> ModFolder | None:
    if not _safe_folder(folder):
        return None
    size, files, truncated = _measured_files([folder], max_files=MAX_FILES_PER_FINDING, cancel=cancel)
    return ModFolder(name=name, path=str(folder), library=str(folder.parent), status=status,
                     indicators=indicators, apparent_bytes=size, file_count=files,
                     truncated=truncated, source=source, advice=advice, item_count=item_count)


def _workshop(extra_steam_roots: list[str] | None,
              games: list[SteamGame], cancel: Cancel) -> list[ModFolder]:
    installed = {game.app_id: game.name for game in games}
    result: list[ModFolder] = []
    for library in steam_libraries(_steam_roots(extra_steam_roots)):
        workshop = library / 'steamapps' / 'workshop'
        content = workshop / 'content'
        if _safe_folder(content):
            for game_dir in _children(content):
                if cancel and cancel():
                    raise InterruptedError('Mod scan canceled')
                if not game_dir.name.isdecimal():
                    continue
                app_id = game_dir.name
                workshop_record = read_vdf(workshop / f'appworkshop_{app_id}.acf').get('appworkshop', {})
                installed_record = (workshop_record.get('workshopitemsinstalled', {})
                                    if isinstance(workshop_record, dict) else {})
                recorded = {str(k) for k in installed_record} if isinstance(installed_record, dict) else set()
                item_dirs = [p for p in _children(game_dir) if p.name.isdecimal()]
                unrecorded = sum(p.name not in recorded for p in item_dirs)
                title = installed.get(app_id, f'Steam app {app_id}')
                status = ('Workshop: associated game installed' if app_id in installed else
                          'Workshop: no installed-game record')
                caution = ('Workshop subscriptions and app state can persist even when a game is not installed. '
                           'Do not delete content directly: Steam may redownload it. '
                           'Use Steam Workshop subscription management first.')
                if unrecorded:
                    caution += f' {unrecorded} item folder(s) are absent from this local installed-item manifest; this does not prove orphan status.'
                measured = _measure(title, game_dir, 'Steam Workshop', status, caution,
                                    indicators=(f'App ID {app_id}', f'{len(item_dirs)} item folders',
                                                f'{unrecorded} not in local manifest'),
                                    item_count=len(item_dirs), cancel=cancel)
                if measured:
                    result.append(measured)
                if len(result) >= MAX_FINDINGS:
                    return result
        # Partially downloaded Workshop data is NOT unused, even if it looks stale.
        downloads = workshop / 'downloads'
        if _safe_folder(downloads):
            for app_dir in _children(downloads):
                if cancel and cancel():
                    raise InterruptedError('Mod scan canceled')
                if not app_dir.name.isdecimal():
                    continue
                measured = _measure(installed.get(app_dir.name, f'Steam app {app_dir.name}'),
                                    app_dir, 'Steam Workshop', 'Workshop: pending/download cache',
                                    'May contain an active or interrupted Steam download. Do not remove while Steam is downloading or updating.',
                                    indicators=(f'App ID {app_dir.name}',), cancel=cancel)
                if measured:
                    result.append(measured)
                if len(result) >= MAX_FINDINGS:
                    return result
    return result


def _vortex(vortex_dir: Path, cancel: Cancel) -> list[ModFolder]:
    rows: list[ModFolder] = []
    if not _safe_folder(vortex_dir):
        return rows
    for child in _children(vortex_dir):
        if cancel and cancel():
            raise InterruptedError('Mod scan canceled')
        if child.name.casefold() == 'downloads':
            for game_downloads in _children(child):
                row = _measure(game_downloads.name, game_downloads, 'Vortex', 'Vortex: downloaded archives',
                               'Archives may be needed for reinstalling mods. Verify in Vortex before removing anything.',
                               indicators=('Download archive storage',), cancel=cancel)
                if row:
                    rows.append(row)
        else:
            staging = child / 'mods'
            if _safe_folder(staging):
                mods = _children(staging)
                row = _measure(child.name, staging, 'Vortex', 'Vortex: mod staging',
                               'Managed staging folder. Vortex can deploy hardlinks into game directories; apparent sizes may double count storage. Never remove through Game Grave.',
                               indicators=(f'{len(mods)} mod folders', 'Managed deployment'),
                               item_count=len(mods), cancel=cancel)
                if row:
                    rows.append(row)
        if len(rows) >= MAX_FINDINGS:
            return rows
    return rows


def _read_ini(path: Path) -> configparser.RawConfigParser | None:
    try:
        if path.stat().st_size > 5_000_000:
            return None
        ini = configparser.RawConfigParser(interpolation=None, strict=False)
        # Qt/Windows INI files may contain non-UTF-8 characters in mod paths.
        try:
            contents = path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            contents = path.read_text(encoding='cp1252', errors='replace')
        ini.read_string(contents)
        return ini
    except (OSError, configparser.Error, UnicodeError):
        return None


def _resolve_mo_path(raw: str, base: Path, ini_dir: Path) -> Path:
    raw = re.sub(r'%BASE_DIR%', str(base), raw.strip().strip('"'), flags=re.I)
    raw = os.path.expandvars(os.path.expanduser(raw))
    # Linux support makes synthetic Windows-style INI fixtures testable.
    if os.name != 'nt':
        raw = raw.replace('\\', '/')
    value = Path(raw)
    if not value.is_absolute():
        value = ini_dir / value
    return value


def _mo2_instance(ini_path: Path, cancel: Cancel) -> list[ModFolder]:
    config = _read_ini(ini_path)
    if config is None or not config.has_section('Settings'):
        return []
    defaults = { 'mod_directory': 'mods', 'download_directory': 'downloads',
                 'profiles_directory': 'profiles', 'overwrite_directory': 'overwrite' }
    settings = config['Settings']
    ini_dir = ini_path.parent
    base_raw = settings.get('base_directory', str(ini_dir))
    base = _resolve_mo_path(base_raw, ini_dir, ini_dir)
    game = ini_dir.name
    rows: list[ModFolder] = []
    for setting, default in defaults.items():
        raw = settings.get(setting, '%BASE_DIR%/' + default)
        location = _resolve_mo_path(raw, base, ini_dir)
        if cancel and cancel():
            raise InterruptedError('Mod scan canceled')
        if not _safe_folder(location):
            continue
        category = {'mod_directory': 'MO2: installed mods',
                    'download_directory': 'MO2: downloads',
                    'profiles_directory': 'MO2: profiles / saves protected',
                    'overwrite_directory': 'MO2: overwrite protected'}[setting]
        if setting in ('profiles_directory', 'overwrite_directory'):
            note = 'Protected MO2 data may contain load orders, configurations, generated outputs and saves. Do not clean this automatically.'
        else:
            note = 'Managed MO2 instance data; game folders can be elsewhere or uninstalled. Check MO2 instances/profiles before any removal.'
        items = _children(location) if setting == 'mod_directory' else []
        row = _measure(f'{game} · {location.name}', location, 'Mod Organizer 2',
                       category, note, indicators=(f'Instance {game}', setting),
                       item_count=len(items), cancel=cancel)
        if row:
            rows.append(row)
    return rows


def _mo2(root: Path, cancel: Cancel) -> list[ModFolder]:
    if not _safe_folder(root):
        return []
    ini_files = []
    for path in [root / 'ModOrganizer.ini', root / 'modorganizer.ini']:
        if path.is_file() and not _is_reparse_point(path):
            ini_files.append(path)
            break
    for child in _children(root):
        for candidate in [child / 'ModOrganizer.ini', child / 'modorganizer.ini']:
            if candidate.is_file() and not _is_reparse_point(candidate):
                ini_files.append(candidate)
                break
    rows = []
    for ini in ini_files:
        rows.extend(_mo2_instance(ini, cancel))
        if len(rows) >= MAX_FINDINGS:
            break
    return rows


def _classify_extra(folder: Path, cancel: Cancel) -> list[ModFolder]:
    """Explicitly added paths can include portable MO2, Vortex, or arbitrary mod archives."""
    if not _safe_folder(folder):
        return []
    name = folder.name.casefold()
    if any((folder / ini).is_file() for ini in ('ModOrganizer.ini', 'modorganizer.ini')):
        return _mo2(folder, cancel)
    if name == 'modorganizer':
        return _mo2(folder, cancel)
    if name == 'vortex' or (folder / 'downloads').is_dir() and any((c / 'mods').is_dir() for c in _children(folder)):
        return _vortex(folder, cancel)
    row = _measure(folder.name, folder, 'Custom mod storage', 'Custom folder: review only',
                   'User-added storage folder. Game Grave does not assume it is unused or safe to delete.',
                   indicators=('Manually added location',), cancel=cancel)
    return [row] if row else []


def find_external_mod_storage(extra_steam_roots: list[str] | None,
                              extra_mod_roots: list[str],
                              games: list[SteamGame],
                              cancel: Cancel = None) -> list[ModFolder]:
    """Inventory locally discoverable Workshop/Vortex/MO2 storage, and added roots.

    No claim of detecting all installations. User-added paths cover moved libraries,
    portable MO2 and custom staging/download directories.
    """
    results = _workshop(extra_steam_roots, games, cancel)
    standard = []
    appdata = os.environ.get('APPDATA')
    programdata = os.environ.get('PROGRAMDATA')
    localdata = os.environ.get('LOCALAPPDATA')
    if appdata:
        standard.append(('vortex', Path(appdata) / 'Vortex'))
    if programdata:
        standard.append(('vortex', Path(programdata) / 'Vortex'))
    if localdata:
        standard.append(('mo2', Path(localdata) / 'ModOrganizer'))
    known = set()
    for kind, root in standard:
        key = str(root).casefold()
        if key in known:
            continue
        known.add(key)
        results.extend(_vortex(root, cancel) if kind == 'vortex' else _mo2(root, cancel))
    for raw in extra_mod_roots[:30]:
        if not isinstance(raw, str) or not raw.strip():
            continue
        root = Path(raw).expanduser()
        key = str(root).casefold()
        if key in known:
            continue
        known.add(key)
        results.extend(_classify_extra(root, cancel))
        if len(results) >= MAX_FINDINGS:
            break
    unique = {}
    for row in results:
        unique[(str(Path(row.path)).casefold(), row.source)] = row
    return list(unique.values())[:MAX_FINDINGS]
