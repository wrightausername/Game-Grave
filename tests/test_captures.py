"""Captures: read-only discovery, honest ownership, analysis, tags, filters and verified removal."""
from __future__ import annotations

from pathlib import Path
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from gg_desktop import captures_actions as actions
from gg_desktop import captures_analysis as analysis
from gg_desktop import captures_data as data
from gg_desktop import captures_insight as insight
from gg_desktop import captures_state as state

DAY = 86400


def write(path, payload=b"x" * 100, age_days=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    moment = time.time() - age_days * DAY
    os.utime(path, (moment, moment))
    return path


def picture(path, color=(200, 30, 30), size=(64, 48), age_days=0, noise=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size)
    pixels = image.load()
    for x in range(size[0]):
        for y in range(size[1]):
            pixels[x, y] = (min(255, color[0] + x * 2 + noise), min(255, color[1] + y * 2), color[2])
    image.save(path)
    moment = time.time() - age_days * DAY
    os.utime(path, (moment, moment))
    return path


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="GG-captures-")
        self.root = Path(self.temp.name)
        self.home = self.root / "Home"
        self.steam = self.root / "Steam"
        self.home.mkdir()
        self.patches = [patch("gg_desktop.captures_data.safe_scan_root", lambda p: Path(p).is_dir()),
                        patch("recordings.safe_scan_root", lambda p: Path(p).is_dir())]
        for p in self.patches:
            p.start()
        self.game = SimpleNamespace(app_id="1091500", name="Cyberpunk 2077", library=str(self.steam))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def scan(self, **settings):
        return data.discover(settings, games=[self.game], steam_roots=[self.steam], home=self.home)


class DiscoveryTests(Fixture):
    def test_lists_everything_in_known_folders_not_only_old_files(self):
        picture(self.home / "Videos" / "Captures" / "new.png")
        picture(self.home / "Pictures" / "Game Screenshots" / "sub" / "old.jpg", age_days=900)
        write(self.home / "Videos" / "Captures" / "Cyberpunk 2077 2026_01_01.mp4", b"v" * 5000)
        write(self.home / "Videos" / "holiday.mp4")  # not hinted: not a capture
        write(self.home / "Pictures" / "Game Screenshots" / "notes.txt")
        report = self.scan()
        names = {c.name: c.kind for c in report.captures}
        self.assertEqual(names, {"new.png": "Screenshots", "old.jpg": "Screenshots", "Cyberpunk 2077 2026_01_01.mp4": "Recordings"})
        self.assertTrue(all(isinstance(c.size, int) and c.old_file.path == c.path for c in report.captures))

    def test_steam_ownership_needs_the_app_id_path(self):
        shot = picture(self.steam / "userdata" / "123" / "760" / "remote" / "1091500" / "screenshots" / "a.png")
        other = picture(self.steam / "userdata" / "123" / "760" / "remote" / "42" / "screenshots" / "b.png")
        picture(self.steam / "userdata" / "123" / "760" / "remote" / "42" / "screenshots" / "thumbnails" / "t.png")
        report = self.scan()
        found = {c.name: c for c in report.captures}
        self.assertEqual(set(found), {"a.png", "b.png"})
        self.assertEqual((found["a.png"].game, found["a.png"].verified), ("Cyberpunk 2077", True))
        self.assertEqual((found["b.png"].game, found["b.png"].verified), ("Steam app 42", False))
        self.assertIn("No installed game", found["b.png"].source)

    def test_folder_name_match_is_labeled_unproven(self):
        picture(self.home / "Pictures" / "Game Screenshots" / "Cyberpunk 2077" / "x.png")
        picture(self.home / "Pictures" / "Game Screenshots" / "Random" / "y.png")
        found = {c.name: c for c in self.scan().captures}
        self.assertEqual(found["x.png"].game, "Cyberpunk 2077")
        self.assertFalse(found["x.png"].verified)
        self.assertIn("not proof", found["x.png"].source)
        self.assertEqual(found["y.png"].game, data.UNVERIFIED)

    def test_user_added_folders_and_limits(self):
        extra = self.root / "MyShots"
        picture(extra / "a.png")
        picture(extra / "b.png")
        report = self.scan(screenshot_roots=[str(extra)])
        self.assertEqual({c.name for c in report.captures}, {"a.png", "b.png"})
        limited = data.discover({"screenshot_roots": [str(extra)]}, steam_roots=[], home=self.home, limit=1)
        self.assertTrue(limited.partial and len(limited.captures) == 1)

    def test_canceling_stops_the_scan(self):
        picture(self.home / "Videos" / "Captures" / "a.png")
        with self.assertRaises(InterruptedError):
            data.discover({}, steam_roots=[], home=self.home, canceled=lambda: True)

    def test_scanning_changes_nothing(self):
        shot = picture(self.home / "Videos" / "Captures" / "a.png")
        before = (shot.read_bytes(), shot.stat().st_mtime_ns)
        self.scan()
        self.assertEqual(before, (shot.read_bytes(), shot.stat().st_mtime_ns))

    def test_real_safe_scan_root_refuses_home_and_drive_root(self):
        self.patches[0].stop()
        try:
            self.assertFalse(data.safe_scan_root(Path.home()))
            self.assertFalse(data.safe_scan_root(Path(Path.home().anchor)))
        finally:
            self.patches[0].start()

    def test_merge_prefers_scan_results(self):
        shot = picture(self.home / "Videos" / "Captures" / "a.png")
        scanned = self.scan().captures
        inv = SimpleNamespace(steam=[self.game], screenshots=[scanned[0].old_file], recordings=[])
        merged = data.merge(scanned, data.from_inventory(inv))
        self.assertEqual(len(merged), 1)


