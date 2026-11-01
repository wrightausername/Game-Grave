"""Local drive storage trends from bounded OS disk counters only."""
from __future__ import annotations

from collections import namedtuple
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gg_desktop.storage_watch import (
    sample_on_ready_room_open, describe_storage_history, load_history,
)


class StorageWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = SimpleNamespace(install_path=str(self.root / "game"))
        patcher = patch("gg_desktop.storage_watch.config_dir", return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_sampling_or_settings_write_during_detected_gameplay(self):
        calls = []
        result = sample_on_ready_room_open(
            [self.game],
            active=SimpleNamespace(active=lambda: True),
            disk_usage=lambda *_: calls.append(1),
            clock=lambda: 100000,
        )
        self.assertEqual(result, {})
        self.assertEqual(calls, [])
        self.assertEqual(load_history(), {})

    def test_six_hour_sample_cadence_and_change_description(self):
        Usage = namedtuple("Usage", "total used free")
        now = [100000]
        value = [1000]
        def usage(_):
            return Usage(total=2000, used=2000-value[0], free=value[0])
        active = SimpleNamespace(active=lambda: False)
        a = sample_on_ready_room_open(
            [self.game], active=active, disk_usage=usage, clock=lambda: now[0])
        self.assertEqual(len(next(iter(a.values()))), 1)
        now[0] += 100
        value[0] = 700
        b = sample_on_ready_room_open(
            [self.game], active=active, disk_usage=usage, clock=lambda: now[0])
        self.assertEqual(len(next(iter(b.values()))), 1)
        now[0] += 6 * 3600
        latest = sample_on_ready_room_open(
            [self.game], active=active, disk_usage=usage, clock=lambda: now[0])
        self.assertEqual(len(next(iter(latest.values()))), 2)
        self.assertIn("less free", describe_storage_history(latest)[0])


if __name__ == "__main__":
    unittest.main()
