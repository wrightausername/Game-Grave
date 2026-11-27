"""REAL end-to-end check of the optional local AI model on the Windows CI machine.

Downloads the Small model from Hugging Face and llama.cpp's engine from GitHub through the same verified installer the
app uses, starts llama-server the same way (graphics build first, CPU build if it won't start), asks real questions built
from sample facts, and checks the replies keep Game Grave's rules. Then removes everything it downloaded.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

# Model replies can hold any character; the Windows CI console is cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gg_desktop import assistant_engine as engine  # noqa: E402
from gg_desktop import local_ai_core as ai  # noqa: E402
from gg_desktop import local_ai_prompt as prompt  # noqa: E402
from tests.test_assistant import facts  # noqa: E402


def main():
    base = Path(tempfile.mkdtemp()) / "ai"
    t = time.monotonic()
    shown = {"pct": -10}

    def report(done, total):
        pct = int(done * 100 / total) if total else 0
        if pct >= shown["pct"] + 10:
            shown["pct"] = pct
            print(f"  {pct}% of {total / ai.GB:.2f} GB", flush=True)
    for key in ("medium", "large", "xl"):  # the other two sizes resolve to one published, fingerprinted file
        remote = ai.resolve_model(key)
        print(f"{key}: {remote.name} {remote.size / ai.GB:.2f} GB sha256 {remote.sha256[:12]}…")
        assert remote.size > 0.5 * ai.BY_KEY[key].approx_bytes
        sight = ai.resolve_vision(key)
        print(f"  image file: {sight.name if sight else 'none'}")
    print("Engine:", ai.RUNTIMES["vulkan"])
    ai.install_runtime("vulkan", report, base=base)
    shown["pct"] = -10
    print("Model: Small,", ai.BY_KEY["small"].repo)
    path = ai.install_model("small", report, base=base)
    print(f"Downloaded and SHA-256 verified in {time.monotonic() - t:.0f}s: {path.name} {path.stat().st_size / ai.GB:.2f} GB")
    vision = ai.vision_path("small", base)
    print("Image file (reads screenshots):", f"{vision.name} {vision.stat().st_size / ai.GB:.2f} GB" if vision.is_file()
          else "none in the repo")

    server = ai.LocalServer("small", base)
    t = time.monotonic()
    kind = ai.start_best(server, base)
    print(f"llama-server started with the {kind} build in {time.monotonic() - t:.0f}s on port {server.port}")
    f = facts()
    good = 0
    seen_picture = None
    try:
        # The Gravekeeper itself: a casual opener answered in its own voice, through the app's own turn.
        from gg_desktop import gravekeeper
        sys.path.insert(0, str(ROOT / "tools"))
        import local_ai_bench as bench
        ctx = bench.context()
        t = time.monotonic()
        out = gravekeeper.turn(server, "hey, what should I play tonight?", ctx.facts, (), ctx)
        print(f"\nGravekeeper ({time.monotonic() - t:.0f}s): {out['text'][:400]}  [looked: {out['looked']}]")
        assert out["text"], "the Gravekeeper should answer a casual question"
        # A screenshot of an error: drawn here, read by the model through its image file.
        if server.vision:
            import base64
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
            from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
            app = QGuiApplication.instance() or QGuiApplication([])
            picture = QImage(640, 200, QImage.Format_RGB32)
            picture.fill(QColor("white"))
            painter = QPainter(picture)
            painter.setPen(QColor("black"))
            painter.setFont(QFont("Segoe UI", 22))
            painter.drawText(picture.rect(), Qt.AlignCenter, "The application was unable to start\ncorrectly (0xc0000142)")
            painter.end()
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.WriteOnly)
            picture.save(buffer, "PNG")
            uri = "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")
            t = time.monotonic()
            ctx.effects = []
            out = gravekeeper.turn(server, "what does this error mean?", ctx.facts, (), ctx, image=uri)
            seen_picture = "0xc0000142" in out["text"].casefold() or "unable to start" in out["text"].casefold()
            print(f"Screenshot ({time.monotonic() - t:.0f}s): {out['text'][:400]}  read the code: {seen_picture}")
            del app
        for q in ("how many games do i have?", "which game should i uninstall to free up space?",
                  "when did i last play cyberpunk?", "what would you recommend adding to game grave?"):
            base_answer = engine.answer(q, f)
            t = time.monotonic()
            raw = server.chat(prompt.build_messages(q, base_answer, f), max_tokens=300, timeout=600, think=False)
            text = prompt.clean_reply(raw)
            print(f"\nQ: {q}  ({time.monotonic() - t:.0f}s)\nA: {text or '[rejected by the rules; built-in answer shown] ' + raw[:300]}")
            if text:
                good += 1
        # The question bench: real questions through lookups, plans and the answer check, as the app runs them.
        sys.path.insert(0, str(ROOT / "tools"))
        import local_ai_bench as bench
        print(f"\nQuestion bench ({len(bench.CASES)} questions, Small model, lookups on):", flush=True)
        import os
        minutes = float(os.environ.get("GG_BENCH_MINUTES", "20"))
        # Each CI run starts at a different question, so every case gets asked over a few runs.
        start = (int(os.environ.get("GITHUB_RUN_NUMBER", "0") or 0) * 15) % len(bench.CASES)
        cases = bench.CASES[start:] + bench.CASES[:start]
        print(f"Starting at question {start + 1}.")
        passed, asked, misses = bench.run(server, think=False, budget_s=minutes * 60, cases=cases,
                                          log=lambda line: print(line, flush=True))
        score = passed / asked if asked else 0
        print(f"\nBench: {passed} of {asked} passed ({score:.0%}).")
        for question, why in misses:
            print(f"  miss: {question}: {'; '.join(why)}")
    finally:
        server.stop()
    assert not server.running
    removed = ai.remove_all(base)
    assert not base.exists()
    print(f"\nRemoved {removed / ai.GB:.2f} GB.")
    assert good >= 3, "The local model should answer most questions within the rules"
    if seen_picture is False:
        print("NOTE: the Small model didn't repeat the error code from the screenshot; Large reads it far better.")
    assert asked >= 10, "the bench should get through at least 10 questions in its time budget"
    assert score >= 0.5, f"The Small model passed only {score:.0%} of the bench; see the misses above"
    print("PASS: the local AI model downloads verified, runs on this PC, answers within the rules and removes cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