class HeaderTests(Fixture):
    def test_dimensions_come_from_headers(self):
        picture(self.home / "Videos" / "Captures" / "a.png", size=(80, 60))
        write(self.home / "Videos" / "Captures" / "broken.png", b"not an image")
        captures = self.scan().captures
        data.read_dimensions(captures)
        found = {c.name: c for c in captures}
        self.assertEqual(found["a.png"].dimensions, (80, 60))
        self.assertIsNone(found["broken.png"].dimensions)
        self.assertTrue(found["broken.png"].dims_failed)


class AnalysisTests(Fixture):
    def test_exact_duplicates_use_contents_not_names(self):
        folder = self.home / "Videos" / "Captures"
        a = picture(folder / "a.png", age_days=10)
        copy = folder / "copy of a.png"
        copy.write_bytes(a.read_bytes())
        os.utime(copy, (time.time() - 2 * DAY,) * 2)
        picture(folder / "b.png", color=(10, 200, 10))
        captures = self.scan().captures
        groups = analysis.find_duplicates(captures)
        self.assertEqual(len(groups), 1)
        names = [next(c.name for c in captures if c.key == k) for k in groups[0]]
        self.assertEqual(names, ["a.png", "copy of a.png"])  # oldest first

    def test_similar_images_group_close_hashes_only(self):
        folder = self.home / "Videos" / "Captures"
        picture(folder / "one.png", size=(96, 64))
        picture(folder / "one_again.png", size=(96, 64), noise=1)
        other = Image.new("RGB", (96, 64))
        px = other.load()
        for x in range(96):
            for y in range(64):
                px[x, y] = (255 - x * 2, y * 3 % 256, (x * y) % 256)
        other.save(folder / "different.png")
        captures = self.scan().captures
        groups, compared = analysis.find_similar(captures)
        self.assertEqual(compared, 3)
        names = [sorted(next(c.name for c in captures if c.key == k) for k in g) for g in groups]
        self.assertEqual(names, [["one.png", "one_again.png"]])

    def test_group_similar_uses_hamming_distance(self):
        groups = analysis.group_similar({"a": 0, "b": 0b111, "c": (1 << 64) - 1})
        self.assertEqual(groups, [["a", "b"]])


