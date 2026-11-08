import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gg_desktop import tools_data as data
from gg_desktop import tools_system as system
from gg_desktop.models import GameRecord


def game(name, size, source="Steam manifest", path="C:\\Games\\x"):
    return GameRecord(key=name, name=name, launcher="Steam", app_id=None, install_path=path, install_evidence="manifest",
                      size_bytes=size, size_source=source, last_played_at=None, last_played_source="", status="Installed",
                      capabilities=())


def mod(name, size, files=1, truncated=False):
    return SimpleNamespace(name=name, source="Steam game folder", apparent_bytes=size, file_count=files, truncated=truncated,
                           status="Unmatched Steam folder", path="C:\\Steam\\" + name, indicators=("mods",), advice="Review manually.")


class Registry(unittest.TestCase):
    def test_every_photo_tile_exists_once_in_six_categories(self):
        self.assertEqual(len(data.CATEGORIES), 6)
        keys = [t.key for t in data.all_tiles()]
        self.assertEqual(len(keys), 24)
        self.assertEqual(len(set(keys)), 24)
        self.assertTrue(all(len(c.tiles) == 4 for c in data.CATEGORIES))

    def test_tiles_are_go_run_or_unavailable_and_each_has_a_target_or_reason(self):
        tabs = {"Other Storage", "Game DNA", "Overview", "Captures", "Old Files", "Graveyard"}
        for t in data.all_tiles():
            self.assertIn(t.kind, {data.GO, data.RUN, data.OFF})
            if t.kind == data.GO:
                self.assertIn(t.target, tabs)
            elif t.kind == data.RUN:
                self.assertTrue(t.target)
            else:
                self.assertIn("does not change Windows settings", t.note)

    def test_things_game_grave_does_not_do_are_not_offered(self):
        off = {t.key for t in data.all_tiles() if t.kind == data.OFF}
        self.assertEqual(off, {"windows_cleanup", "game_optimizer", "memory_optimizer", "startup_manager",
                               "command_runner", "file_associations", "junction_manager"})

    def test_no_tile_text_claims_safety_or_freed_space(self):
        for t in data.all_tiles():
            text = (t.title + " " + t.note).casefold()
            self.assertNotIn("safe to", text)
            self.assertNotIn("freed", text)
            self.assertNotIn("&", t.title)

    def test_tabs_filter_categories_and_unknown_falls_back_to_all(self):
        self.assertEqual(len(data.categories_for("hub")), 6)
        self.assertEqual([c.key for c in data.categories_for("advanced")], ["utilities", "advanced"])
        self.assertEqual(len(data.categories_for("nonsense")), 6)
        for key, *_rest in data.TABS:
            self.assertTrue(data.categories_for(key))

    def test_quick_actions_and_kit_menu_cover_the_existing_kit_workflow(self):
        self.assertEqual(len(data.QUICK_ACTIONS), 5)
        self.assertEqual({k for k, _t, _h in data.KIT_ACTIONS},
                         {"create", "restore", "rehearse", "missing", "compare", "versions", "transfer"})


