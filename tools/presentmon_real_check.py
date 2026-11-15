"""REAL check on the Windows build machine: download the pinned Intel PresentMon exactly as Make it run better does
(GitHub only, SHA-256 checked), confirm it runs, then delete it."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from gg_desktop import local_ai_core as ai
    from gg_desktop import tune_core as tc
    with tempfile.TemporaryDirectory(prefix="GG-presentmon-") as temp:
        dest = Path(temp) / tc.PRESENTMON_NAME
        ai.download(tc.remote(), dest)
        assert dest.is_file() and dest.stat().st_size > 100_000, dest
        run = subprocess.run([str(dest), "--help"], capture_output=True, text=True, timeout=60)
        words = (run.stdout + run.stderr).casefold()
        assert "process_id" in words and "output_file" in words and "timed" in words, words[:600]
    print(f"PASS: PresentMon {tc.PRESENTMON_VERSION} downloads from GitHub, matches its pinned SHA-256, runs, and offers "
          "the options Make it run better uses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
