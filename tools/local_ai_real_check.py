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
    for key in ("medium", "large"):  # the other two sizes resolve to one published, fingerprinted file
        remote = ai.resolve_model(key)
        print(f"{key}: {remote.name} {remote.size / ai.GB:.2f} GB sha256 {remote.sha256[:12]}…")
        assert remote.size > 0.5 * ai.BY_KEY[key].approx_bytes
    print("Engine:", ai.RUNTIMES["vulkan"])
    ai.install_runtime("vulkan", report, base=base)
    shown["pct"] = -10
    print("Model: Small,", ai.BY_KEY["small"].repo)
    path = ai.install_model("small", report, base=base)
    print(f"Downloaded and SHA-256 verified in {time.monotonic() - t:.0f}s: {path.name} {path.stat().st_size / ai.GB:.2f} GB")

    server = ai.LocalServer("small", base)
    t = time.monotonic()
    kind = ai.start_best(server, base)
    print(f"llama-server started with the {kind} build in {time.monotonic() - t:.0f}s on port {server.port}")
    f = facts()
    good = 0
    try:
        for q in ("how many games do i have?", "which game should i uninstall to free up space?",
                  "when did i last play cyberpunk?", "what would you recommend adding to game grave?"):
            base_answer = engine.answer(q, f)
            t = time.monotonic()
            raw = server.chat(prompt.build_messages(q, base_answer, f), max_tokens=300, timeout=600)
            text = prompt.clean_reply(raw)
            print(f"\nQ: {q}  ({time.monotonic() - t:.0f}s)\nA: {text or '[rejected by the rules; built-in answer shown] ' + raw[:300]}")
            if text:
                good += 1
    finally:
        server.stop()
    assert not server.running
    removed = ai.remove_all(base)
    assert not base.exists()
    print(f"\nRemoved {removed / ai.GB:.2f} GB.")
    assert good >= 3, "The local model should answer most questions within the rules"
    print("PASS: the local AI model downloads verified, runs on this PC, answers within the rules and removes cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