class Reports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def read(self, path):
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))

    def test_csv_guards_against_formulas(self):
        for bad in ("=1+1", "+cmd", "-2", "@SUM(A1)", "  =x"):
            self.assertTrue(data.csv_safe(bad).startswith("'"), bad)
        self.assertEqual(data.csv_safe("Portal 2"), "Portal 2")
        path = Path(self.tmp.name) / "g.csv"
        data.write_csv(path, ("a",), [("=HYPERLINK(\"x\")",)])
        self.assertEqual(self.read(path)[1][0], "'=HYPERLINK(\"x\")")

    def test_game_report_is_sorted_and_never_invents_a_size(self):
        rows = data.game_rows([game("Small", 10), game("Unknown", None), game("Big", 5000), game("Alpha", None)])
        self.assertEqual([r[0] for r in rows], ["Big", "Small", "Alpha", "Unknown"])
        unknown = rows[-1]
        self.assertEqual(unknown[2], "")
        self.assertEqual(unknown[3], "Not reported")
        path = Path(self.tmp.name) / "g.csv"
        self.assertEqual(data.write_csv(path, data.GAME_HEADER, rows), 4)
        table = self.read(path)
        self.assertEqual(table[0], list(data.GAME_HEADER))
        self.assertEqual(len(table), 5)

    def test_game_names_that_look_like_formulas_are_neutralised(self):
        rows = data.game_rows([game("=cmd|' /C calc'!A0", 1)])
        path = Path(self.tmp.name) / "g.csv"
        data.write_csv(path, data.GAME_HEADER, rows)
        self.assertTrue(self.read(path)[1][0].startswith("'="))

    def test_mod_report_marks_truncated_counts(self):
        rows = data.mod_rows([mod("small", 5), mod("big", 900, files=7, truncated=True)])
        self.assertEqual([r[0] for r in rows], ["big", "small"])
        self.assertEqual(rows[0][3], "7+")
        self.assertEqual(rows[1][3], 1)

    def test_system_report_states_only_what_the_scan_reported(self):
        inv = SimpleNamespace(games=[game("A", 2048), game("B", None)], mods=[mod("m", 1)], files=[], screenshots=[1],
                              recordings=[], saves=[], graveyard=[], scanned_at="", warnings=["Epic unreadable"],
                              file_scan_root="")
        text = data.system_report_text(inventory=inv, system=[("Memory in use", "Unavailable")],
                                       settings={"steam_extra_roots": ["D:\\Steam"]}, generated="2026-11-08 10:00", version="9")
        self.assertIn("No scan has finished in this session", text)
        self.assertIn("Games found: 2 (1 with a reported size)", text)
        self.assertIn("Reported game size total: 2.0 KB", text)
        self.assertIn("Epic unreadable", text)
        self.assertIn("D:\\Steam", text)
        self.assertIn("Memory in use: Unavailable", text)
        self.assertIn("do not mean anything is safe to remove", text)

    def test_text_report_round_trips(self):
        path = Path(self.tmp.name) / "r.txt"
        self.assertEqual(data.write_text(path, "a\nb\n"), 2)
        self.assertEqual(path.read_bytes(), b"a\r\nb\r\n")


