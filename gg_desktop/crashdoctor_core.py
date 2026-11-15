"""Qt-free Crash Doctor: Mod Bisect that runs the tests for you.

Each test: switch exactly the mods the Bisect engine asks for on (everything else off), launch the game, and judge it:
it crashed if the game stopped before the "runs fine" time or Windows recorded a crash for a program in the game's
folder; it ran fine if it was still running after that time (then Game Grave closes it); not sure if it never started.

Three ways to switch mods, so no single mod manager is required:
- Mod Organizer 2: the approved Bisect copy profile ("GG Bisect - <profile>"); the game starts through MO2 with it.
- Vortex: Vortex's own deployment list (vortex.deployment*.json in the game folder) says which deployed files belong to
  which mod; a test moves the files of switched-off mods into a holding folder and puts them back afterwards.
- Folder (no manager): every file or folder inside the folder you pick is one mod; switched-off ones are moved into a
  holding folder and put back afterwards.
Vortex and Folder write a manifest first and only move; nothing is deleted or overwritten. Everything goes back when the
search ends, when you press Stop, or the next time Game Grave starts if it was closed in the middle.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from gg_desktop.bisect_core import Unit

HOLD_NAME = "_GameGrave_Crash_Doctor_Off"
MANIFEST = "crash-doctor.json"
LOADERS = ("skse64_loader.exe", "skse_loader.exe", "f4se_loader.exe", "sfse_loader.exe", "nvse_loader.exe",
           "fose_loader.exe", "obse_loader.exe", "obse64_loader.exe")
NOT_GAME = re.compile(r"(unins|setup|install|launcher|crash|report|redist|vc_|dxsetup|loader|helper|easyanticheat|"
                      r"be_service|battleye|updater|config|editor|creationkit)", re.I)
START_WAIT = 120          # seconds for the game to appear
FINE_CHOICES = (60, 120, 300)
MAX_RUNS = 40             # launches per search at most


class DoctorError(RuntimeError):
    pass


# ------------------------------------------------------------------ verdict for one launch
@dataclass
class Observation:
    started: bool
    ran_for: float            # seconds the game ran (until it stopped, or until judged fine)
    still_running: bool       # running when the fine time was reached
    crash_recorded: bool = False


def judge(obs: Observation, fine_after: float) -> str:
    """'crash', 'ok' or 'unsure' for one launch."""
    if obs.crash_recorded and obs.started:
        return "crash"
    if not obs.started:
        return "unsure"
    if obs.still_running or obs.ran_for >= fine_after:
        return "ok"
    return "crash"


def explain(result: str, obs: Observation, fine_after: float) -> str:
    if result == "unsure":
        return "The game didn't start within two minutes, so this test counts as not sure."
    if result == "crash":
        why = "Windows recorded a crash" if obs.crash_recorded else f"it closed after {obs.ran_for:.0f} seconds"
        return f"Crashed: {why}."
    return f"Ran fine for {fine_after / 60:.0f} minute{'s' if fine_after >= 120 else ''}, then Game Grave closed it."


# ------------------------------------------------------------------ launching
def game_programs(install_path, listdir=os.listdir, size=os.path.getsize):
    """Programs in the game folder that are probably the game (biggest first), loaders listed separately."""
    folder = Path(install_path)
    try:
        names = [n for n in listdir(folder) if n.casefold().endswith(".exe")]
    except OSError:
        return [], []
    loaders = [n for n in names if n.casefold() in LOADERS]
    games = [n for n in names if not NOT_GAME.search(n)]
    games.sort(key=lambda n: -(size(folder / n) if (folder / n).exists() else 0))
    return games, loaders


def launch_choices(game):
    """[(words, command or steam link)] best first: the script extender's loader, the game itself, then Steam."""
    out = []
    path = getattr(game, "install_path", "")
    games, loaders = game_programs(path) if path else ([], [])
    for loader in loaders:
        out.append((f"{loader} (script extender)", [str(Path(path) / loader)]))
    for exe in games[:3]:
        out.append((exe, [str(Path(path) / exe)]))
    if getattr(game, "launcher", "") == "Steam" and str(getattr(game, "app_id", "")).isdigit():
        out.append(("Through Steam", "steam://rungameid/" + str(game.app_id)))
    return out


