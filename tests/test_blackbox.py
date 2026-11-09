import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from gg_desktop import blackbox_core as bb


def event(exe, path, when="2026-11-08T20:15:30.1234567Z", module="d3d11.dll", code="c0000005", offset="000000000012ab34"):
    return (f'<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><EventID>1000</EventID>'
            f'<TimeCreated SystemTime="{when}"/></System><EventData><Data>{exe}</Data><Data>1.0</Data><Data>0</Data>'
            f'<Data>{module}</Data><Data>1.0</Data><Data>0</Data><Data>{code}</Data><Data>{offset}</Data>'
            f'<Data>1234</Data><Data>0</Data><Data>{path}</Data></EventData></Event>')


class BlackBoxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "Game"
        (self.game / "bin").mkdir(parents=True)
        (self.game / "bin" / "game.exe").write_bytes(b"x")

    def test_parse_reads_real_fields_and_skips_junk(self):
        xml = event("game.exe", "C:\\g\\game.exe") + "<Event><System/></Event>"
        crashes = bb.parse_events(xml)
        self.assertEqual(len(crashes), 1)
        self.assertEqual((crashes[0].exe, crashes[0].module, crashes[0].code), ("game.exe", "d3d11.dll", "c0000005"))
        self.assertEqual(bb.parse_events("not xml at all <<<"), [])
        self.assertEqual(bb.parse_events(""), [])

    def test_only_this_games_crashes_are_kept(self):
        xml = event("game.exe", "D:\\elsewhere\\game.exe") + event("chrome.exe", "C:\\chrome\\chrome.exe") \
            + event("other.exe", str(self.game / "bin" / "other.exe"))
        kept = bb.crashes_for(bb.parse_events(xml), self.game)
        self.assertEqual(sorted(c.exe for c in kept), ["game.exe", "other.exe"])

    def test_report_collects_logs_changes_and_grave_lines(self):
        now = datetime(2026, 11, 9, 12, 0)
        (self.game / "crash").mkdir()
        dump = self.game / "crash" / "report.dmp"
        dump.write_bytes(b"d" * 2048)
        changed = self.game / "bin" / "patch.pak"
        changed.write_bytes(b"p")
        old = self.game / "bin" / "ancient.pak"
        old.write_bytes(b"o")
        for f, when in ((dump, now - timedelta(days=1)), (changed, now - timedelta(days=3)), (old, now - timedelta(days=60))):
            os.utime(f, (when.timestamp(), when.timestamp()))
        activity = [{"kind": "soulbind_apply", "details": "Game: Invert vertical look 0 to 1", "date": "2026-11-07T10:00:00"},
                    {"kind": "x", "details": "unrelated", "date": "2026-11-07T10:00:00"}]
        report = bb.build_report("Game", self.game, events_xml=event("game.exe", str(self.game / "bin" / "game.exe")),
                                 activity=activity, now=now)
        self.assertEqual(len(report.crashes), 1)
        self.assertEqual([f.path for f in report.logs], [str(Path("crash") / "report.dmp")])
        self.assertEqual([f.path for f in report.changed], [str(Path("bin") / "patch.pak")])
        self.assertEqual(len(report.grave), 1)
        text = bb.render(report)
        self.assertIn("does not say why the game crashed", text)
        self.assertIn("cannot tell when the last good launch was", text)

    def test_no_crash_says_so_and_event_log_failure_is_stated(self):
        report = bb.build_report("Game", self.game, events_xml="", activity=[], now=datetime(2026, 11, 9))
        self.assertIn("None found in the Windows Application log", bb.render(report))
        with patch("gg_desktop.blackbox_core.query_events", side_effect=OSError("The Windows event log could not be read on this PC.")):
            report = bb.build_report("Game", self.game, activity=[], now=datetime(2026, 11, 9))
        self.assertFalse(report.event_log_ok)
        self.assertIn("could not be read", bb.render(report))

    def test_user_name_is_hidden_and_report_saved(self):
        self.assertEqual(bb.hide_user("C:\\Users\\Alex Wright\\Games\\x"), "C:\\Users\\<user>\\Games\\x")
        report = bb.Report("A: B/C", "C:\\Users\\alex\\g", datetime(2026, 11, 9, 1, 2, 3))
        path = bb.save_report(report, root=self.root / "out")
        self.assertTrue(path.name.startswith("A-B-C-20261109-010203"))
        self.assertNotIn("alex", path.read_text())

    def test_large_folder_scan_is_bounded(self):
        with patch.object(bb, "MAX_SCAN_FILES", 5):
            for i in range(20):
                (self.game / f"f{i}.bin").write_bytes(b"x")
            report = bb.build_report("Game", self.game, events_xml="", activity=[], now=datetime.now())
        self.assertTrue(report.scan_limited)


if __name__ == "__main__":
    unittest.main()
