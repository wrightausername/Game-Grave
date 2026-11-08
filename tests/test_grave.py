"""Graveyard: classification, honest evidence, live filter counts, metrics and removal limits."""
from __future__ import annotations

from pathlib import Path
import os
import tempfile
import time
import unittest

from core import OldFile
from gg_desktop import grave_actions as actions
from gg_desktop import grave_data as data
from gg_desktop import grave_insight as insight
from gg_desktop.other_storage_data import StorageEntry
from graveyard import GraveyardEntry

DAY = 86400
MB = 1024 ** 2
NOW = 1_800_000_000.0


def old_file(path, size=MB, age=400):
    return OldFile(str(path), size, NOW - age * DAY, 1, 1, int((NOW - age * DAY) * 1e9), 1)


def entry(name, category, size=MB, age=400, can=True, with_file=True, key=None, path=None):
    path = path or f"C:\\Scratch\\{name}"
    return GraveyardEntry(
        key=key or f"file:{path.casefold()}", name=name, path=path, category=category, apparent_bytes=size, age_days=age,
        relationship="rel", finding="found", protection="p", can_recycle=can,
        old_file=old_file(path, size, age) if with_file else None)


def stored(name, category, related="Game", size=5 * MB, items=10, newest=None, kind="review", app_id=""):
    path = f"C:\\Scratch\\Store\\{name}"
    return StorageEntry(path.casefold(), name, path, category, related, size, items, newest, False, "summary", "evidence",
                        "note", kind, app_id)


class Classification(unittest.TestCase):
    def test_graveyard_entries_land_on_the_right_tab_and_evidence(self):
        rows = data.from_graveyard([
            entry("Cyberpunk 2077", "Neglected installed game", can=False, with_file=False, key="steam:1091500"),
            entry("skyrim mod pack.zip", "Possible mod / game download"),
            entry("clip.mp4", "Old game recording"),
            entry("shot.png", "Old game screenshot", can=False),
            entry("manual.bin", "Manual review", can=False),
            entry("SomeMods", "Manual / Other", can=False, with_file=False, key="mod:x"),
        ], NOW)
        got = {r.name: (r.tab, r.kind, r.evidence) for r in rows}
        self.assertEqual(got["Cyberpunk 2077"], ("Games", data.TYPES[0], "Direct"))
        self.assertEqual(got["skyrim mod pack.zip"], ("Downloads", data.TYPES[2], "Name hint"))
        self.assertEqual(got["clip.mp4"], ("Leftovers", data.TYPES[5], "Location"))
        self.assertEqual(got["shot.png"], ("Leftovers", data.TYPES[5], "Location"))
        self.assertEqual(got["manual.bin"], ("Leftovers", data.TYPES[6], "Yours"))
        self.assertEqual(got["SomeMods"], ("Mods", data.TYPES[1], "Age only"))
        self.assertEqual(next(r for r in rows if r.name == "Cyberpunk 2077").app_id, "1091500")

    def test_storage_entries_orphans_configs_and_leftovers(self):
        rows = data.from_storage([
            stored("Steam app 5 Shader Cache", "Shader Cache", "No installed game", kind="steam-shader"),
            stored("Cyberpunk Shader Cache", "Shader Cache", "Cyberpunk 2077", kind="steam-shader", app_id="1091500"),
            stored("My Games", "Config / Settings", kind="settings"),
            stored("Launcher cache", "Caches", kind="clearable"),
            stored("Logs", "Logs / Reports", kind="clearable"),
            stored("Steam Temp", "Temporary Files"),
        ], NOW)
        tabs = {r.name: (r.tab, r.kind, r.evidence) for r in rows}
        self.assertEqual(tabs["Steam app 5 Shader Cache"], ("Orphans", data.TYPES[3], "Direct"))
        self.assertEqual(tabs["Cyberpunk Shader Cache"], ("Leftovers", data.TYPES[3], "Direct"))
        self.assertEqual(tabs["My Games"], ("Configs", data.TYPES[4], "Location"))
        self.assertEqual(tabs["Launcher cache"][0:2], ("Leftovers", data.TYPES[3]))
        self.assertEqual(tabs["Logs"][1], data.TYPES[6])
        self.assertEqual(next(r for r in rows if r.name == "Cyberpunk Shader Cache").game, "Cyberpunk 2077")
        self.assertEqual(next(r for r in rows if r.name == "Logs").game, "")

    def test_merge_drops_a_scanned_folder_the_engine_already_lists(self):
        first = data.from_graveyard([entry("a.zip", "Possible mod / game download", path="C:\\Scratch\\Store\\Dup")], NOW)
        second = data.from_storage([stored("Dup", "Caches", kind="clearable"), stored("Other", "Caches")], NOW)
        self.assertEqual(sorted(i.name for i in data.merge(first, second)), ["Other", "a.zip"])

    def test_no_item_claims_safety(self):
        rows = data.from_graveyard([entry("a.zip", "Possible mod / game download")], NOW)
        rows += data.from_storage([stored("Logs", "Logs / Reports")], NOW)
        for item in rows:
            text = " ".join(t for _, t in insight.reasons(item, [])) + item.why + data.EVIDENCE_TEXT[item.evidence]
            self.assertNotIn("safe to remove", text.casefold())
            self.assertNotIn("unused", text.casefold().replace("does not show it is unused", "").replace("not show it is unused", ""))