def mo2_launch(mo2_exe, profile_name, executable_title):
    return [str(mo2_exe), "-p", profile_name, "moshortcut://:" + executable_title]


def mo2_executables(ini_text):
    """[(title, binary)] from Mod Organizer 2's settings ([customExecutables])."""
    found = {}
    section = False
    for line in ini_text.splitlines():
        s = line.strip()
        if s.startswith("["):
            section = s.casefold() == "[customexecutables]"
            continue
        m = re.match(r"(\d+)\\(title|binary)=(.*)", s) if section else None
        if m:
            found.setdefault(int(m.group(1)), {})[m.group(2)] = m.group(3).strip()
    items = [(v.get("title", ""), v.get("binary", "")) for _, v in sorted(found.items()) if v.get("title")]
    items.sort(key=lambda t: (0 if Path(t[1].replace("\\", "/")).name.casefold() in LOADERS else 1))
    return items


# ------------------------------------------------------------------ switchers
class Switcher:
    method = ""

    def units(self) -> list:
        raise NotImplementedError

    def apply(self, on_keys) -> None:
        raise NotImplementedError

    def restore(self) -> list:
        """Put everything back. Returns names that could not be put back (left in the holding folder)."""
        return []


def _unit(key, name, path=None):
    added = None
    if path is not None:
        try:
            added = os.stat(path).st_ctime
        except OSError:
            added = None
    kind = "code" if str(name).casefold().endswith((".dll", ".esp", ".esm", ".esl", ".pex", ".lua", ".asi")) else "unknown"
    return Unit(key, name, added, kind)


class _Holding:
    """A holding folder next to the mods with a manifest of exactly what was moved. Only moves; never overwrites."""

    def __init__(self, root: Path, name: str = HOLD_NAME):
        self.root = Path(root)
        self.hold = self.root / name
        self.manifest = self.hold / MANIFEST

    def moved(self) -> list:
        try:
            return list(json.loads(self.manifest.read_text(encoding="utf-8")).get("moved", []))
        except (OSError, ValueError):
            return []

    def _write(self, moved):
        self.hold.mkdir(exist_ok=True)
        temp = self.manifest.with_suffix(".tmp")
        temp.write_text(json.dumps({"version": 1, "root": str(self.root), "moved": moved, "when": time.time()}),
                        encoding="utf-8")
        temp.replace(self.manifest)

    def move_out(self, rel):
        src, dst = self.root / rel, self.hold / rel
        if not src.exists() or dst.exists():
            return False
        moved = self.moved()
        if rel not in moved:
            self._write(moved + [rel])       # recorded before it moves, so a crash mid-way can always be undone
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return True

    def move_back(self, rel):
        src, dst = self.hold / rel, self.root / rel
        if not src.exists():
            self._write([r for r in self.moved() if r != rel])
            return True
        if dst.exists():
            return False                       # something new is there: never overwrite it
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        self._write([r for r in self.moved() if r != rel])
        return True

    def restore(self):
        left = [rel for rel in list(self.moved()) if not self.move_back(rel)]
        if not left:
            try:
                self.manifest.unlink(missing_ok=True)
                for sub in sorted(self.hold.rglob("*"), key=lambda p: -len(p.parts)):
                    if sub.is_dir():
                        sub.rmdir()
                self.hold.rmdir()
            except OSError:
                pass
        return left


class FolderSwitcher(Switcher):
    """No mod manager: each file or folder inside `folder` is one mod."""
    method = "Folder"

    def __init__(self, folder):
        self.folder = Path(folder)
        self.holding = _Holding(self.folder)

    def units(self):
        names = set()
        try:
            names = {p.name for p in self.folder.iterdir() if not p.name.startswith((".", "_GameGrave_"))}
        except OSError as exc:
            raise DoctorError("The mod folder can't be read: " + str(exc))
        names |= {Path(rel).parts[0] for rel in self.holding.moved()}
        return [_unit(n, n, self.folder / n if (self.folder / n).exists() else self.holding.hold / n) for n in sorted(
            names, key=str.casefold)]

    def apply(self, on_keys):
        on = set(on_keys)
        for unit in self.units():
            if unit.key in on:
                self.holding.move_back(unit.key)
            else:
                self.holding.move_out(unit.key)

    def restore(self):
        return self.holding.restore()


