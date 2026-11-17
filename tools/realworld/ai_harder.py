"""The Gravekeeper, pushed harder: the Medium model, the whole question bench, real multi-turn conversations, and how
long a person waits for the first answer.

Downloads the engine and the Medium model through the app's own verified installer, starts it the way the app does,
and talks to it through the app's own Gravekeeper turn. Conversations carry their earlier turns the way the chat page
does, so follow-ups like "how big is it?" must use what was said before. Everything downloaded is removed at the end.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

# Each conversation: (question, words one of which the answer must hold, words it must not hold)
CONVERSATIONS = {
    "biggest then follow-up": [
        ("which of my games takes the most space?", ("Starfield",), ()),
        ("how big is it?", ("120",), ()),
        ("and when did I last play it?", ("3 days", "three days", "days ago"), ()),
    ],
    "game then pronoun": [
        ("tell me about cyberpunk", ("Cyberpunk",), ()),
        ("has it crashed lately?", ("crash", "nvwgf2umx", "graphics driver", "three", "3"), ()),
        ("what should I try first to fix that?", ("driver", "update", "Crash Doctor", "mod"), ("format", "reinstall windows")),
    ],
    "change of mind": [
        ("I want to free up space", ("space", "GB", "Starfield", "Cyberpunk", "old files"), ()),
        ("actually forget that, what should I play tonight?", ("Cyberpunk", "Hades", "Starfield", "play"), ("delete", "uninstall")),
    ],
    "casual chat": [
        ("hey how's it going", ("",), ("as an ai language model",)),
        ("what can you do for me?", ("game", "space", "mod", "crash"), ()),
        ("cool thanks", ("",), ("as an ai language model",)),
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_ci_temp/realworld"))
    parser.add_argument("--model", default="medium")
    parser.add_argument("--bench-minutes", type=float, default=60)
    args = parser.parse_args()
    rw.isolate("GG-rw-ai-")
    rep = rw.Report(f"ai-{args.model}", args.output)
    from gg_desktop import gravekeeper
    from gg_desktop import local_ai_core as ai
    sys.path.insert(0, str(rw.ROOT / "tools"))
    import local_ai_bench as bench

    base = Path(tempfile.mkdtemp()) / "ai"
    t = time.monotonic()
    ai.install_runtime("vulkan", lambda *_: None, base=base)
    path = ai.install_model(args.model, lambda *_: None, base=base)
    rep.note("downloaded and verified", model=path.name, gb=round(path.stat().st_size / ai.GB, 2),
             seconds=round(time.monotonic() - t))
    server = ai.LocalServer(args.model, base)
    try:
        t = time.monotonic()
        kind = ai.start_best(server, base)
        started_in = time.monotonic() - t
        ctx = bench.context()
        t = time.monotonic()
        first = gravekeeper.turn(server, "hi! what's taking up space on my pc?", ctx.facts, (), ctx)
        first_answer = time.monotonic() - t
        rep.check("the first answer arrives within 60 seconds of asking (model already started)", first_answer < 60
                  and bool(first["text"]), seconds=round(first_answer, 1), engine=kind, start_seconds=round(started_in, 1),
                  answer=first["text"][:300])
        rep.check("from switching the assistant on to the first answer: under 3 minutes",
                  started_in + first_answer < 180, seconds=round(started_in + first_answer, 1))

        for name, steps in CONVERSATIONS.items():
            ctx = bench.context()
            history, ok, said, times = [], True, [], []
            for question, want, never in steps:
                ctx.effects = []
                t = time.monotonic()
                try:
                    out = gravekeeper.turn(server, question, ctx.facts, tuple(history), ctx)
                    text = out["text"] or ""
                    if out.get("plan") is not None and not text:
                        text = "[plan] " + ", ".join(bench.jobs_of(out["plan"].steps))
                except Exception as exc:
                    text = f"[error {exc}]"
                times.append(round(time.monotonic() - t, 1))
                hit = any(w.casefold() in text.casefold() for w in want) and bool(text.strip())
                bad = [w for w in never if w.casefold() in text.casefold()]
                ok = ok and hit and not bad
                said.append({"q": question, "a": text[:260], "followed": hit, "said_wrong": bad})
                history.append((question, text))
            rep.check(f"conversation: {name}", ok, turns=said, seconds=times)

        passed, asked, misses = bench.run(server, think=False, budget_s=args.bench_minutes * 60,
                                          log=lambda line: print(line, flush=True))
        score = passed / asked if asked else 0
        rep.check(f"the question bench on {args.model}: at least 85% right", score >= 0.85 and asked >= 20,
                  passed=passed, asked=asked, score=f"{score:.0%}", misses=misses[:20])
    finally:
        server.stop()
        ai.remove_all(base)
    return rep.finish()


if __name__ == "__main__":
    raise SystemExit(main())
