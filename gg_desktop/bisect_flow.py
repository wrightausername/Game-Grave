"""Mod Bisect, the walkthrough: everything the Mods > Bisect tab shows, with no Qt and no file access.

`Flow` owns one Bisect run. It builds the engine session from the owner's clues, turns each engine test into plain
instructions, takes the owner's answers (crashed / ran fine / not sure / undo), can be saved and restored between
sessions, and writes the final report. The screen only draws what this returns and forwards clicks.

Nothing here decides anything the engine does not prove: clues and crash reports only order the search.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from gg_desktop import bisect_clues as clues_mod
from gg_desktop.bisect_core import Session, Verdict, batches, recent_order

DAY = 86400.0
SNAPSHOT_VERSION = 1
UNITS = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30, "year": 365, "years": 365}
WORD_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y",
                "%d %B %Y", "%d %b %Y")


def parse_when(text: str, now: float):
    """(epoch seconds or None, problem text). Empty input is fine and means "not given"."""
    raw = (text or "").strip()
    if not raw:
        return None, ""
    low = raw.lower().strip(" .")
    if low in ("today", "now"):
        return now, ""
    if low == "yesterday":
        return now - DAY, ""
    if low in ("last week", "a week ago"):
        return now - 7 * DAY, ""
    if low in ("last month", "a month ago"):
        return now - 30 * DAY, ""
    if low in ("last year", "a year ago"):
        return now - 365 * DAY, ""
    match = re.fullmatch(r"(\d+|a|an|one|two|three|four|five|six)\s+(day|days|week|weeks|month|months|year|years)"
                         r"(?:\s+ago)?", low)
    if match:
        count = int(match.group(1)) if match.group(1).isdigit() else WORD_NUMBERS[match.group(1)]
        return now - count * UNITS[match.group(2)] * DAY, ""
    for fmt in DATE_FORMATS:
        try:
            when = datetime.strptime(raw.strip(" ."), fmt)
        except ValueError:
            continue
        stamp = when.timestamp()
        if stamp > now + DAY:
            return None, "That date is in the future."
        return stamp, ""
    return None, "I could not read that date. Try 2026-10-30, Oct 30 2026, or 2 weeks ago."


def day_text(stamp, now: float) -> str:
    if stamp is None:
        return "Unknown"
    days = int((now - stamp) // DAY)
    date = datetime.fromtimestamp(stamp).strftime("%b %d, %Y").replace(" 0", " ")
    if days < 0:
        return date
    return f"{date} ({'today' if days == 0 else str(days) + 'd ago'})"


@dataclass(frozen=True)
class Setup:
    """What the owner told us. Every field is optional; none of it decides the answer."""
    last_good: float | None = None
    window_start: float | None = None
    hint_keys: tuple = ()
    always_on: tuple = ()
    sometimes: bool = False                 # "it only crashes sometimes"

    @property
    def detect(self) -> float:
        return 0.7 if self.sometimes else 1.0

    @property
    def runs(self) -> int:
        return 3 if self.sometimes else 1


@dataclass(frozen=True)
class StepView:
    kind: str                               # test | done
    number: int = 0
    purpose: str = ""
    title: str = ""
    why: str = ""
    instructions: str = ""
    on_keys: frozenset = frozenset()
    on_names: tuple = ()
    off_count: int = 0
    runs: int = 1
    expected: str = ""


@dataclass(frozen=True)
class RowView:
    key: str
    name: str
    added: str
    status: str
    why: str


TITLES = {"baseline": "Check that it crashes with everything on", "empty": "Check that it stops with the mods off",
          "narrow": "Narrowing it down", "check": "Checking the result", "confirm": "Double-checking the result",
          "clear": "Final check", "fix": "Which single mod is enough"}
PLAY = ("Start the game and do whatever normally makes it crash. ")


def instructions_for(test, number: int) -> str:
    runs = test.runs
    if test.purpose == "baseline":
        lead = "This is your normal setup. It should crash. "
    elif test.purpose == "empty":
        lead = "Only the always-on mods are on. It should NOT crash. "
    else:
        lead = ""
    text = lead + PLAY
    if runs > 1 and test.expected == "ok":
        text += (f"Because the crash does not happen every time, try up to {runs} times. A crash on any try means "
                 "Crashed. Only answer Ran Fine after all of them were clean.")
    elif runs > 1:
        text += f"Try up to {runs} times; one crash is enough to answer Crashed."
    else:
        text += "Then answer below."
    return text


class Flow:
    def __init__(self, units, setup: Setup, *, now: float, clues=None, answers=(), profile_key: str = ""):
        self.base_units = list(units)
        self.setup = setup
        self.now = now
        self.clues = clues
        self.profile_key = profile_key
        self.units = clues_mod.apply_hits(self.base_units, clues) if clues else list(self.base_units)
        self.units = [replace(u, pinned=True) if u.key in set(setup.always_on) else u for u in self.units]
        window = (setup.window_start, now) if setup.window_start is not None else None
        hints = tuple(setup.hint_keys) or (clues_mod.started_after(self.units, clues) if clues else ())
        self.hint_keys = hints
        self.session = Session(self.units, last_good=setup.last_good, now=now, hint_keys=hints, window=window,
                               detect=setup.detect, runs=setup.runs,
                               fault_keys=clues.fault_keys if clues else ())
        for result in answers:
            step = self.session.next_step()
            if isinstance(step, Verdict):
                raise ValueError("The saved answers do not fit this list of mods any more.")
            self.session.record(step, result)

    # ------------------------------------------------------------ current state
    @property
    def names(self) -> dict:
        return {u.key: u.name for u in self.units}

    @property
    def answers(self) -> list:
        return [result for _, result in self.session.tests]

    def started(self) -> bool:
        return bool(self.session.tests)

    def step(self):
        """StepView for the next test, or the engine's Verdict when the search is finished."""
        raw = self.session.next_step()
        if isinstance(raw, Verdict):
            return raw
        number = len(self.session.tests) + 1
        names = self.names
        on = tuple(sorted((names[k] for k in raw.enabled if k in names), key=str.lower))
        return StepView("test", number, raw.purpose, TITLES.get(raw.purpose, "Test"), raw.why,
                        instructions_for(raw, number), frozenset(raw.enabled), on,
                        len(self.units) - len(on), raw.runs, raw.expected)

    def done(self) -> bool:
        return isinstance(self.session.next_step(), Verdict)

    def answer(self, result: str) -> None:
        raw = self.session.next_step()
        if isinstance(raw, Verdict):
            return
        self.session.record(raw, result)

    def undo(self) -> bool:
        return self.session.undo()

    def progress_text(self) -> str:
        info = self.session.progress()
        total = info["of"]
        base = f"{info['launches']} answered · {info['suspects']} of {total} mods still in play"
        if info["causes_found"]:
            base += f" · {info['causes_found']} cause found"
        return base

    # ------------------------------------------------------------ the table
    def rows(self) -> list:
        """One row per mod: most suspicious first before the search, then what the answers say."""
        session = self.session
        final = session.next_step()
        found = {k for g in getattr(final, "groups", ()) for k in g} if isinstance(final, Verdict) else set()
        focus = session.focus
        current = self.step() if not isinstance(final, Verdict) else None
        on = current.on_keys if isinstance(current, StepView) else frozenset()
        ordered = sorted(session.weights, key=lambda k: (-session.weights[k], self.units_by_key[k].name.lower()))
        rows = []
        for key in ordered:
            unit = self.units_by_key[key]
            if found:
                status = "Cause" if key in found else "Not the cause"
            elif not self.started():
                status = "Starts on"
            elif key not in focus:
                status = "Ruled out"
            else:
                status = "On in test" if key in on else "Off in test"
            why = session.reasons[key][0] if session.reasons.get(key) else ""
            rows.append(RowView(key, unit.name, day_text(unit.added, self.now), status, why))
        for key in sorted(session.pinned, key=lambda k: self.units_by_key[k].name.lower()):
            unit = self.units_by_key[key]
            rows.append(RowView(key, unit.name, day_text(unit.added, self.now), "Always on", "you marked it always on"))
        return rows

    @property
    def units_by_key(self) -> dict:
        return {u.key: u for u in self.units}

    def batch_choices(self) -> list:
        """Groups of mods installed together, newest first: (label, keys). For "when I downloaded the pack"."""
        free = [u for u in self.units if not u.pinned]
        out = []
        for batch in batches(free):
            first = datetime.fromtimestamp(batch.start).strftime("%b %d, %Y").replace(" 0", " ")
            count = len(batch.keys)
            names = [self.units_by_key[k].name for k in batch.keys[:2]]
            sample = ", ".join(names) + (" and more" if count > 2 else "")
            out.append((f"{count} installed {first}: {sample}", tuple(batch.keys)))
        return out

    # ------------------------------------------------------------ results
    def cross_check(self) -> list:
        if self.clues is None:
            return []
        verdict = self.session.next_step()
        if not isinstance(verdict, Verdict):
            return clues_mod.what_reports_say(self.clues)
        return clues_mod.cross_reference(self.units, self.clues, verdict)

    def report_text(self, profile_name: str = "") -> str:
        head = f"Profile: {profile_name}\n" if profile_name else ""
        return head + self.session.report(extra=self.cross_check())

    # ------------------------------------------------------------ saving
    def signature(self) -> str:
        payload = [[u.key, u.name, list(u.requires), u.pinned, u.kind, round(u.added or 0), u.crash_hits]
                   for u in sorted(self.units, key=lambda u: u.key)]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:20]

    def snapshot(self) -> dict:
        s = self.setup
        return {"version": SNAPSHOT_VERSION, "profile": self.profile_key, "now": self.now, "signature": self.signature(),
                "last_good": s.last_good, "window_start": s.window_start, "hint_keys": list(s.hint_keys),
                "always_on": list(s.always_on), "sometimes": s.sometimes, "answers": self.answers,
                "hits": dict(self.clues.hits) if self.clues else {},
                "fault_keys": list(self.clues.fault_keys) if self.clues else [],
                "first_crash": self.clues.first_crash if self.clues else None}

    @classmethod
    def restore(cls, units, data: dict, profile_key: str = "") -> "Flow":
        """Rebuild a saved run. Raises ValueError when the data or the mods no longer match."""
        try:
            if data.get("version") != SNAPSHOT_VERSION or data.get("profile", "") != profile_key:
                raise ValueError("This saved search belongs to something else.")
            setup = Setup(data.get("last_good"), data.get("window_start"), tuple(data.get("hint_keys", ())),
                          tuple(data.get("always_on", ())), bool(data.get("sometimes")))
            clues = clues_mod.Clues(hits={k: int(v) for k, v in dict(data.get("hits", {})).items()},
                                    fault_keys=tuple(data.get("fault_keys", ())), first_crash=data.get("first_crash"))
            answers = [a for a in data.get("answers", ()) if a in ("crash", "ok")]
            flow = cls(units, setup, now=float(data["now"]), clues=clues, answers=answers, profile_key=profile_key)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("The saved search could not be read.") from exc
        if flow.signature() != data.get("signature"):
            raise ValueError("Your mods changed since this search started, so it cannot be continued safely.")
        return flow


def mods_to_turn_on(step: StepView, always_on_names=()) -> str:
    """Plain list for managers Game Grave cannot write to: exactly what to switch on."""
    lines = [f"Test {step.number}: {step.title}", f"Turn ON these {len(step.on_names)} mods and turn every other mod OFF:", ""]
    lines += [f"  {name}" for name in step.on_names]
    return "\n".join(lines)