def vortex_manifests(game_folder):
    """vortex.deployment*.json files Vortex keeps in the game folder and in its Data folder."""
    roots = [Path(game_folder), Path(game_folder) / "Data"]
    found = []
    for root in roots:
        try:
            found += [p for p in root.iterdir() if p.name.casefold().startswith("vortex.deployment") and p.suffix == ".json"]
        except OSError:
            continue
    return found


def vortex_files(manifest_paths):
    """{mod name: [(target root, relative path)]} from Vortex's deployment lists."""
    mods = {}
    for path in manifest_paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        target = Path(data.get("targetPath") or Path(path).parent)
        for item in data.get("files", []) or []:
            rel, source = item.get("relPath"), item.get("source")
            if isinstance(rel, str) and isinstance(source, str) and rel and source and ".." not in Path(rel).parts:
                mods.setdefault(source, []).append((str(target), rel))
    return mods


class VortexSwitcher(Switcher):
    """Vortex: moves a mod's deployed files aside using Vortex's own deployment list, and back afterwards."""
    method = "Vortex"

    def __init__(self, game_folder):
        self.game_folder = Path(game_folder)
        manifests = vortex_manifests(game_folder)
        if not manifests:
            raise DoctorError("Vortex's deployment list wasn't found in the game folder. Deploy your mods in Vortex once, "
                              "or use the Folder method.")
        self.mods = vortex_files(manifests)
        self.holdings = {}

    def _holding(self, root):
        if root not in self.holdings:
            self.holdings[root] = _Holding(Path(root))
        return self.holdings[root]

    def units(self):
        return [_unit(name, name) for name in sorted(self.mods, key=str.casefold)]

    def apply(self, on_keys):
        on = set(on_keys)
        for name, files in self.mods.items():
            for root, rel in files:
                (self._holding(root).move_back if name in on else self._holding(root).move_out)(rel)

    def restore(self):
        left = []
        for root in {r for files in self.mods.values() for r, _ in files}:
            left += self._holding(root).restore()
        return left


class MO2Switcher(Switcher):
    """Mod Organizer 2: the approved Bisect copy profile. Only that copy's modlist.txt is written."""
    method = "Mod Organizer 2"

    def __init__(self, profile_folder, apply_module=None):
        from gg_desktop import bisect_apply, mymods_core
        self.apply_mod = apply_module or bisect_apply
        self.profile_folder = Path(profile_folder)
        text = (self.profile_folder / "modlist.txt").read_text(encoding="utf-8", errors="replace")
        self.enabled = [name for name, mark in mymods_core.parse_modlist(text) if mark == "+"]
        self.copy = None
        self.mods_dir = None                 # set by the window from the instance, for crash-report clues

    def units(self):
        return [_unit(name, name) for name in self.enabled]

    def apply(self, on_keys):
        if self.copy is None:
            self.copy = self.apply_mod.make_copy(self.profile_folder)
        self.apply_mod.write_test(self.copy.folder, sorted(on_keys))

    @property
    def copy_name(self):
        return self.copy.folder.name if self.copy is not None else ""


# ------------------------------------------------------------------ unfinished tests left behind
def leftovers(folders):
    """Holding folders with a manifest still in them (Game Grave closed in the middle of a test)."""
    out = []
    for folder in folders:
        for root in (Path(folder), Path(folder) / "Data"):
            if (root / HOLD_NAME / MANIFEST).is_file():
                out.append(root)
    return out


def put_back(root):
    return _Holding(Path(root)).restore()



# ------------------------------------------------------------------ after the search: keep the cause off
OFF_NAME = "_GameGrave_Turned_Off"     # mods the person chose to keep off after a search; separate from test moves