class Filters(unittest.TestCase):
    def setUp(self):
        self.items = data.from_graveyard([
            entry("a.zip", "Possible mod / game download", size=50 * MB, age=40),
            entry("b.zip", "Possible mod / game download", size=500 * MB, age=200),
            entry("c.mp4", "Old game recording", size=5 * 1024 * MB, age=800),
            entry("Game", "Neglected installed game", size=20 * 1024 * MB, age=400, can=False, with_file=False, key="steam:7"),
        ], NOW)

    def test_age_is_cumulative_and_unknown_age_is_excluded(self):
        names = lambda ages: sorted(i.name for i in insight.filter_items(self.items, ages=ages))
        self.assertEqual(names(("30+ Days",)), ["Game", "a.zip", "b.zip", "c.mp4"])
        self.assertEqual(names(("6+ Months",)), ["Game", "b.zip", "c.mp4"])
        self.assertEqual(names(("24+ Months",)), ["c.mp4"])
        self.items[0].age_days = None
        self.assertNotIn("a.zip", names(("30+ Days",)))
        self.assertIn("a.zip", names(()))

    def test_size_buckets_and_types(self):
        names = lambda **k: sorted(i.name for i in insight.filter_items(self.items, **k))
        self.assertEqual(names(sizes=("< 100 MB",)), ["a.zip"])
        self.assertEqual(names(sizes=("1 GB - 10 GB", "> 10 GB")), ["Game", "c.mp4"])
        self.assertEqual(names(types=(data.TYPES[2],)), ["a.zip", "b.zip"])
        self.assertEqual(names(types=()), [])
        self.assertEqual(len(names(types=data.TYPES)), 4)

    def test_tabs_query_and_sort(self):
        self.assertEqual([i.name for i in insight.filter_items(self.items, tab="Downloads", sort="Name (A-Z)")], ["a.zip", "b.zip"])
        self.assertEqual([i.name for i in insight.filter_items(self.items, query="MP4")], ["c.mp4"])
        self.assertEqual(insight.filter_items(self.items, sort="Size (Largest)")[0].name, "Game")
        self.assertEqual(insight.filter_items(self.items, sort="Last Touched (Oldest)")[0].name, "c.mp4")
        self.assertEqual(insight.filter_items(self.items, sort="Last Touched (Newest)")[0].name, "a.zip")
        counts = insight.tab_counts(self.items)
        self.assertEqual((counts["All Items"], counts["Downloads"], counts["Games"], counts["Orphans"]), (4, 2, 1, 0))

    def test_facet_counts_ignore_their_own_selection(self):
        age, size, kind = insight.facet_counts(self.items, ages=("24+ Months",))
        self.assertEqual(age["30+ Days"], 4)       # age counts ignore the age choice
        self.assertEqual(size["1 GB - 10 GB"], 1)  # size counts obey it
        self.assertEqual(sum(size.values()), 1)
        self.assertEqual(kind[data.TYPES[5]], 1)
        self.assertEqual(kind[data.TYPES[2]], 0)


class Metrics(unittest.TestCase):
    def test_totals_and_reviewable_follow_the_engine(self):
        rows = data.from_graveyard([
            entry("a.zip", "Possible mod / game download", size=MB, age=400),
            entry("shot.png", "Old game screenshot", can=False, age=10),
            entry("Game", "Neglected installed game", size=2 * MB, age=300, can=False, with_file=False, key="steam:1"),
            entry("Mods1", "Manual / Other", can=False, with_file=False, key="mod:a", age=10),
        ], NOW)
        t = insight.totals(rows, [])
        self.assertEqual((t["items"], t["downloads"], t["mods"], t["games"], t["reviewable"], t["idle"]), (4, 1, 1, 1, 1, 2))
        self.assertEqual(t["bytes"], 5 * MB)
        with tempfile.TemporaryDirectory() as folder:
            held = data.from_graveyard([entry("a.zip", "Possible mod / game download", path=str(Path(folder) / "a.zip"))], NOW)
            self.assertEqual(insight.totals(held, [])["reviewable"], 1)
            self.assertEqual(insight.totals(held, [folder])["reviewable"], 0)

    def test_protected_settings_folders_are_never_reviewable(self):
        item = data.from_storage([stored("My Games", "Config / Settings", kind="settings")], NOW)[0]
        self.assertTrue(data.is_protected(item, []))
        self.assertFalse(insight.recyclable(item))


