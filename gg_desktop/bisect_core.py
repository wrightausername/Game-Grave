"""Mod Bisect: find the mod behind a crash with as few launches as the evidence allows.

This is the decision engine only. It never touches a file and never launches a game. It is told which mods exist
(and what is known about each), it proposes one test at a time ("run the game with exactly these mods on"), the owner
runs it and answers crashed / fine / not sure, and the engine updates what it believes.

Why this is more than "disable half, try again":
* Every mod starts with a suspicion weight built from facts it was given, not guesses: added after the last time the
  game worked, contains scripts or plugins (assets such as textures rarely crash a game), named in a crash log. The
  weights only decide which tests are asked first. Only the owner's test results ever count as proof.
* Each test splits the remaining suspicion in half, not the number of mods, so a recent script mod is checked early.
* Mods that need other mods are switched on and off together, so a test never builds a setup that cannot load.
* A crash that does not always happen is handled with a detection rate and repeat runs: one "fine" run proves little
  when the crash only appears half the time, and the engine says so instead of clearing a mod.
* It first checks that the crash really happens with everything on, and that it stops with every mod off. If it does
  not stop, the cause is not a mod and the engine says that and stops.
* Before it names a culprit it runs a fix check (without the mod the crash is gone) and a repro check (with only that
  mod, plus what it needs, the crash returns). If the data only fit two mods that crash together, it finds that pair.
* A wrong tap can be undone. Nothing is concluded from a single contradiction.

Pure Python (no Qt) so every rule is unit tested.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

CONFIDENCE = 0.95      # a verdict needs this much belief, after the fix and repro checks
CLEARED = 0.05         # a mod whose belief fell below this share of where it started is cleared and left on
SLIP = 0.01            # chance a "crash" is caused by something we are not modelling
OUTSIDE = "__outside_mods__"
OUTSIDE_PRIOR = 0.03   # chance the cause is not a mod at all, before any test
PAIR_MASS = 0.15       # belief given to "two mods together" once single mods stop fitting
PAIR_LIMIT = 80        # pairs are searched among this many most suspicious mods
MAX_TESTS = 60
SURPRISE = 0.05        # a result this unlikely under a theory counts against it
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
    purpose: str                       # baseline, empty, search, fix, repro
    enabled: frozenset                 # exactly these units on, everything else off
    runs: int                          # launches to do before answering "fine"
    why: str
    expected: str = ""                 # for fix ("ok") and repro ("crash"), else ""
    under_test: tuple = ()             # units whose status this test is about


@dataclass(frozen=True)
class Verdict:
    kind: str                          # culprit, interaction, outside, unreproducible, undetermined
    keys: tuple
    confidence: float
    text: str


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def suspicion(unit: Unit, last_good: float | None, now: float | None) -> tuple[float, list]:
    """Weight and the plain reasons behind it. These only order the tests."""
    weight, reasons = 1.0, []
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


class Session:
    def __init__(self, units, *, last_good: float | None = None, now: float | None = None,
                 detect: float = 1.0, runs: int = 1):
        self.units = {u.key: u for u in units}
        self.pinned = frozenset(k for k, u in self.units.items() if u.pinned)
        self.detect = min(max(detect, 0.05), 0.99)
        self.runs = max(1, int(runs))
        self.weights, self.reasons = {}, {}
        for key, unit in self.units.items():
            if key in self.pinned:
                continue
            self.weights[key], self.reasons[key] = suspicion(unit, last_good, now)
        self.tests: list[tuple[Test, str]] = []
        self.unsure = 0
        self._requires = {k: tuple(r for r in u.requires if r in self.units) for k, u in self.units.items()}

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
        out, changed = {key}, True
        while changed:
            changed = False
            for k, needs in self._requires.items():
                if k not in out and any(n in out for n in needs):
                    out.add(k)
                    changed = True
        return frozenset(out)

    # ------------------------------------------------------------ belief
    def _hypotheses(self, pairs: bool) -> dict:
        """theory -> prior belief. A theory is one mod, two mods together, or "not a mod"."""
        keys = list(self.weights)
        total = sum(self.weights.values()) or 1.0
        mass = 1.0 - OUTSIDE_PRIOR - (PAIR_MASS if pairs else 0.0)
        theories = {OUTSIDE: OUTSIDE_PRIOR}
        for key in keys:
            theories[frozenset([key])] = mass * self.weights[key] / total
        if pairs:
            pool = set(keys)
            for test, result in self.tests:
                if result == "crash":
                    pool &= test.enabled
            top = sorted(pool, key=lambda k: (-self.weights[k], k))[:PAIR_LIMIT]
            norm = sum(self.weights[a] * self.weights[b] for i, a in enumerate(top) for b in top[i + 1:]) or 1.0
            for i, a in enumerate(top):
                for b in top[i + 1:]:
                    theories[frozenset([a, b])] = PAIR_MASS * self.weights[a] * self.weights[b] / norm
        return theories

    def _likelihood(self, theory, test: Test, result: str) -> float:
        q = 1.0 - (1.0 - self.detect) ** test.runs      # chance a crashing setup shows its crash in these runs
        inside = theory == OUTSIDE or theory <= test.enabled
        if result == "crash":
            return q if inside else SLIP
        return (1.0 - q) if inside else 1.0

    def _belief(self, pairs: bool):
        theories = self._hypotheses(pairs)
        surprises = {t: 0 for t in theories}
        post = dict(theories)
        for test, result in self.tests:
            for t in post:
                lik = self._likelihood(t, test, result)
                post[t] *= lik
                if lik < SURPRISE:
                    surprises[t] += 1
        total = sum(post.values())
        if total <= 0:
            return {t: 1.0 / len(post) for t in post}, surprises
        return {t: v / total for t, v in post.items()}, surprises

    def posterior(self):
        """(belief by theory, whether two-mod theories are in play, results each theory got badly wrong).

        Pairs join when no single mod fits the results. A theory that needed a very unlikely result to be true is
        never named as the cause, however large its share of the belief, because shares always add up to one."""
        single, surprises = self._belief(False)
        if any(s == 0 for t, s in surprises.items() if t != OUTSIDE) or not self.tests:
            return single, False, surprises
        both, surprises = self._belief(True)
        return both, True, surprises

    def suspects(self):
        """Mods ranked by how strongly the evidence points at them, with the reasons."""
        belief, _, _ = self.posterior()
        score = {k: 0.0 for k in self.weights}
        for theory, p in belief.items():
            if theory != OUTSIDE:
                for key in theory:
                    score[key] += p
        rows = [(self.units[k], min(1.0, score[k]), self.reasons[k]) for k in score]
        rows.sort(key=lambda r: (-r[1], r[0].name.lower()))
        return rows

    # ------------------------------------------------------------ planning
    def _test(self, purpose, enabled, why, expected="", under=(), runs=None) -> Test:
        return Test(purpose, self.closure(set(enabled) | set(self.pinned)), runs or self.runs, why, expected, tuple(under))

    def _proof_runs(self) -> int:
        """Launches so that a missed crash is under 1% likely: one 'fine' run proves little for a flaky crash."""
        miss = 1.0 - self.detect
        return max(self.runs, min(12, math.ceil(math.log(0.01) / math.log(miss)))) if miss > 0.0 else self.runs

    def _ran(self, purpose, enabled):
        return any(t.enabled == enabled for t, _ in self.tests)

    def _find(self, purpose):
        for test, result in self.tests:
            if test.purpose == purpose:
                return test, result
        return None

    def next_step(self):
        """The next Test to run, or the Verdict when the evidence is enough."""
        everything = frozenset(self.units)
        base = self._find("baseline")
        if base is None:
            return Test("baseline", everything, max(self.runs, 2) if self.detect < 0.95 else self.runs,
                        "Check the crash happens with every mod on. A search cannot start from a crash you cannot trigger.",
                        expected="crash")
        if base[1] == "ok":
            runs = base[0].runs
            miss = (1.0 - self.detect) ** runs
            return Verdict("unreproducible", (), 0.0,
                           f"The game did not crash in {_plural(runs, 'launch')} with every mod on, so there is nothing to "
                           f"narrow down yet. At your detection rate that happens {round(100 * miss)}% of the time even when "
                           "the crash is real. If it only crashes sometimes, use more runs per test and start again.")
        if self._find("empty") is None:
            return self._test("empty", (), "Check the crash stops with every mod off (only the always-on ones stay).",
                              expected="ok", runs=max(self.runs, 1 if self.detect >= 0.95 else 3))
        belief, pairs, surprises = self.posterior()
        empty = self._find("empty")
        direct = empty is not None and empty[1] == "crash" and belief[OUTSIDE] >= max(belief.values())
        if belief[OUTSIDE] >= CONFIDENCE or direct:
            kept = f" Only the always-on mods ({len(self.pinned)}) were left on, so one of those is also possible." if self.pinned else ""
            return Verdict("outside", (), belief[OUTSIDE],
                           "The game still crashes with the mods off, so the cause is not one of the mods you can turn off. "
                           "Check the game files, the graphics driver, and the crash report from Black Box." + kept)
        theory, p = max(((t, v) for t, v in belief.items() if t != OUTSIDE), key=lambda r: (r[1], sorted(r[0])))
        if p >= CONFIDENCE and surprises[theory] == 0:
            return self._verify(theory, p)
        if pairs and surprises[theory] > 0:
            return Verdict("undetermined", tuple(sorted(theory)), p,
                           "No one mod and no pair of mods fits every answer. Either an answer was tapped wrong "
                           "(undo it and repeat that test), the crash needs three or more mods together, or it "
                           "depends on your save. The closest suspects are listed, but nothing is proven.")
        if len(self.tests) >= MAX_TESTS:
            return Verdict("undetermined", tuple(sorted(theory)), p,
                           "The results do not point at one cause yet. The top suspects are listed; a crash that "
                           "depends on three or more mods together, or on your save, cannot be narrowed this way.")
        return self._search(belief)

    def _verify(self, theory, p):
        keys = sorted(theory)
        all_on = frozenset(self.units)
        for key in keys:
            off = self.dependents(key)
            enabled = self.closure(set(all_on - off) | set(self.pinned))
            if not self._ran("fix", enabled):
                names = ", ".join(self.units[k].name for k in sorted(off))
                return Test("fix", enabled, self._proof_runs(),
                            f"Fix check: turn off only {names}. If the crash is gone, it was one of them.",
                            expected="ok", under_test=(key,))
        alone = self.closure(set(keys) | set(self.pinned))
        if not self._ran("repro", alone):
            names = " + ".join(self.units[k].name for k in keys)
            return Test("repro", alone, self._proof_runs(),
                        f"Repro check: turn on only {names} (and what they need). The crash should come back.",
                        expected="crash", under_test=tuple(keys))
        kind = "culprit" if len(keys) == 1 else "interaction"
        names = " and ".join(self.units[k].name for k in keys)
        needed = sorted(self.closure(keys) - set(keys) - self.pinned)
        if kind == "culprit":
            text = f"{names} is the cause. The crash stopped without it and came back with it."
        else:
            text = f"{names} crash the game together. Either one on its own is fine."
        if needed:
            text += (" It cannot be switched on without " + ", ".join(self.units[k].name for k in needed) +
                     ", so the cause is it or something it needs; this test cannot separate them.")
        text += " This comes from your test results, not from guesses."
        if self.detect < 0.95:
            text += (f" Because the crash does not always show, this is about {round(100 * p)}% sure, not certain. "
                     "Running the fix check once more would raise it.")
        return Verdict(kind, tuple(keys), p, text)

    def _search(self, belief):
        q = 1.0 - (1.0 - self.detect) ** self.runs
        target = min(1.0, 0.5 / q)                     # share of belief to leave switched on
        start = self._hypotheses(False)
        start_marginal = {k: start[frozenset([k])] for k in self.weights}
        marginal = {k: 0.0 for k in self.weights}
        for theory, p in belief.items():
            if theory != OUTSIDE:
                for key in theory:
                    marginal[key] += p
        cleared = {k for k, v in marginal.items() if v < CLEARED * start_marginal[k]}
        base = self.closure(self.pinned | cleared)

        def mass(keys):
            return sum(p for t, p in belief.items() if t == OUTSIDE or t <= keys)

        def spread(keys):                               # how unsure we are of the outcome: higher is more informative
            x = min(max(mass(keys) * q, 1e-12), 1 - 1e-12)
            return -x * math.log(x) - (1 - x) * math.log(1 - x)

        order = sorted((k for k in marginal if k not in cleared), key=lambda k: (-marginal[k], k))
        enabled = set(base)
        current = mass(frozenset(enabled))
        skipped = []                                    # units that would overshoot the target
        for key in order:
            if key in enabled:
                continue
            grown = self.closure(enabled | {key})
            m = mass(grown)
            if m <= target + 1e-9:
                enabled, current = set(grown), m
                if current >= target * 0.97:
                    break
            else:
                skipped.append(grown)
        everyone = frozenset(self.units)
        options = [frozenset(enabled)]
        for grown in skipped:                           # one more unit past the target can be the better cut
            options.append(frozenset(enabled | grown))
        for key in order[:40]:                          # simple cuts around one suspect, for tiny or tangled lists
            options.append(self.closure(set(base) | {key}))
            options.append(everyone - self.dependents(key))
        seen = {t.enabled for t, _ in self.tests}
        fresh = []
        for keys in options:
            keys = self.closure(set(keys) | set(self.pinned))
            if keys != everyone and keys not in [k for k, _ in fresh]:
                fresh.append((keys, keys in seen))
        fresh.sort(key=lambda item: (item[1], -round(spread(item[0]), 9), len(item[0])))
        if not fresh or (fresh[0][1] and q >= 0.9):
            # Every setup that could tell the suspects apart has been run, or none can be built because the
            # suspects need each other. Repeating a reliable test teaches nothing, so say so and stop.
            names = ", ".join(self.units[k].name for k in order[:5])
            return Verdict("undetermined", tuple(order[:5]), max(marginal.values(), default=0.0),
                           "The mods still under suspicion need each other, so no setup can switch one on without "
                           "the others and the test cannot tell them apart. The cause is among: " + names + ".")
        pick = set(fresh[0][0])
        tested = tuple(sorted(k for k in pick if k in marginal and k not in cleared))
        crash_chance = mass(frozenset(pick)) * q
        return Test("search", self.closure(set(pick) | set(self.pinned)), self.runs,
                    f"Run with these {_plural(len(tested), 'suspect')} on and the rest off. About "
                    f"{round(100 * crash_chance)}% chance it crashes, so either answer tells us a lot.",
                    under_test=tested)

    # ------------------------------------------------------------ results
    def record(self, test: Test, result: str) -> None:
        """result: crash, ok, or unsure. Unsure adds no evidence; the same test will be asked again."""
        if result == "unsure":
            self.unsure += 1
            return
        if result not in ("crash", "ok"):
            raise ValueError("result must be crash, ok or unsure")
        self.tests.append((test, result))

    def undo(self) -> bool:
        """Take back the last answer (a wrong tap). Belief is rebuilt from the answers that remain."""
        if self.tests:
            self.tests.pop()
            return True
        return False

    def report(self) -> str:
        step = self.next_step()
        lines = ["Mod Bisect report", ""]
        for i, (test, result) in enumerate(self.tests, 1):
            lines.append(f"{i}. {test.purpose}: {len(test.enabled)} of {len(self.units)} mods on -> {result}")
        if isinstance(step, Verdict):
            lines += ["", step.text]
        lines += ["", "Only your test answers count as proof. The suspicion order is a starting point, not a finding."]
        return "\n".join(lines)