def turn_off(switcher, keys) -> list:
    """Keep the mods a search named turned off. Folder and Vortex: their files move into OFF_NAME (undo: turn_back_on).
    Mod Organizer 2: unticked in the real profile through My Mods, which keeps a snapshot for its Undo.
    Returns the names that could not be turned off."""
    keys = list(keys)
    if isinstance(switcher, MO2Switcher):
        from gg_desktop import mymods_core
        mymods_core.set_enabled(switcher.profile_folder, keys, False)
        return []
    failed = []
    if isinstance(switcher, FolderSwitcher):
        hold = _Holding(switcher.folder, OFF_NAME)
        failed = [k for k in keys if (switcher.folder / k).exists() and not hold.move_out(k)]
    elif isinstance(switcher, VortexSwitcher):
        for name in keys:
            for root, rel in switcher.mods.get(name, []):
                if (Path(root) / rel).exists() and not _Holding(Path(root), OFF_NAME).move_out(rel):
                    failed.append(name)
                    break
    return failed


def turned_off(folders) -> list:
    """Folders where Crash Doctor is keeping mods turned off."""
    out = []
    for folder in folders:
        for root in (Path(folder), Path(folder) / "Data"):
            if (root / OFF_NAME / MANIFEST).is_file() and root not in out:
                out.append(root)
    return out


def turn_back_on(root) -> list:
    return _Holding(Path(root), OFF_NAME).restore()


def resume_key(method: str, game: str, where) -> str:
    """Where a Crash Doctor search is saved, so Stop (or the launch limit) can continue later."""
    return f"crash-doctor|{method}|{game}|{str(where).casefold()}"



# ------------------------------------------------------------------ the easy path: guess everything, ask one question
# Where games keep mods when no mod manager is used, checked in this order inside the game folder.
MOD_FOLDERS = ("Mods", "mods", "BepInEx/plugins", "MelonLoader/Mods", "archive/pc/mod", "Mods/Mods", "plugins")
OUTSIDE_FOLDERS = {"baldur's gate 3": "Larian Studios/Baldur's Gate 3/Mods"}     # under %LOCALAPPDATA%


def find_mod_folder(install_path, game_name="", local_appdata=None):
    """The folder that holds this game's mods when no mod manager is used, or "" when none is found."""
    candidates = [Path(install_path) / rel for rel in MOD_FOLDERS] if install_path else []
    base = local_appdata if local_appdata is not None else os.environ.get("LOCALAPPDATA", "")
    for words, rel in OUTSIDE_FOLDERS.items():
        if base and words in game_name.casefold():
            candidates.insert(0, Path(base) / rel)
    for folder in candidates:
        try:
            items = [p for p in folder.iterdir() if not p.name.startswith((".", "_GameGrave_"))]
        except OSError:
            continue
        if items:
            return str(folder)
    return ""


# "When does it crash?" -> (key, words, seconds it must run to count as fine, crashes only sometimes, honest note)
WHEN = (("menu", "On the main menu or while it starts", 60, False, ""),
        ("load", "When I load a save or enter a new area", 120, False,
         "Load the save yourself in each test only if it doesn't load by itself; most games reach the menu and that's "
         "enough for crashes on start-up."),
        ("play", "After playing for a while", 300, True,
         "This is the hardest kind: each test waits 5 minutes and may need more launches. If the crash takes longer than "
         "that to happen, Crash Doctor can't catch it."),
        ("random", "Randomly, not every time", 120, True, "Each test may run up to 3 times to be sure."))


def when_choice(key):
    return next((w for w in WHEN if w[0] == key), WHEN[0])


def estimate(mods: int, fine_after: int, sometimes: bool = False):
    """(fewest launches, most launches, fewest minutes, most minutes) for a search over this many mods. One cause takes
    about log2(n) launches; a pair or a second cause adds more. Each launch is the wait plus about a minute to start."""
    import math
    low = max(1, math.ceil(math.log2(max(mods, 1) + 1))) + 1
    high = low * 2 + 2
    if sometimes:
        low, high = low + 1, high * 2
    per = (fine_after + 60) / 60
    return low, min(high, MAX_RUNS), max(1, round(low * per)), max(2, round(min(high, MAX_RUNS) * per))


def remaining(suspects: int, fine_after: int, sometimes: bool = False):
    """(launches left, minutes left), roughly, while a search runs."""
    low, _high, low_min, _ = estimate(max(suspects, 1), fine_after, sometimes)
    return low, low_min