class TagTests(unittest.TestCase):
    def test_tags_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tags.json"
            tags = state.add_tag({}, ["k1", "k2"], "  Best   Shots ")
            tags = state.add_tag(tags, ["k1"], "boss")
            state.save_tags(tags, path)
            loaded = state.load_tags(path)
            self.assertEqual(loaded, {"k1": ["Best Shots", "boss"], "k2": ["Best Shots"]})
            self.assertEqual(state.all_tags(loaded), ["Best Shots", "boss"])
            loaded = state.remove_tag(loaded, ["k1", "k2"], "Best Shots")
            self.assertEqual(loaded, {"k1": ["boss"]})
            with self.assertRaises(ValueError):
                state.clean_tag("   ")
            path.write_text("not json")
            self.assertEqual(state.load_tags(path), {})


class InsightTests(Fixture):
    def captures(self):
        folder = self.home / "Videos" / "Captures"
        picture(folder / "Cyberpunk 2077" / "new.png", age_days=2)
        picture(folder / "Cyberpunk 2077" / "old.png", age_days=400, size=(3840, 4))
        write(folder / "clip.mp4", b"v" * (6 * 1024 ** 2), age_days=800)
        captures = self.scan().captures
        data.read_dimensions(captures)
        return captures

    def test_totals_use_real_metadata(self):
        captures = self.captures()
        t = insight.totals(captures, now=time.time())
        self.assertEqual((t["screenshots"], t["recordings"], t["games"]), (2, 1, 1))
        self.assertEqual(t["bytes"], sum(c.size for c in captures))
        self.assertGreaterEqual(t["oldest"], 799)
        self.assertEqual(insight.age_text(800), "2+ Years")
        self.assertEqual(insight.age_text(75), "2+ Months")
        self.assertEqual(t["candidate_bytes"], sum(c.size for c in captures if c.name in {"old.png", "clip.mp4"}))

    def test_tabs_and_filters(self):
        captures = self.captures()
        names = lambda **kw: [c.name for c in insight.filter_captures(captures, **kw)]
        self.assertEqual(names(tab="Screenshots"), ["new.png", "old.png"])
        self.assertEqual(names(tab="Recordings"), ["clip.mp4"])
        self.assertEqual(names(tab="Clean Up"), ["old.png", "clip.mp4"])
        self.assertEqual(names(tab="Duplicates"), [])
        self.assertEqual(names(tab="Screenshots", age=3), ["old.png"])
        self.assertEqual(names(tab="Recordings", size=2), ["clip.mp4"])
        self.assertEqual(names(tab="Recordings", size=3), [])
        self.assertEqual(names(tab="Screenshots", game="Cyberpunk 2077", query="NEW"), ["new.png"])
        self.assertEqual(names(tab="Screenshots", sort="Name (A–Z)"), ["new.png", "old.png"])
        self.assertEqual(names(tab="Screenshots", resolution=5), [])
        self.assertEqual(names(tab="Screenshots", kinds=("Recordings",)), [])

    def test_resolution_filter_and_tags(self):
        captures = self.captures()
        key = captures[0].key
        tags = {key: ["keep"]}
        names = lambda **kw: [c.name for c in insight.filter_captures(captures, tab="Timeline", tags=tags, **kw)]
        self.assertEqual(names(tag="keep"), [captures[0].name])
        self.assertEqual(len(names(tag="Untagged")), 2)
        self.assertEqual(names(resolution=1), ["old.png"])
        self.assertEqual(names(resolution=4), ["new.png"])
        self.assertEqual(names(resolution=5), ["clip.mp4"])
        self.assertEqual(names(month="1999-01"), [])

    def test_duplicate_and_similar_tabs_and_clean_up_extras(self):
        folder = self.home / "Videos" / "Captures"
        a = picture(folder / "a.png", age_days=3)
        b = folder / "b.png"
        b.write_bytes(a.read_bytes())
        os.utime(b, (time.time() - DAY,) * 2)
        captures = self.scan().captures
        groups = analysis.find_duplicates(captures)
        shown = insight.filter_captures(captures, tab="Duplicates", duplicates=groups)
        self.assertEqual(sorted(c.name for c in shown), ["a.png", "b.png"])
        cleanup = insight.filter_captures(captures, tab="Clean Up", duplicates=groups, now=time.time())
        self.assertEqual([c.name for c in cleanup], ["b.png"])  # keeps the oldest copy, offers the extra
        rel = insight.related(shown[0], captures, groups, None)
        self.assertEqual([r for r, _ in rel][:1], ["Exact copy"])

    def test_facts_never_say_safe_to_delete(self):
        captures = self.captures()
        for dup in (None, []):
            for c in captures:
                text = " ".join(t for _, t in insight.facts(c, never_touch=[], duplicates=dup, similar=None)).lower()
                self.assertNotIn("safe to delete", text)
                self.assertNotIn("safe to remove", text)
        self.assertIn("not checked", insight.facts(captures[0], never_touch=[], duplicates=None, similar=None)[1][1].lower())

    def test_delete_gating(self):
        captures = self.captures()
        self.assertFalse(insight.selection_state([], False)[0])
        self.assertTrue(insight.selection_state(captures[:1], False)[0])
        self.assertFalse(insight.selection_state(captures[:1], True)[0])


