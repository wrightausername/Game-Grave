"""Mod Bisect: find which mods are behind a crash, however many of them there are.

This is the decision engine only. It never touches a file and never launches a game. It is told which mods exist
(and what is known about each), it proposes one test at a time ("run the game with exactly these mods on"), the owner
runs it and answers crashed / fine / not sure, and the engine decides the next test.

What "reliable" means here. The answer is never inferred from a guess or from a date. It is a set of mods that your
own launches showed to be the cause:
  1. With only that set (plus mods that cannot be turned off) the game crashes.
  2. Take away any one mod of the set (and whatever needs it) and the crash stops. So nothing in it is spare.
  3. With the set off and every other mod on, the game runs. If it still crashes, there is another, separate cause;
     the search repeats until the game runs, and every cause is listed.
It works for one mod, two mods that only crash together, ten, or several unrelated causes at once, because it keeps
shrinking a crashing setup until nothing more can be taken away (the "delta debugging" method) instead of assuming
one culprit.

What the clues do. Dates, "it started after I added these", a pack you downloaded, and crash-log hits are only
hints that decide which tests run first, so the answer usually arrives in far fewer launches. A wrong hint costs
launches, never correctness: the first tests check the hinted mods and the rest separately, and the three checks
above are always run before anything is named.

Other things it does: it first checks that the crash really happens with everything on and stops with every mod
off (otherwise it says the cause is not a mod); it keeps mods that need each other together; crashes that do not
always happen get repeat runs, and the answer says how sure it is; a wrong tap can be undone.

What it cannot know: it assumes the crash depends only on which mods are on. A crash that depends on one particular
save, or on the order mods load in, can look unrelated to any mod; the engine says so when the results do not fit.

Pure Python (no Qt) so every rule is unit tested.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MAX_TESTS = 400            # a search that needs more says where it got to instead of running forever
MAX_CAUSES = 8             # separate causes found one after another
PROOF_MISS = 0.001         # chance a real crash goes unseen in a check that must be trustworthy
HOUR = 3600.0
DAY = 86400.0


@dataclass(frozen=True)
class Unit:
    """One thing that can be switched on or off. A mod folder, a Workshop item, a plugin."""
    key: str
    name: str
    added: float | None = None        # when it appeared (epoch seconds); None when unknown
    kind: str = "unknown"              # "code" (scripts, plugins, DLLs), "assets" (textures, sounds) or "unknown"
    requires: tuple = ()               # keys of units it cannot work without
    pinned: bool = False               # always on (a framework you cannot test without)
    crash_hits: int = 0                # times a crash log named files inside it


@dataclass(frozen=True)
class Test:
    purpose: str                       # baseline, empty, narrow, check, clear
    enabled: frozenset                 # exactly these units on, everything else off
    runs: int                          # launches to do before answering "fine"; stop at the first crash
    why: str
    expected: str = ""                 # "crash" or "ok" when the test is a check, else ""
    under_test: tuple = ()             # units this test is about


@dataclass(frozen=True)
class Verdict:
    kind: str                          # culprit, interaction, multiple, outside, unreproducible, undetermined
    keys: tuple                        # every mod named as part of a cause
    confidence: float                  # 1.0 when the crash is reliable and all checks passed
    text: str
    groups: tuple = ()                 # one tuple of keys per separate cause
    fixes: tuple = ()                  # mods that, turned off alone, were shown to stop the crash


@dataclass(frozen=True)
class Batch:
    start: float
    end: float
    keys: tuple


def _plural(n, word):
    if n == 1:
        return f"{n} {word}"
    return f"{n} {word}" + ("es" if word.endswith(("ch", "sh", "s", "x")) else "s")


def _sure(confidence):
    if confidence >= 0.995:
        return "over 99%"
    return f"about {int(100 * confidence)}%"


def _percent(p):
    """A chance as text that never rounds a real risk down to nothing."""
    if p <= 0:
        return "0%"
    if p < 0.01:
        return "less than 1%"
    return f"{round(100 * p)}%"


def suspicion(unit: Unit, last_good: float | None, now: float | None, hinted: bool = False,
              in_window: bool = False) -> tuple[float, list]:
    """Weight and the plain reasons behind it. These only order the tests."""
    weight, reasons = 1.0, []
    if hinted:
        weight *= 60.0
        reasons.append("you said the crashes started after adding it")
    if in_window:
        weight *= 12.0
        reasons.append("added in the time you named")
    if unit.kind == "code":
        weight *= 3.0
        reasons.append("contains scripts or plugins, which can crash a game")
    if unit.added is None:
        reasons.append("install date unknown")
    elif last_good is not None:
        if unit.added > last_good:
            weight *= 8.0
            reasons.append("added after the game last worked")
        else:
            reasons.append("was already installed when the game last worked")
    elif now is not None:
        days = max(0.0, (now - unit.added) / DAY)
        weight *= 1.0 + 2.0 * math.exp(-days / 21.0)
        reasons.append(f"added {_plural(int(days), 'day')} ago")
    if unit.crash_hits:
        weight *= 1.0 + 25.0 * min(unit.crash_hits, 4)
        reasons.append(f"named in {_plural(unit.crash_hits, 'crash log')}")
    return weight, reasons


def recent_order(units, last_good: float | None = None, now: float | None = None) -> list:
    """Newest first, with the reason shown to the owner. Units with no date go last."""
    rows = []
    for u in units:
        if u.added is None:
            label = "install date unknown"
        else:
            note = ""
            if last_good is not None:
                note = ", after the game last worked" if u.added > last_good else ", before the game last worked"
            age = f"{_plural(int(max(0.0, (now - u.added) / DAY)), 'day')} ago" if now is not None else "dated"
            label = f"added {age}{note}"
        rows.append((u, label))
    rows.sort(key=lambda r: (r[0].added is None, -(r[0].added or 0.0), r[0].name.lower()))
    return rows


def batches(units, gap_hours: float = 6.0) -> list:
    """Mods installed together, newest batch first. A pack or a modlist you downloaded lands as one batch, so
    "when I downloaded the pack" can be picked from a list instead of remembered as a date."""
    dated = sorted((u for u in units if u.added is not None), key=lambda u: u.added)
    found, current = [], []
    for unit in dated:
        if current and unit.added - current[-1].added > gap_hours * HOUR:
            found.append(current)
            current = []
        current.append(unit)
    if current:
        found.append(current)
    out = [Batch(group[0].added, group[-1].added, tuple(u.key for u in group)) for group in found]
    out.sort(key=lambda b: -b.end)
    return out


class _OutOfBudget(Exception):
    pass


class Session:
    def __init__(self, units, *, last_good: float | None = None, now: float | None = None,
                 hint_keys=(), window: tuple | None = None, detect: float = 1.0, runs: int = 1):
        self.units = {u.key: u for u in units}
        self.pinned = frozenset(k for k, u in self.units.items() if u.pinned)
        self.detect = min(max(detect, 0.05), 1.0)
        self.runs = max(1, int(runs))
        self._requires = {k: tuple(r for r in u.requires if r in self.units) for k, u in self.units.items()}
        hinted = {k for k in hint_keys if k in self.units}
        self.weights, self.reasons, self.priority = {}, {}, set()
        for key, unit in self.units.items():
            if key in self.pinned:
                continue
            in_window = bool(window and unit.added is not None and window[0] <= unit.added <= window[1])
            self.weights[key], self.reasons[key] = suspicion(unit, last_good, now, key in hinted, in_window)
            if key in hinted or in_window:
                self.priority.add(key)
        if not self.priority and last_good is not None:
            self.priority = {k for k in self.weights if (self.units[k].added or 0) > last_good and self.units[k].added}
        self.tests: list[tuple[Test, str]] = []
        self.unsure = 0
        self._focus = frozenset(self.weights)
        self._causes: list = []

    # ------------------------------------------------------------ dependencies
    def closure(self, keys) -> frozenset:
        """The keys plus everything they need, directly or through other mods."""
        out, stack = set(), list(keys)
        while stack:
            key = stack.pop()
            if key in out or key not in self.units:
                continue
            out.add(key)
            stack.extend(self._requires[key])
        return frozenset(out)

    def dependents(self, key) -> frozenset:
        """The key plus every unit that needs it: what has to go off with it."""
        return self.dependents_of({key})

    def dependents_of(self, keys) -> frozenset:
        out, changed = set(keys), True
        while changed:
            changed = False
            for k, needs in self._requires.items():
                if k not in out and any(n in out for n in needs):
                    out.add(k)
                    changed = True
        return frozenset(out)

    # ------------------------------------------------------------ runs and confidence
    def _miss(self, runs: int) -> float:
        return (1.0 - self.detect) ** runs

    def _proof_runs(self) -> int:
        """Launches so that a real crash goes unseen less than 0.1% of the time."""
        if self.detect >= 1.0:
            return self.runs
        return max(self.runs, min(12, math.ceil(math.log(PROOF_MISS) / math.log(1.0 - self.detect))))

    def _enabled(self, free_keys) -> frozenset:
        return self.closure(set(free_keys) | set(self.pinned))

    def _test(self, purpose, free_keys, why, *, runs=None, expected="", under=()) -> Test:
        return Test(purpose, self._enabled(free_keys), runs or self.runs, why, expected, tuple(under))

    def _names(self, keys, limit=6) -> str:
        names = [self.units[k].name for k in sorted(keys, key=lambda k: self.units[k].name.lower())]
        more = len(names) - limit
        return ", ".join(names[:limit]) + (f" and {more} more" if more > 0 else "")

    # ------------------------------------------------------------ the search
    def _asker(self):
        memo = {}
        budget = [0]

        def ask(test, fresh=False):
            known = memo.get(test.enabled)
            if not fresh and known and (known[0] == "crash" or known[1] >= test.runs):
                return known[0]
            if budget[0] >= MAX_TESTS:
                raise _OutOfBudget()
            budget[0] += 1
            result = yield test
            memo[test.enabled] = (result, test.runs)
            return result
        return ask

    def _chunks(self, focus, n):
        order = sorted(focus, key=lambda k: (k not in self.priority, -self.weights[k], k))
        inside = sum(1 for k in order if k in self.priority)
        if n == 2 and 0 < inside < len(order):
            return [order[:inside], order[inside:]]
        size, extra = divmod(len(order), n)
        out, at = [], 0
        for i in range(n):
            step = size + (1 if i < extra else 0)
            out.append(order[at:at + step])
            at += step
        return [c for c in out if c]

    def _shrink(self, focus, ask):
        """Delta debugging: keep a crashing set and take pieces away until nothing more can go.

        At two pieces each half is tried on its own. At finer cuts the pieces are taken away one after the
        other, least suspicious first, and every piece that is not needed stays removed for the rest of the pass."""
        focus = frozenset(focus)
        n = 2
        while len(focus) > 1:
            self._focus = focus
            chunks = self._chunks(focus, min(n, len(focus)))
            reduced = False
            if len(chunks) <= 2:
                for chunk in chunks:                               # does a half alone crash?
                    part = self.closure(chunk) & focus
                    if part and part != focus:
                        test = self._test("narrow", part, f"Only these {_plural(len(part), 'mod')} on: "
                                          "does it still crash? If yes, the cause is inside them.", under=part)
                        if (yield from ask(test)) == "crash":
                            focus, reduced = frozenset(part), True
                            break
                if reduced:
                    continue
            current = focus
            for chunk in reversed(chunks):                         # does it still crash without a piece?
                rest = current - self.dependents_of(chunk)
                if rest and rest != current:
                    test = self._test("narrow", rest, f"Without these {_plural(len(chunk), 'mod')}: does it "
                                      "still crash? If yes, none of them is needed for the crash.", under=chunk)
                    if (yield from ask(test)) == "crash":
                        current, reduced = frozenset(rest), True
            if reduced:
                focus, n = current, max(2, n // 2)
                continue
            if n >= len(focus):
                break
            n = min(len(focus), n * 2)
        self._focus = focus
        return focus

    def _flow(self):
        ask = self._asker()
        everyone = frozenset(self.weights)
        base = self._test("baseline", everyone, "Check the crash happens with every mod on. A search cannot start "
                          "from a crash you cannot trigger.", runs=max(self.runs, self._proof_runs()), expected="crash")
        if (yield from ask(base)) == "ok":
            miss = self._miss(base.runs)
            return Verdict("unreproducible", (), 0.0,
                           f"The game did not crash in {_plural(base.runs, 'launch')} with every mod on, so there is "
                           f"nothing to narrow down yet. At your detection rate a real crash would go unseen {_percent(miss)} of the "
                           "time even when the crash is real. If it only crashes sometimes, use more runs per test and "
                           "start again.")
        empty = self._test("empty", (), "Check the crash stops with every mod off (only the always-on ones stay).",
                           runs=self._proof_runs(), expected="ok")
        if (yield from ask(empty)) == "crash":
            kept = (f" Only the always-on mods ({len(self.pinned)}) were left on, so one of those is also possible."
                    if self.pinned else "")
            return Verdict("outside", (), 1.0,
                           "The game still crashes with the mods off, so the cause is not one of the mods you can turn "
                           "off. Check the game files, the graphics driver, and the crash report from Black Box." + kept)
        proofs = 1
        causes = []
        off = frozenset()
        complete = False
        while len(causes) < MAX_CAUSES:
            remaining = everyone - off
            focus = remaining
            while True:
                found = yield from self._shrink(focus, ask)
                # 1-minimal: removing any one piece (with what needs it) must stop the crash, proven with full runs
                again = None
                for key in sorted(found):
                    rest = found - self.dependents(key)
                    if not rest:
                        continue
                    test = self._test("check", rest, f"Check: turn off only {self.units[key].name} (and what needs "
                                      "it) from the crashing set. The crash should stop.",
                                      runs=self._proof_runs(), expected="ok", under=(key,))
                    if (yield from ask(test)) == "crash":
                        again = rest
                        break
                    proofs += 1
                if again is not None:
                    focus = again
                    continue
                # the set must crash on its own, asked again so one wrong tap cannot carry the verdict
                confirm = self._test("confirm", found, "Double-check: only these mods on. It crashed in an earlier "
                                     "test; does it crash again?", runs=self._proof_runs(), expected="crash",
                                     under=found)
                if (yield from ask(confirm, fresh=True)) == "crash":
                    break
                focus = remaining                                   # the answers disagree: search again
            causes.append(found)
            self._causes = list(causes)
            off = off | self.dependents_of(found)
            clear = self._test("clear", everyone - off, "Fix check: every cause found so far off, everything else "
                               "on. It should run without crashing.", runs=self._proof_runs(), expected="ok")
            if (yield from ask(clear)) == "ok":
                proofs += 1
                complete = True
                break
        if not complete:
            return self._finish(causes, proofs, complete=False, fixes=())
        fixes = []
        if len(causes) == 1 and len(causes[0]) > 1:
            for key in sorted(causes[0]):
                test = self._test("fix", everyone - self.dependents(key), f"Fix check: turn off only "
                                  f"{self.units[key].name} (and what needs it), everything else on.",
                                  runs=self._proof_runs(), expected="ok", under=(key,))
                if (yield from ask(test)) == "ok":
                    fixes.append(key)
                    proofs += 1
        else:
            fixes = list(causes[0]) if len(causes) == 1 else []
        return self._finish(causes, proofs, complete=True, fixes=tuple(fixes))

    def _describe(self, group) -> str:
        names = self._names(group)
        inside = [(k, r) for k in sorted(group) for r in self._requires[k] if r in group]
        if len(group) == 1:
            line = f"{names} is the cause. The crash stopped without it and came back with it."
        else:
            line = f"{names} crash the game together. Take away any one of them and it stops."
        if inside:
            pairs = "; ".join(f"{self.units[a].name} needs {self.units[b].name}" for a, b in inside[:4])
            line += f" They have to be switched together ({pairs}), so this test cannot separate them."
        return line

    def _finish(self, causes, proofs, complete, fixes=()) -> Verdict:
        confidence = 1.0
        if self.detect < 1.0:
            confidence = max(0.0, (1.0 - self._miss(self._proof_runs())) ** proofs)
        keys = tuple(sorted({k for c in causes for k in c}))
        groups = tuple(tuple(sorted(c)) for c in causes)
        if len(causes) == 1:
            kind = "culprit" if len(groups[0]) == 1 else "interaction"
            text = self._describe(causes[0])
        else:
            kind = "multiple"
            text = f"The crash has {len(causes)} separate causes, and each one alone is enough: " + " ".join(
                f"({i}) {self._describe(c)}" for i, c in enumerate(causes, 1))
        if complete and len(causes) == 1 and len(causes[0]) > 1:
            if len(fixes) == len(causes[0]):
                text += " Turning off any one of them is enough."
            elif fixes:
                text += f" Turning off just {self._names(fixes)} is enough."
            else:
                text += " No single one of them is enough on its own, so turn them off together."
        if not complete:
            kind = "undetermined"
            text += f" More causes may remain: the search stopped after {MAX_CAUSES}."
        else:
            text += " With these off the game ran without crashing. This comes from your test results, not from guesses."
        if self.detect < 1.0 and complete:
            text += (f" Because the crash does not always show, this is {_sure(confidence)} sure, "
                     "not certain.")
        return Verdict(kind, keys, confidence, text, groups, tuple(sorted(fixes)))

    def _run(self):
        try:
            verdict = yield from self._flow()
        except _OutOfBudget:
            return self._out_of_budget()
        return verdict

    def _out_of_budget(self) -> Verdict:
        focus = sorted(self._focus, key=lambda k: (-self.weights[k], k))
        return Verdict("undetermined", tuple(focus[:12]), 0.0,
                       f"This needed more than {MAX_TESTS} launches. It did narrow the crash to {_plural(len(focus), 'mod')}"
                       f" ({self._names(focus, 8)}). A crash that depends on your save or on load order, or that needs a "
                       "very large group of mods together, cannot be pinned down further this way.")

    # ------------------------------------------------------------ public steps
    def next_step(self):
        """The next Test to run, or the Verdict when the evidence is enough."""
        gen = self._run()
        try:
            step = next(gen)
            for recorded, result in self.tests:
                if step.enabled != recorded.enabled:
                    raise RuntimeError("answers no longer match the search; start a new Bisect")
                step = gen.send(result)
            return step
        except StopIteration as done:
            return done.value

    def record(self, test: Test, result: str) -> None:
        """result: crash, ok, or unsure. Unsure adds no evidence; the same test will be asked again."""
        if result == "unsure":
            self.unsure += 1
            return
        if result not in ("crash", "ok"):
            raise ValueError("result must be crash, ok or unsure")
        self.tests.append((test, result))

    def undo(self) -> bool:
        """Take back the last answer (a wrong tap). The search is replayed from the answers that remain."""
        if self.tests:
            self.tests.pop()
            return True
        return False

    def progress(self) -> dict:
        """What the screen can show while the search runs."""
        self.next_step()
        return {"launches": len(self.tests), "suspects": len(self._focus), "of": len(self.weights),
                "causes_found": len(self._causes)}

    def suspects(self):
        """Mods still in play, most suspicious first, with the reasons. 'share' is relative suspicion, not a chance."""
        self.next_step()
        focus = [k for k in self.weights if k in self._focus]
        total = sum(self.weights[k] for k in focus) or 1.0
        rows = [(self.units[k], self.weights[k] / total, self.reasons[k]) for k in focus]
        rows.sort(key=lambda r: (-r[1], r[0].name.lower()))
        return rows

    def report(self) -> str:
        step = self.next_step()
        lines = ["Mod Bisect report", ""]
        for i, (test, result) in enumerate(self.tests, 1):
            lines.append(f"{i}. {test.purpose}: {len(test.enabled)} of {len(self.units)} mods on -> {result}")
        if isinstance(step, Verdict):
            lines += ["", step.text]
        lines += ["", "Only your test answers count as proof. The suspicion order is a starting point, not a finding."]
        return "\n".join(lines)