HINTS = {
    "culprit": "Usually this means the mod is out of date for your version of the game, needs another mod it depends on, "
               "or is broken. Check its page for an update and for the mods it requires.",
    "interaction": "These mods fight each other. Often one of them has a patch for the other; otherwise keep only one.",
    "multiple": "Each of these crashes the game by itself. Turning them all off is the quick fix; check each one's page "
                "for an update.",
    "outside": "The game crashed even with every mod off, so a mod isn't the cause. Try Verify Files in Steam (or your "
               "launcher), or Fix my game.",
    "unreproducible": "It didn't crash in any test. If it crashes later in play, run it again and pick \"After playing "
                      "for a while\".",
    "undetermined": "It narrowed things down but couldn't finish. Press Start to carry on.",
}


def headline(kind, names):
    """The one sentence a person reads first."""
    if kind == "culprit" and names:
        return f"Found it: {names[0]} is crashing your game."
    if kind == "interaction" and names:
        return f"Found it: {', '.join(names[:-1])} and {names[-1]} crash when they're on together."
    if kind == "multiple" and names:
        return f"Found {len(names)} mods that crash your game: {', '.join(names[:6])}."
    return {"outside": "It isn't a mod.", "unreproducible": "The game didn't crash in any test.",
            "undetermined": "Not finished yet."}.get(kind, "Done.")


def look_up_url(mod, game):
    from urllib.parse import quote_plus
    return "https://www.google.com/search?q=" + quote_plus(f"{mod} {game} mod")


TOOLS_TO_CLOSE = {"modorganizer.exe": "Mod Organizer 2", "vortex.exe": "Vortex"}


def blockers(process_names, game_exes):
    """Programs that must be closed before testing: the mod managers and the game itself. [(exe, friendly name)]"""
    games = {g.casefold() for g in game_exes}
    out = []
    for name in process_names:
        key = name.casefold()
        if key in TOOLS_TO_CLOSE and (name, TOOLS_TO_CLOSE[key]) not in out:
            out.append((name, TOOLS_TO_CLOSE[key]))
        elif key in games and (name, "the game") not in out:
            out.append((name, "the game"))
    return out


def files_by_mod(switcher, cap=2000):
    """{mod key: file paths in it} so crash logs that name a file point at its mod (for the crash-report clues)."""
    out = {}
    if isinstance(switcher, VortexSwitcher):
        return {name: [str(Path(r) / rel) for r, rel in files[:cap]] for name, files in switcher.mods.items()}
    if isinstance(switcher, FolderSwitcher):
        roots = {u.key: switcher.folder / u.key for u in switcher.units()}
    elif isinstance(switcher, MO2Switcher):
        roots = {k: switcher.mods_dir / k for k in switcher.enabled} if switcher.mods_dir else {}
    else:
        return out
    for key, root in roots.items():
        found = []
        try:
            if root.is_file():
                found = [str(root)]
            else:
                for path in root.rglob("*"):
                    if path.is_file():
                        found.append(str(path))
                        if len(found) >= cap:
                            break
        except OSError:
            pass
        out[key] = found
    return out


@dataclass
class Plan:
    method: str
    game: str
    launch_words: str
    fine_after: int
    sometimes: bool = False
    notes: list = field(default_factory=list)


def confirmation(plan: Plan, units: int, folder: str = "") -> str:
    how = {"Mod Organizer 2": "writes only the Bisect test copy of your profile's modlist (your real profile is untouched)",
           "Vortex": "moves the deployed files of switched-off mods into a holding folder in the game folder, using "
                     "Vortex's own deployment list, and moves them back afterwards (close Vortex first)",
           "Folder": f"moves switched-off items from {folder} into a holding folder next to them, and moves them back "
                     "afterwards"}[plan.method]
    return (f"Crash Doctor will test {units} mods for {plan.game}, up to {MAX_RUNS} launches.\n\n"
            f"For each test it {how}, then starts the game with {plan.launch_words}. If the game is still running after "
            f"{plan.fine_after // 60} minute{'s' if plan.fine_after >= 120 else ''}, it counts as fine and Game Grave "
            "closes it; if it closes or crashes before that, it counts as a crash.\n\n"
            "Nothing is deleted or overwritten. Stop puts everything back and keeps the answers so far, so Start carries on "
            "from where it stopped. Best for crashes on start-up or while loading; "
            "don't use the PC for the game while it runs.")