class ActionTests(Fixture):
    def setUp(self):
        super().setUp()
        self.folder = self.home / "Videos" / "Captures"
        self.files = [picture(self.folder / f"s{i}.png", color=(10 * i, 20, 30)) for i in range(3)]
        self.captures = self.scan().captures
        self.roots = [r.path for r in data.capture_roots({}, steam_roots=[self.steam], home=self.home)]

    def run_recycle(self, captures, never=()):
        moved = []
        with patch("gg_desktop.captures_actions.recycle_file", side_effect=lambda p: (moved.append(p), os.unlink(p))), \
             patch("gg_desktop.captures_actions.register_recycle", return_value="r1"), \
             patch("gg_desktop.captures_actions.log_event"):
            result = actions.recycle(captures, self.roots, never, "test")
        return result, moved

    def test_recycles_only_verified_files(self):
        target = next(c for c in self.captures if c.name == "s0.png")
        result, moved = self.run_recycle([target])
        self.assertEqual((result["completed"], result["skipped"]), (1, []))
        self.assertEqual([p.name for p in moved], ["s0.png"])
        self.assertFalse(self.files[0].exists())
        self.assertTrue(all(p.exists() for p in self.files[1:]))

    def test_changed_protected_and_outside_files_are_skipped(self):
        changed, protected, outside = self.captures[0], self.captures[1], self.captures[2]
        Path(changed.path).write_bytes(Path(changed.path).read_bytes() + b"!")
        result, moved = self.run_recycle([changed, protected, outside], never=[str(Path(protected.path))])
        self.assertEqual(result["completed"], 1)
        self.assertEqual(len(result["skipped"]), 2)
        self.assertTrue(Path(changed.path).exists() and Path(protected.path).exists())
        plans = actions.inspect([outside], [self.root / "Elsewhere"], [])
        self.assertIn("known capture folder", plans[0].reason)

    def test_run_size_limit(self):
        with self.assertRaises(ValueError):
            actions.recycle([self.captures[0]] * (actions.MAX_RUN + 1), self.roots, (), "t")
        plans = actions.inspect([self.captures[0]] * (actions.MAX_RUN + 1), self.roots, [])
        self.assertIn("limited", plans[-1].reason)

    def test_copy_never_overwrites_or_changes_originals(self):
        dest = self.root / "Out"
        dest.mkdir()
        (dest / "s0.png").write_bytes(b"existing")
        result = actions.copy_to(self.captures, dest)
        self.assertEqual(len(result["copied"]), 3)
        self.assertEqual((dest / "s0.png").read_bytes(), b"existing")
        self.assertTrue((dest / "s0 (2).png").exists())
        self.assertTrue(all(f.exists() for f in self.files))
        with self.assertRaises(ValueError):
            actions.copy_to(self.captures, self.root / "missing")


if __name__ == "__main__":
    unittest.main()
