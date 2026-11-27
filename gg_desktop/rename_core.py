"""Batch Rename engine (Toolbox > Files > Batch Rename). No Qt in this module, so every rule is tested.

Drag files in, type a name, Rename All: typing "WW" gives WW_01.png, WW_02.png, WW_03.png. The whole old name is replaced
and only the extension is kept.

Honesty and safety rules:
* Only names change. File contents are never opened or changed.
* Nothing is ever overwritten. A taken name blocks Rename All until it is fixed, and the move itself refuses to replace a
  file (Windows `os.rename` never replaces), so a file created in the middle of a rename is safe too.
* Every batch is one transaction: all files go to unique temporary names first, then to their final names, with a journal
  on disk. If any step fails, every file is put back. If the PC loses power mid-rename, the next start puts files back.
* Undo is kept on disk (the last 50 batches) and still works after Game Grave is closed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

CASE_KEEP, CASE_LOWER, CASE_UPPER, CASE_TITLE = "keep", "lower", "upper", "title"
DATE_NONE, DATE_TODAY, DATE_FILE = "none", "today", "file"
CASES = (CASE_KEEP, CASE_LOWER, CASE_UPPER, CASE_TITLE)
DATES = (DATE_NONE, DATE_TODAY, DATE_FILE)

INVALID_CHARS = '<>:"/\\|?*'
MAX_HISTORY = 50


@dataclass(frozen=True)
class Item:
    path: str
    is_dir: bool = False
    created: float = 0.0   # seconds since the epoch; 0 when unknown


@dataclass
class Options:
    base_name: str = ""     # replaces the whole original name; empty keeps the original name (advanced edits only)
    start: int = 1
    padding: int = 2
    separator: str = "_"
    find: str = ""          # case-insensitive
    replace: str = ""
    prefix: str = ""
    suffix: str = ""
    remove: str = ""        # every character listed is removed
    case: str = CASE_KEEP
    date: str = DATE_NONE

    @classmethod
    def from_dict(cls, data):
        o = cls()
        if not isinstance(data, dict):
            return o
        for key in ("base_name", "separator", "find", "replace", "prefix", "suffix", "remove"):
            if isinstance(data.get(key), str):
                setattr(o, key, data[key][:200])
        for key, low, high in (("start", 0, 9_999_999), ("padding", 1, 9)):
            value = data.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
                setattr(o, key, value)
        if data.get("case") in CASES:
            o.case = data["case"]
        if data.get("date") in DATES:
            o.date = data["date"]
        return o

    def to_dict(self):
        return dict(self.__dict__)


# ------------------------------------------------------------------ naming
def split_name(item: Item):
    """(stem, extension). Folders never have an extension."""
    name = Path(item.path).name
    if item.is_dir:
        return name, ""
    ext = Path(name).suffix
    if ext == name:          # ".gitignore": the whole name is the extension, like Windows treats it
        return "", ext
    return name[:len(name) - len(ext)], ext


def number(index: int, total: int, o: Options) -> str:
    """The sequence number. Padding grows when the batch needs more digits, so 1,000 files still sort correctly."""
    start = max(0, int(o.start))
    pad = min(9, max(1, int(o.padding)))
    if total > 0:
        pad = max(pad, len(str(start + total - 1)))
    return str(start + index).zfill(pad)


def _replace_fold(text: str, find: str, repl: str) -> str:
    if not find:
        return text
    low, lf = text.casefold(), find.casefold()
    if len(low) != len(text) or len(lf) != len(find):
        return text.replace(find, repl)
    out, i = [], 0
    while True:
        j = low.find(lf, i)
        if j < 0:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:j])
        out.append(repl)
        i = j + len(find)


def _apply_case(text: str, case: str) -> str:
    if case == CASE_LOWER:
        return text.lower()
    if case == CASE_UPPER:
        return text.upper()
    if case == CASE_TITLE:
        out, start = [], True
        for ch in text.lower():
            if ch in " _-.":
                start = True
                out.append(ch)
            elif start:
                out.append(ch.upper())
                start = False
            else:
                out.append(ch)
        return "".join(out)
    return text


def new_name(item: Item, index: int, total: int, o: Options, now: float | None = None) -> str:
    stem, ext = split_name(item)
    base = o.base_name.strip()
    numbered = bool(base)
    if numbered:
        stem = base
    if o.find:
        stem = _replace_fold(stem, o.find, o.replace)
    if o.remove:
        stem = "".join(ch for ch in stem if ch not in o.remove)
    stem = _apply_case(stem, o.case)
    parts = [o.prefix, stem]
    if o.date in (DATE_TODAY, DATE_FILE):
        when = item.created if (o.date == DATE_FILE and item.created) else (now if now is not None else time.time())
        parts += [o.separator, datetime.fromtimestamp(when).strftime("%Y-%m-%d")]
    if numbered:
        parts += [o.separator, number(index, total, o)]
    parts += [o.suffix, ext]
    return "".join(parts)


def valid_name(name: str):
    """(ok, reason) for a Windows file name."""
    if not name.strip():
        return False, "Name is empty"
    if len(name) > 255:
        return False, "Name is too long"
    if any(ord(ch) < 32 or ch in INVALID_CHARS for ch in name):
        return False, "Contains a character Windows does not allow"
    if name.endswith((" ", ".")):
        return False, "Cannot end with a space or dot"
    dev = name.upper().split(".", 1)[0].strip()
    if dev in {"CON", "PRN", "AUX", "NUL"} or (len(dev) == 4 and dev[:3] in {"COM", "LPT"} and dev[3].isdigit()):
        return False, "Reserved Windows name"
    return True, ""


def natural_key(name: str):
    """Sort so img2 comes before img10."""
    out, digits = [], ""
    for ch in name.casefold():
        if ch.isdigit():
            digits += ch
            continue
        if digits:
            out.append((0, int(digits), ""))
            digits = ""
        out.append((1, 0, ch))
    if digits:
        out.append((0, int(digits), ""))
    return out


def sort_by_created(items):
    """Oldest first, then natural name order."""
    return sorted(items, key=lambda it: (it.created, natural_key(Path(it.path).name)))


# ------------------------------------------------------------------ plan and checks
OK, UNCHANGED, DUPLICATE, EXISTS, INVALID, MISSING, NESTED = "ok", "unchanged", "duplicate", "exists", "invalid", "missing", "nested"
BLOCKING = {DUPLICATE, EXISTS, INVALID, MISSING, NESTED}
MESSAGES = {
    DUPLICATE: "Two files would get this name",
    EXISTS: "A file with this name already exists",
    INVALID: "Not a valid file name",
    MISSING: "This file is no longer there",
    NESTED: "Inside a folder that is also being renamed",
    UNCHANGED: "No change",
}


@dataclass
class Planned:
    src: str
    dst: str
    name: str
    status: str = OK
    reason: str = ""

    @property
    def blocking(self):
        return self.status in BLOCKING

    @property
    def message(self):
        return self.reason or MESSAGES.get(self.status, "")


def key(path: str) -> str:
    """Windows compares names without case."""
    return os.path.normcase(os.path.normpath(str(path))).casefold()


def _exists(path: str) -> bool:
    return os.path.lexists(path)


def plan(items, o: Options, now: float | None = None, exists=_exists):
    total = len(items)
    out = []
    for i, it in enumerate(items):
        name = new_name(it, i, total, o, now)
        out.append(Planned(src=it.path, dst=str(Path(it.path).parent / name), name=name))
    check(out, items, exists)
    return out


def check(plans, items, exists=_exists):
    srcs = {key(p.src) for p in plans}
    sep = os.sep
    dirs = [key(p.src) + sep for p, it in zip(plans, items) if it.is_dir and p.dst != p.src]
    counts = {}
    for p in plans:
        p.status, p.reason = OK, ""
        ok, why = valid_name(p.name)
        if not ok:
            p.status, p.reason = INVALID, why
            continue
        if exists is not None and not exists(p.src):
            p.status = MISSING
            continue
        ks = key(p.src)
        if any(ks.startswith(d) for d in dirs):
            p.status = NESTED
            continue
        kd = key(p.dst)
        counts[kd] = counts.get(kd, 0) + 1
        if p.dst == p.src:
            p.status = UNCHANGED
            continue
        if kd != ks and kd not in srcs and exists is not None and exists(p.dst):
            p.status = EXISTS
    for p in plans:
        if p.status in (OK, UNCHANGED) and counts.get(key(p.dst), 0) > 1:
            p.status = DUPLICATE


def ops_of(plans):
    return [Op(p.src, p.dst) for p in plans if p.status == OK]


def problems(plans):
    return sum(1 for p in plans if p.blocking)


# ------------------------------------------------------------------ safe moves
def move_no_replace(src: str, dst: str):
    """Rename without ever replacing. On Windows os.rename refuses an existing target by itself."""
    if sys.platform == "win32":
        os.rename(src, dst)
        return
    if os.path.lexists(dst):
        raise FileExistsError(17, "File exists", dst)
    if os.path.isdir(src) and not os.path.islink(src):
        os.rename(src, dst)
        return
    os.link(src, dst, follow_symlinks=False)
    os.unlink(src)


# ------------------------------------------------------------------ transactions and undo
@dataclass(frozen=True)
class Op:
    src: str
    dst: str


@dataclass
class Batch:
    id: str
    when: str
    ops: list = field(default_factory=list)


class RenameError(Exception):
    """A batch stopped. rolled_back True means every file has its old name again."""

    def __init__(self, op: Op, reason: str, rolled_back: bool, rollback_problem: str = ""):
        self.op, self.reason, self.rolled_back, self.rollback_problem = op, reason, rolled_back, rollback_problem
        text = f"Could not rename {Path(op.src).name} to {Path(op.dst).name}: {reason}."
        text += " Nothing was changed." if rolled_back else f" Some files could not be put back: {rollback_problem}"
        super().__init__(text)


class NothingToUndo(Exception):
    pass


def _reason(exc) -> str:
    if isinstance(exc, FileExistsError):
        return "a file with that name already exists"
    if isinstance(exc, PermissionError):
        return "Windows refused (the file may be open in another program, or you don't have permission)"
    if isinstance(exc, FileNotFoundError):
        return "the file or folder is no longer there"
    return getattr(exc, "strerror", None) or str(exc) or type(exc).__name__


def _write_json(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)   # Game Grave's own data file, so replacing it is right


class Store:
    """Runs batches and keeps the undo history in `folder`."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.lock = threading.Lock()
        self.history = []
        self.recovered = False
        self.recover_problem = ""
        self.folder.mkdir(parents=True, exist_ok=True)
        try:
            raw = json.loads((self.folder / "undo-history.json").read_text(encoding="utf-8"))
            for b in raw if isinstance(raw, list) else []:
                ops = [Op(str(o["src"]), str(o["dst"])) for o in b.get("ops", []) if isinstance(o, dict)]
                if ops:
                    self.history.append(Batch(str(b.get("id", "")), str(b.get("when", "")), ops))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        self._recover()

    @property
    def journal(self):
        return self.folder / "rename-journal.json"

    def can_undo(self):
        with self.lock:
            return bool(self.history)

    def last(self):
        with self.lock:
            return self.history[-1] if self.history else None

    def _save(self):
        _write_json(self.folder / "undo-history.json",
                    [{"id": b.id, "when": b.when, "ops": [{"src": o.src, "dst": o.dst} for o in b.ops]} for b in self.history])

    # -- apply
    def apply(self, ops, progress=None) -> Batch:
        with self.lock:
            batch = self._run(list(ops), progress)
            self.history.append(batch)
            del self.history[:-MAX_HISTORY]
            self._save()
            return batch

    def _run(self, ops, progress):
        if not ops:
            raise ValueError("Nothing to rename.")
        srcs = {key(o.src) for o in ops}
        seen = set()
        for o in ops:       # check the real disk again, right before anything moves
            if not _exists(o.src):
                raise RenameError(o, "the file is no longer there", True)
            kd = key(o.dst)
            if kd in seen:
                raise RenameError(o, "two files would get the same name", True)
            seen.add(kd)
            if kd not in srcs and _exists(o.dst):
                raise RenameError(o, "a file with that name already exists", True)
        tx = f"{int(time.time() * 1000):x}{secrets.token_hex(3)}"
        steps = []
        for i, o in enumerate(ops):
            folder = Path(o.src).parent
            temp = folder / f".ggbr-{tx}-{i}.tmp"
            n = 0
            while _exists(temp):
                n += 1
                temp = folder / f".ggbr-{tx}-{i}-{n}.tmp"
            steps.append({"src": o.src, "temp": str(temp), "dst": o.dst})
        journal = {"id": tx, "phase": 1, "steps": steps}
        _write_json(self.journal, journal)
        total, done = len(steps) * 2, 0

        def tick():
            nonlocal done
            done += 1
            if progress and (done % 25 == 0 or done == total):
                progress(done, total)

        for i, s in enumerate(steps):
            try:
                move_no_replace(s["src"], s["temp"])
            except OSError as exc:
                problem = self._rollback(steps[:i], 0)
                self._finish(problem)
                raise RenameError(Op(s["src"], s["dst"]), _reason(exc), not problem, problem) from None
            tick()
        journal["phase"] = 2
        try:
            _write_json(self.journal, journal)
        except OSError as exc:
            problem = self._rollback(steps, 0)
            self._finish(problem)
            raise RenameError(ops[0], "the safety journal could not be updated: " + _reason(exc), not problem, problem) from None
        for i, s in enumerate(steps):
            try:
                move_no_replace(s["temp"], s["dst"])
            except OSError as exc:
                problem = self._rollback(steps, i)
                self._finish(problem)
                raise RenameError(Op(s["src"], s["dst"]), _reason(exc), not problem, problem) from None
            tick()
        self._finish("")
        return Batch(tx, datetime.now().astimezone().isoformat(timespec="seconds"), ops)

    def _finish(self, problem):
        if not problem:
            try:
                self.journal.unlink()
            except OSError:
                pass

    @staticmethod
    def _rollback(steps, finished_phase2):
        problems_ = []
        for s in reversed(steps[:finished_phase2]):
            try:
                move_no_replace(s["dst"], s["temp"])
            except OSError as exc:
                problems_.append(f"{Path(s['dst']).name}: {_reason(exc)}")
        for s in reversed(steps):
            if _exists(s["temp"]):
                try:
                    move_no_replace(s["temp"], s["src"])
                except OSError as exc:
                    problems_.append(f"{Path(s['temp']).name}: {_reason(exc)}")
        return "; ".join(problems_)

    def _recover(self):
        """Put files back after a crash or power loss in the middle of a batch."""
        try:
            journal = json.loads(self.journal.read_text(encoding="utf-8"))
            steps = [s for s in journal.get("steps", []) if all(isinstance(s.get(k), str) for k in ("src", "temp", "dst"))]
        except (OSError, ValueError, AttributeError):
            return
        if not steps:
            self._finish("")
            return
        problems_ = []
        if journal.get("phase") == 2:
            # Every source reached its temp name, so a final name whose temp is gone was made by this batch.
            for s in reversed(steps):
                if not _exists(s["temp"]) and _exists(s["dst"]):
                    try:
                        move_no_replace(s["dst"], s["temp"])
                    except OSError as exc:
                        problems_.append(f"{Path(s['dst']).name}: {_reason(exc)}")
        for s in reversed(steps):
            if _exists(s["temp"]):
                try:
                    move_no_replace(s["temp"], s["src"])
                except OSError as exc:
                    problems_.append(f"{Path(s['temp']).name}: {_reason(exc)}")
        self.recovered = True
        self.recover_problem = "; ".join(problems_)
        self._finish(self.recover_problem)

    # -- undo
    def undo_plan(self):
        """(ops that can be reversed, how many cannot) for the last batch."""
        with self.lock:
            return self._undo_plan()

    def _undo_plan(self):
        if not self.history:
            raise NothingToUndo()
        freed, cand, bad = set(), [], 0
        for o in self.history[-1].ops:
            if not _exists(o.dst):
                bad += 1
                continue
            cand.append(Op(o.dst, o.src))
            freed.add(key(o.dst))
        ready = []
        for o in cand:
            if key(o.dst) != key(o.src) and _exists(o.dst) and key(o.dst) not in freed:
                bad += 1
                continue
            ready.append(o)
        return ready, bad

    def undo_last(self, skip_unavailable=False, progress=None):
        """Reverse the last batch. Returns the ops that ran (src is the name before undo)."""
        with self.lock:
            ready, bad = self._undo_plan()
            if bad and not skip_unavailable:
                raise ValueError(f"{bad} file(s) from the last rename can no longer be put back.")
            if ready:
                self._run(ready, progress)
            self.history.pop()
            self._save()
            return ready


def scan_paths(paths, rename_folders=False):
    """Turn dropped paths into items. A dropped folder adds the files directly inside it (hidden and system files left
    out), or the folder itself when rename_folders is on."""
    out = []
    for raw in paths:
        p = Path(str(raw))
        try:
            if p.is_dir() and not rename_folders:
                with os.scandir(p) as entries:
                    for e in entries:
                        try:
                            if e.is_file(follow_symlinks=False) and not _hidden(e):
                                out.append(Item(e.path, False, _created(e.stat(follow_symlinks=False))))
                        except OSError:
                            continue
            elif p.exists():
                out.append(Item(str(p), p.is_dir(), _created(p.stat())))
        except OSError:
            continue
    return out


def _created(st) -> float:
    return float(getattr(st, "st_birthtime", 0) or (st.st_ctime if sys.platform == "win32" else st.st_mtime))


def _hidden(entry) -> bool:
    attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attrs & 0x6) or entry.name.casefold() in {"desktop.ini", "thumbs.db"}