class Removal(unittest.TestCase):
    def test_delete_options_only_offer_what_applies(self):
        rows = data.from_graveyard([
            entry("a.zip", "Possible mod / game download"),
            entry("shot.png", "Old game screenshot", can=False),
            entry("Game", "Neglected installed game", can=False, with_file=False, key="steam:77"),
            entry("Mods1", "Manual / Other", can=False, with_file=False, key="mod:a"),
        ], NOW)
        archive, shot, game, mod = rows
        enabled = lambda items: {k: e for k, _, e, _ in insight.delete_options(items, [])}
        self.assertTrue(enabled([archive])["recycle"])
        self.assertFalse(enabled([archive, shot])["recycle"])
        self.assertFalse(enabled([])["recycle"])
        self.assertTrue(enabled([shot])["preview"])
        self.assertFalse(enabled([shot])["recycle"])
        self.assertTrue(enabled([game])["steam"])
        self.assertTrue(enabled([mod])["mods"])
        self.assertFalse(enabled([game])["recycle"])
        self.assertFalse(enabled([archive], )["steam"])

    def test_blockers_explain_each_refusal(self):
        rows = data.from_graveyard([
            entry("a.zip", "Possible mod / game download"),
            entry("shot.png", "Old game screenshot", can=False),
            entry("Mods1", "Manual / Other", can=False, with_file=False, key="mod:a"),
        ], NOW)
        archive, shot, mod = rows
        self.assertEqual(actions.blockers([archive], []), [])
        self.assertTrue(any("preview" in b for b in actions.blockers([shot], [])))
        self.assertTrue(any("not an ordinary file" in b for b in actions.blockers([mod], [])))
        with tempfile.TemporaryDirectory() as folder:
            held = data.from_graveyard([entry("a.zip", "Possible mod / game download", path=str(Path(folder) / "a.zip"))], NOW)[0]
            self.assertTrue(any("protected" in b for b in actions.blockers([held], [folder])))
        self.assertTrue(actions.blockers([], []))
        many = [archive] * (insight.MAX_RECYCLE + 1)
        self.assertTrue(any("at most" in b for b in actions.blockers(many, [])))

    def test_steam_uninstall_only_for_proven_games(self):
        game = data.from_graveyard([entry("G", "Neglected installed game", can=False, with_file=False, key="steam:620")], NOW)[0]
        self.assertEqual(actions.uninstall_url(game), "steam://uninstall/620")
        game.app_id = "62;calc"
        self.assertIsNone(actions.uninstall_url(game))
        other = data.from_graveyard([entry("a.zip", "Possible mod / game download")], NOW)[0]
        self.assertIsNone(actions.uninstall_url(other))


class Contents(unittest.TestCase):
    def test_list_contents_is_read_only_and_capped(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sub").mkdir()
            for n in range(5):
                (root / f"f{n}.txt").write_bytes(b"x" * 10)
            before = sorted(os.listdir(root))
            rows, truncated = actions.list_contents(root, limit=3)
            self.assertEqual(len(rows), 3)
            self.assertTrue(truncated)
            rows, truncated = actions.list_contents(root)
            self.assertEqual((len(rows), truncated), (6, False))
            self.assertEqual(rows[0][:2], ("sub", "folder"))
            self.assertEqual(sorted(os.listdir(root)), before)
            self.assertEqual(actions.list_contents(root / "missing"), ([], False))


class Presentation(unittest.TestCase):
    def test_text_helpers(self):
        row = data.from_graveyard([entry("a.zip", "Possible mod / game download", age=10)], NOW)[0]
        self.assertIn("10 days ago", insight.age_phrase(row))
        self.assertEqual(insight.items_text(row), "1 file")
        folder = data.from_storage([stored("Cache", "Caches", items=1204, newest=NOW - 3 * DAY)], NOW)[0]
        self.assertEqual(insight.items_text(folder), "1,204 files")
        self.assertIn("3 days", folder.why)
        self.assertEqual(next(insight.csv_rows([row]))[0], "Name")


if __name__ == "__main__":
    unittest.main()
