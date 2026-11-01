"""Manual FPS benchmark history; no game-process instrumentation."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
import tempfile
from pathlib import Path
import unittest

from gg_desktop.performance_watch import (
    add_benchmark, read_benchmarks, benchmark_summary,
)


class PerformanceWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = SimpleNamespace(
            name="Benchmark Example", launcher="Steam",
            install_path=str(self.root / "games" / "Example"))
        patcher = patch("gg_desktop.performance_watch.config_dir", return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_manual_entries_are_stored_and_compared(self):
        self.assertEqual(read_benchmarks(self.game), [])
        add_benchmark(self.game, 80, 59, "ultra settings")
        rows = add_benchmark(self.game, 95, 70, "ultra settings, new driver")
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(read_benchmarks(self.game)), 2)
        summary = benchmark_summary(rows)
        self.assertIn("+15.0 average FPS", summary)
        self.assertIn("+11.0 1% low", summary)

    def test_invalid_or_deceptive_values_cannot_be_saved(self):
        for avg, low in ((0, 0), (90, 120), (float("nan"), 10),
                         (2001, 50), (95, -1)):
            with self.subTest(average=avg, low=low):
                with self.assertRaises(ValueError):
                    add_benchmark(self.game, avg, low)
        self.assertFalse(read_benchmarks(self.game))

    def test_other_game_never_inherits_benchmark_history(self):
        add_benchmark(self.game, 120, 90)
        other = SimpleNamespace(name="Benchmark Example", launcher="Steam",
                                install_path=str(self.root / "other"))
        self.assertEqual(read_benchmarks(other), [])


if __name__ == "__main__":
    unittest.main()
