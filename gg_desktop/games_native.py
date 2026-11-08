"""Games-only native launcher metadata and explicitly requested actions.

No shell command strings, folder deletion or automatic uninstall. Management
handoffs open the real client; uninstallers require a separate confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote, urlencode
from xml.etree import ElementTree

from core import _has_reparse_component, read_vdf
from gg_desktop.games_account_store import read_document
from gg_desktop.games_data import install_directory
from gg_desktop.games_sources import launcher_bucket
from gg_desktop.models import _path_key
from gg_desktop.games_providers import identifier

WINDOWS_NATIVE = os.name == "nt"

CLIENT_NAMES = {
    "EA": ("EADesktop.exe",), "Rockstar": ("Launcher.exe",),
    "Epic": ("EpicGamesLauncher.exe",), "GOG": ("GalaxyClient.exe",),
    "Ubisoft": ("UbisoftConnect.exe", "upc.exe", "Uplay.exe"),
    "Battle.net": ("Battle.net.exe", "Battle.net Launcher.exe"),
    "Other": ("RiotClientServices.exe",),
}
CLIENT_FOLDERS = {
    "EA": ("Electronic Arts/EA Desktop/EA Desktop/EADesktop.exe",),
    "Rockstar": ("Rockstar Games/Launcher/Launcher.exe",),
    "Epic": ("Epic Games/Launcher/Portal/Binaries/Win32/EpicGamesLauncher.exe", "Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"),
    "GOG": ("GOG Galaxy/GalaxyClient.exe",),
    "Ubisoft": ("Ubisoft/Ubisoft Game Launcher/UbisoftConnect.exe", "Ubisoft/Ubisoft Game Launcher/upc.exe"),
    "Battle.net": ("Battle.net/Battle.net.exe", "Battle.net/Battle.net Launcher.exe"),
    "Other": ("Riot Games/Riot Client/RiotClientServices.exe",),
}
ROCKSTAR = {
    "grand theft auto v": ("gta5", "PlayGTAV.exe"),
    "grand theft auto v legacy": ("gta5", "PlayGTAV.exe"),
    "grand theft auto v enhanced": ("gta5_gen9", "GTA5_Enhanced_BE.exe"),
    "red dead redemption": ("rdr", "RDR.exe"), "red dead redemption 2": ("rdr2", "RDR2.exe"),
    "l.a. noire": ("lanoire", "LANoire.exe"), "max payne 3": ("mp3", "MaxPayne3.exe"),
    "grand theft auto iv": ("gta4", "GTAIV.exe"),
    "bully: scholarship edition": ("bully", "Bully.exe"),
}


def executable(path):
    path = Path(path)
    if not path.is_absolute() or path.suffix.casefold() != ".exe" or _has_reparse_component(path) or not path.is_file():
        raise ValueError("The selected executable is missing or redirected.")
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("The selected file is not a Windows executable.")
    return str(path)


def client_path(provider, *, environment=None, registry=None):
    env = os.environ if environment is None else environment
    custom = read_document("options.json", {}).get("launcher_paths", {}).get(provider)
    candidates = [custom] if isinstance(custom, str) else []
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "ProgramW6432"):
        value = env.get(variable)
        if value:
            candidates.extend(str(Path(value)/part) for part in CLIENT_FOLDERS.get(provider, ()))
    if registry is None:
        try:
            import winreg as registry
        except ImportError:
            registry = None
    if registry:
        for hive in (registry.HKEY_LOCAL_MACHINE, registry.HKEY_CURRENT_USER):
            for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
                for name in CLIENT_NAMES.get(provider, ()):
                    try:
                        with registry.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + name, 0, registry.KEY_READ | view) as key:
                            value = registry.QueryValueEx(key, "")[0]
                            if isinstance(value, str):
                                candidates.append(value.strip('"'))
                    except OSError:
                        pass
                if provider == "Rockstar":
                    try:
                        with registry.OpenKey(hive, r"SOFTWARE\Rockstar Games\Launcher", 0, registry.KEY_READ | view) as key:
                            candidates.append(str(Path(registry.QueryValueEx(key, "InstallFolder")[0])/"Launcher.exe"))
                    except (OSError, TypeError):
                        pass
    for candidate in dict.fromkeys(candidates):
        try:
            if Path(candidate).name.casefold() in {name.casefold() for name in CLIENT_NAMES.get(provider, ())}:
                return executable(candidate)
        except (OSError, ValueError):
            pass
    return ""


def _xml(path):
    try:
        if _has_reparse_component(path) or not path.is_file() or path.stat().st_size > 2 * 1024**2:
            return None
        raw = path.read_bytes()
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            return None
        root = ElementTree.fromstring(raw)
        return root if sum(1 for _ in root.iter()) <= 20000 else None
    except (OSError, ValueError, ElementTree.ParseError):
        return None


def epic_installations():
    import json
    from itertools import islice
    from launchers import _ordinary_install
    base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))/"Epic/EpicGamesLauncher/Data/Manifests"
    output = {}
    if _has_reparse_component(base):
        return output
    for path in islice(base.glob("*.item"), 3000):
        try:
            if _has_reparse_component(path) or path.stat().st_size > 2*1024**2:
                continue
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                continue
            install = _ordinary_install(data.get("InstallLocation"))
            if install is not None and identifier(data.get("AppName")):
                key = _path_key(str(install))
                output[key] = data if key not in output else None
        except (OSError, ValueError, TypeError):
            continue
    return output


def installed_facts(game, steam_roots=(), *, epic_records=None):
    provider = launcher_bucket(game.launcher)
    facts = dict(provider=provider, product_id="", source="Local installation record")
    if " / " in game.launcher or len(game.claimed_by) != 1:
        return facts
    if provider == "Steam" and re.fullmatch(r"[1-9][0-9]{0,9}", str(game.app_id or "")):
        facts["product_id"] = game.app_id
        for root in steam_roots:
            manifest = Path(root)/"steamapps"/("appmanifest_"+game.app_id+".acf")
            state = read_vdf(manifest).get("appstate", {})
            if not isinstance(state, dict):
                continue
            try:
                if str(state.get("appid")) != game.app_id or str(state.get("installdir")) != Path(game.install_path).name:
                    continue
                flags = int(state.get("stateflags", 0))
                current, target = str(state.get("buildid", "")), str(state.get("targetbuildid", ""))
                needed = bool(flags & 2 or target and current and target != current)
                facts.update(installed_version=current, update_available=needed,
                    update_label="Update available" if needed else "No update reported", update_source="Steam client manifest",
                    update_checked_at=manifest.stat().st_mtime, source="Steam client manifest")
                break
            except (OSError, ValueError, TypeError):
                continue
    elif provider == "EA":
        root = _xml(Path(game.install_path)/"__Installer/installerdata.xml")
        if root is not None:
            ids = []
            for node in root.iter():
                tag = str(node.tag).rsplit("}", 1)[-1].casefold()
                if tag in ("contentid", "contentids", "offerid", "gameid"):
                    ids.extend(identifier(part.strip()) for part in (node.text or "").split(","))
                for name, value in node.attrib.items():
                    if name.casefold() in ("contentid", "offerid", "gameid"):
                        ids.append(identifier(value))
            facts["aliases"] = [value for value in dict.fromkeys(ids) if value][:30]
            facts["product_id"] = next(iter(facts["aliases"]), "")
        if not facts["product_id"] and re.fullmatch(r"(?:OFB-EAST:|Origin\.)[A-Za-z0-9_.:-]{1,160}", str(game.app_id or "")):
            facts["product_id"] = game.app_id
    elif provider == "GOG":
        if re.fullmatch(r"[1-9][0-9]{0,19}", str(game.app_id or "")):
            facts["product_id"] = game.app_id
        else:
            from gg_desktop.game_artwork import MAX_METADATA
            import json
            for path in list(Path(game.install_path).glob("goggame-*.info"))[:12]:
                try:
                    if _has_reparse_component(path) or path.stat().st_size > MAX_METADATA:
                        continue
                    body = json.loads(path.read_text(encoding="utf-8-sig"))
                    ident = str(body.get("gameId", ""))
                    if re.fullmatch(r"[1-9][0-9]{0,19}", ident):
                        facts["product_id"] = ident
                        break
                except (OSError, ValueError, TypeError):
                    continue
    elif provider == "Ubisoft" and re.fullmatch(r"[1-9][0-9]{0,11}", str(game.app_id or "")):
        facts["product_id"] = game.app_id
    elif provider == "Rockstar":
        product = ROCKSTAR.get(game.name.casefold())
        if product and (Path(game.install_path)/product[1]).is_file() and not _has_reparse_component(Path(game.install_path)/product[1]):
            facts["product_id"] = product[0]
    elif provider == "Epic":
        data = (epic_records if epic_records is not None else epic_installations()).get(_path_key(game.install_path))
        if isinstance(data, dict) and identifier(data.get("AppName")) == str(game.app_id):
            facts.update(product_id=identifier(data.get("AppName")), namespace=identifier(data.get("CatalogNamespace")),
                catalog_id=identifier(data.get("CatalogItemId")), installed_version=str(data.get("AppVersionString", ""))[:300],
                source="Epic installation manifest")
        if not facts["product_id"]:
            facts["product_id"] = identifier(game.app_id)
    return facts


@dataclass(frozen=True)
class Action:
    label: str
    uri: str = ""
    argv: tuple = ()
    handoff: bool = False
    confirmation: bool = False


def _numeric(value):
    return bool(re.fullmatch(r"[1-9][0-9]{0,19}", str(value or "")))


def native_action(game, facts, action, *, client_finder=None, uninstaller=None):
    client_finder = client_finder or client_path
    provider = launcher_bucket(game.launcher)
    product = identifier(game.app_id if provider == "Steam" else facts.get("product_id"))
    if " / " in game.launcher or len(game.claimed_by) != 1:
        raise ValueError("More than one launcher claims this installation. Choose a game EXE for Play; manage it in its confirmed owner.")
    if action not in ("launch", "install", "validate", "details", "uninstall"):
        raise ValueError("Unsupported game action.")
    if action != "install" and action != "details":
        install_directory(game)
    if action == "uninstall" and uninstaller:
        return Action("Open registered game uninstaller", argv=tuple(uninstaller), confirmation=True)
    if provider == "Steam" and _numeric(product):
        prefixes = {"launch": "rungameid", "install": "install", "validate": "validate", "details": "nav/games/details", "uninstall": "uninstall"}
        return Action("Open Steam controls", uri=f"steam://{prefixes[action]}/{product}", confirmation=action == "uninstall")
    if provider == "Epic":
        if action in ("launch", "install") and product:
            namespace, catalog = identifier(facts.get("namespace")), identifier(facts.get("catalog_id"))
            identity = ":".join((namespace, catalog, product)) if action == "launch" and namespace and catalog else product
            return Action("Launch with Epic" if action == "launch" else "Install with Epic",
                uri="com.epicgames.launcher://apps/" + quote(identity, safe="") + "?" + urlencode(dict(action=action, silent="true")))
        return Action("Open Epic library management", uri="com.epicgames.launcher://store/library", handoff=True)
    if provider == "Ubisoft" and _numeric(product) and action in ("launch", "install", "uninstall"):
        return Action("Open Ubisoft game controls", uri=f"uplay://{action}/{product}", confirmation=action == "uninstall")
    if provider == "GOG" and _numeric(product):
        if action == "uninstall":
            target = Path(game.install_path)/"unins000.exe"
            if target.is_file():
                return Action("Open this game's GOG uninstaller", argv=(executable(target),), confirmation=True)
        elif action == "launch":
            client = client_finder("GOG")
            if client:
                return Action("Launch with GOG Galaxy", argv=(client, "/command=runGame", "/gameId="+product, "/path="+game.install_path))
        else:
            return Action("Open this game in GOG Galaxy", uri="goggalaxy://openGameView/"+product, handoff=action in ("validate", "details"))
    if provider == "EA" and product and action in ("launch", "install"):
        return Action("Open this game in EA", uri="origin2://game/launch?"+urlencode(dict(offerIds=product, autoDownload="1" if action == "install" else "0")))
    if provider == "Rockstar":
        client = client_finder(provider)
        if client:
            if action == "launch":
                return Action("Launch with Rockstar", argv=(client, "-launchTitleInFolder", game.install_path))
            if action == "uninstall" and product in {value[0] for value in ROCKSTAR.values()}:
                return Action("Open Rockstar uninstall", argv=(client, "-enableFullMode", "-uninstall="+product), confirmation=True)
            return Action("Open Rockstar game management", argv=(client, "-enableFullMode"), handoff=True)
    client = client_finder(provider)
    if client and action in ("validate", "details", "uninstall"):
        return Action("Open " + game.launcher + " game management", argv=(client,), handoff=True)
    if provider == "Xbox (PC)":
        return Action("Open Windows installed-game management", uri="ms-settings:appsfeatures", handoff=True)
    if action == "uninstall":
        return Action("Open Windows installed-game management", uri="ms-settings:appsfeatures", handoff=True)
    raise ValueError("This launcher's client could not be found. Choose its EXE in Library connections, or choose this game's EXE for Play.")


def split_command(command):
    """Parse a Windows executable command without ever invoking a shell."""
    if not isinstance(command, str) or len(command) > 12000 or any(c in command for c in "\r\n\0"):
        return []
    # The executable must be explicitly quoted if its path contains spaces.
    match = re.fullmatch(r'\s*(?:"([^"]+)"|([^\s"]+))(.*)', command)
    if not match:
        return []
    first, remainder = match.group(1) or match.group(2), match.group(3)
    if not first.casefold().endswith(".exe"):
        return []
    arguments = re.findall(r'"(?:[^"\\]|\\.)*"|[^\s"]+', remainder)
    if " ".join(arguments).replace(" ", "") != remainder.replace(" ", ""):
        return []
    return [first] + [argument[1:-1] if argument.startswith('"') else argument for argument in arguments]


def registered_uninstaller(game, *, registry=None):
    if registry is None:
        try:
            import winreg as registry
        except ImportError:
            return None
    expected = _path_key(game.install_path)
    found = set()
    for hive in (registry.HKEY_LOCAL_MACHINE, registry.HKEY_CURRENT_USER):
        for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
            try:
                parent = registry.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0, registry.KEY_READ | view)
            except OSError:
                continue
            with parent:
                for index in range(3000):
                    try:
                        name = registry.EnumKey(parent, index)
                    except OSError:
                        break
                    try:
                        with registry.OpenKey(parent, name) as key:
                            display = registry.QueryValueEx(key, "DisplayName")[0]
                            normalize = lambda value: "".join(char for char in str(value).casefold() if char.isalnum())
                            if normalize(display) != normalize(game.name):
                                continue
                            try:
                                install = registry.QueryValueEx(key, "InstallLocation")[0]
                            except OSError:
                                install = ""
                            same_root = isinstance(install, str) and bool(install.strip()) and _path_key(install.strip('"')) == expected
                            if install and not same_root:
                                continue
                            command = registry.QueryValueEx(key, "UninstallString")[0]
                            argv = split_command(command)
                            if not argv:
                                continue
                            if Path(argv[0]).name.casefold() == "msiexec.exe":
                                remainder = " ".join(argv[1:])
                                product = re.fullmatch(r"/[ixIX]\s*(\{[0-9a-fA-F-]{36}\})", remainder)
                                if not same_root or product is None or product[1].casefold() != name.casefold():
                                    continue
                                windows = os.environ.get("SystemRoot", "C:/Windows")
                                program = executable(Path(windows)/"System32/msiexec.exe")
                                found.add((program, "/x", product[1]))
                                continue
                            program = Path(executable(argv[0]))
                            if program.name.casefold() in {"cmd.exe", "powershell.exe", "pwsh.exe", "rundll32.exe", "mshta.exe", "wscript.exe", "cscript.exe", "python.exe", "regsvr32.exe"}:
                                continue
                            # Only this installation's own uninstaller, or
                            # Blizzard's specifically registered uninstaller.
                            inside = _path_key(str(program.parent)).startswith(expected + "\\") or _path_key(str(program.parent)) == expected
                            blizzard = launcher_bucket(game.launcher) == "Battle.net" and program.name.casefold() == "blizzard uninstaller.exe"
                            if inside or blizzard and same_root:
                                found.add(tuple([str(program)] + argv[1:]))
                    except (OSError, ValueError, TypeError):
                        continue
    return next(iter(found)) if len(found) == 1 else None


def execute(action, open_url, *, spawn=None):
    spawn = spawn or subprocess.Popen
    if action.uri:
        if not open_url(action.uri):
            raise ValueError("Windows could not open the launcher. Check that its client is installed.")
    elif action.argv:
        program = executable(action.argv[0])
        if not WINDOWS_NATIVE:
            raise ValueError("Native launcher executables run in the Windows application.")
        spawn([program, *action.argv[1:]], cwd=str(Path(program).parent), shell=False)
    else:
        raise ValueError("No native action is available.")