class Hash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "f.bin"
        self.blob = b"game grave" * 400000
        self.path.write_bytes(self.blob)

    def test_matches_hashlib_and_reports_progress_to_100(self):
        seen = []
        digest = data.sha256_file(self.path, progress=lambda d, t: seen.append((d, t)))
        self.assertEqual(digest, hashlib.sha256(self.blob).hexdigest())
        self.assertEqual(seen[-1][0], seen[-1][1])
        self.assertGreater(len(seen), 1)

    def test_empty_file_hashes(self):
        empty = Path(self.tmp.name) / "e"
        empty.write_bytes(b"")
        self.assertEqual(data.sha256_file(empty), hashlib.sha256(b"").hexdigest())

    def test_cancel_stops_without_a_result(self):
        with self.assertRaises(InterruptedError):
            data.sha256_file(self.path, canceled=lambda: True)

    def test_missing_file_raises_os_error(self):
        with self.assertRaises(OSError):
            data.sha256_file(Path(self.tmp.name) / "nope")

    def test_file_is_not_modified(self):
        before = self.path.read_bytes()
        data.sha256_file(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_compare_states(self):
        actual = hashlib.sha256(b"x").hexdigest()
        self.assertEqual(data.compare_hash(actual, "")[0], "empty")
        self.assertEqual(data.compare_hash(actual, "   ")[0], "empty")
        self.assertEqual(data.compare_hash(actual, "abc123")[0], "invalid")
        self.assertEqual(data.compare_hash(actual, actual)[0], "match")
        self.assertEqual(data.compare_hash(actual, actual.upper())[0], "match")
        self.assertEqual(data.compare_hash(actual, "0" * 64)[0], "different")

    def test_compare_accepts_common_paste_shapes(self):
        actual = hashlib.sha256(b"x").hexdigest()
        self.assertEqual(data.compare_hash(actual, actual + "  setup.exe")[0], "match")
        self.assertEqual(data.compare_hash(actual, actual + " *setup.exe\n")[0], "match")
        spaced = " ".join(actual[i:i + 8] for i in range(0, 64, 8))
        self.assertEqual(data.compare_hash(actual, spaced)[0], "match")
        self.assertEqual(data.compare_hash(actual, actual[:-1])[0], "invalid")

    def test_a_match_message_never_says_the_file_is_safe(self):
        actual = hashlib.sha256(b"x").hexdigest()
        message = data.compare_hash(actual, actual)[1]
        self.assertNotIn("safe", message.casefold())
        self.assertNotIn("virus", message.casefold())


class Tasks(unittest.TestCase):
    def test_nothing_is_listed_when_nothing_runs(self):
        self.assertEqual(data.build_tasks(), [])

    def test_each_running_job_is_listed_honestly(self):
        tasks = data.build_tasks(scanning=True, scan_percent=250, scan_stage="Mod Radar", cleaning=True,
                                 hash_name="a.iso", hash_percent=-5)
        self.assertEqual([t.kind for t in tasks], ["scan", "work", "hash"])
        self.assertEqual(tasks[0].percent, 100)
        self.assertTrue(tasks[0].cancelable)
        self.assertIsNone(tasks[1].percent)
        self.assertFalse(tasks[1].cancelable)
        self.assertEqual(tasks[2].percent, 0)
        self.assertIn("a.iso", tasks[2].title)

    def test_log_is_newest_first_limited_and_tolerates_junk(self):
        events = [{"kind": "Scan completed", "date": "2026-11-01T10:00:00", "details": "x"},
                  {"kind": "Manual recycled", "date": "2026-11-03T10:00:00", "details": "a.txt"},
                  {"kind": "Restored from Recycle Bin", "date": "2026-11-02T10:00:00", "details": "b.txt"},
                  "junk", None]
        lines = data.log_lines(events, 2)
        self.assertEqual([l[0] for l in lines], ["File moved to Recycle Bin", "File restored"])
        self.assertEqual(data.log_lines([], 3), [])
        self.assertEqual(data.log_lines(events, 0), [])


class Health(unittest.TestCase):
    def test_percent_is_clamped_and_bad_values_are_unavailable(self):
        self.assertEqual(system.clamp_percent(46.4), 46)
        self.assertEqual(system.clamp_percent(-3), 0)
        self.assertEqual(system.clamp_percent(400), 100)
        for bad in (None, "x", float("nan")):
            self.assertIsNone(system.clamp_percent(bad))

    def test_storage_reading_is_a_real_percentage_or_unavailable(self):
        value = system.storage_percent(tempfile.gettempdir())
        self.assertTrue(value is None or 0 <= value <= 100)
        self.assertIsNone(system.storage_percent(Path(tempfile.gettempdir()) / "definitely" / "not" / "here"))
        self.assertEqual(system.storage_text(Path(tempfile.gettempdir()) / "definitely" / "not" / "here"), "Unavailable")

    def test_cpu_meter_needs_two_samples_and_uses_deltas(self):
        feed = iter([(100, 1000), (150, 1200), (150, 1200), (400, 1300)])
        meter = system.CpuMeter(lambda: next(feed))
        self.assertIsNone(meter.sample())
        self.assertTrue(meter.waiting)
        self.assertEqual(meter.sample(), 75)          # 200 total, 50 idle
        self.assertFalse(meter.waiting)
        self.assertIsNone(meter.sample())             # no time passed
        self.assertEqual(meter.sample(), 0)           # idle moved more than total: clamped, never negative

    def test_cpu_meter_survives_a_reader_that_fails_or_is_absent(self):
        def boom():
            raise OSError("no")
        self.assertIsNone(system.CpuMeter(boom).sample())
        self.assertIsNone(system.CpuMeter(lambda: None).sample())

    def test_report_lines_label_unavailable_readings(self):
        lines = dict(system.report_lines(None))
        self.assertEqual(lines["CPU in use"], "Unavailable")
        self.assertIn("Storage in use", lines)


if __name__ == "__main__":
    unittest.main()
