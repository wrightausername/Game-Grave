"""Overview measures real file metadata without changing accepted scan evidence."""
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import ModFolder, OldFile, SteamGame
from gg_desktop.backend import Inventory
from gg_desktop.models import merge_games
from gg_desktop.mods_data import Catalog, ModEntry
from gg_desktop.overview_storage import measure_storage, inventory_key


class StorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="GG-overview-storage-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def payload(self, path, size):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        return path

    def game(self, path="Game", reported=999999):
        folder = self.root / path
        folder.mkdir(parents=True, exist_ok=True)
        raw = SteamGame(path, "Same game title", str(self.root), str(folder), reported, None, "Fixture")
        return merge_games([raw], [])[0]

    def mod(self, path, source="Custom mod storage", status="Detected"):
        return ModFolder(Path(path).name, str(path), str(self.root), status, (), 9999, 1, False, source)

    @staticmethod
    def record(path):
        st = path.stat()
        return OldFile(str(path), st.st_size, st.st_mtime, st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink)

    def measure(self, inventory, **kwargs):
        return measure_storage(inventory, catalog_reader=lambda *_a, **_k: Catalog(), **kwargs)

    def test_games_use_actual_bytes_not_stale_or_zero_manifest(self):
        game = self.game(reported=0)
        self.payload("Game/content.bin", 713)
        self.payload("Game/nested/other.bin", 12)
        result = self.measure(Inventory(games=[game]))
        self.assertEqual(result.total, 725)
        self.assertEqual(result.totals["Games"], 725)
        self.assertEqual(result.files, 2)
        self.assertFalse(result.partial)

    def test_same_install_is_counted_once_but_same_title_elsewhere_is_distinct(self):
        game, other = self.game(), self.game("Other")
        self.payload("Game/a", 11)
        self.payload("Other/a", 13)
        result = self.measure(Inventory(games=[game, replace(game, key="duplicate"), other]))
        self.assertEqual(result.game_count, 2)
        self.assertEqual(result.total, 24)

    def test_inline_mod_finding_does_not_charge_entire_game_as_mods(self):
        game = self.game()
        self.payload("Game/base.bin", 100)
        self.payload("Game/Mods/package/data.bin", 30)
        mod = self.mod(Path(game.install_path), "Steam game folder", "Installed: possible mods")
        result = self.measure(Inventory(games=[game], mods=[mod]))
        self.assertEqual(result.totals["Games"], 100)
        self.assertEqual(result.totals["Mods"], 30)
        self.assertEqual(result.total, 130)

    def test_nested_roots_and_old_files_are_not_double_counted(self):
        game = self.game()
        first = self.payload("Game/base.bin", 31)
        mod = self.payload("Game/Mods/a.bin", 43)
        inventory = Inventory(games=[game], mods=[self.mod(mod.parent), self.mod(mod.parent.parent)],
                              files=[self.record(first), self.record(mod)])
        result = self.measure(inventory)
        self.assertEqual(result.total, 74)
        self.assertEqual(result.totals["Old Files"], 0)
        self.assertEqual(sum(r.counted_bytes for r in result.roots), result.total)

    def test_deployed_hardlinks_count_once_as_mods_in_either_root_order(self):
        game = self.game()
        source = self.payload("Staging/Texture/dds.bin", 91)
        deployed = self.root / "Game/deployed.bin"
        try:
            os.link(source, deployed)
        except OSError:
            self.skipTest("Hardlinks unavailable")
        self.payload("Game/base.bin", 10)
        inventory = Inventory(games=[game], mods=[self.mod(source.parent.parent), self.mod(source.parent)])
        for mods in (inventory.mods, list(reversed(inventory.mods))):
            result = self.measure(replace(inventory, mods=mods))
            self.assertEqual(result.total, 101)
            self.assertEqual(result.totals["Mods"], 91)
            self.assertEqual(result.totals["Games"], 10)
            self.assertEqual(result.files, 2)
            self.assertEqual(result.shared_files, 1)

    def test_five_categories_have_one_exact_denominator(self):
        game = self.game()
        self.payload("Game/content", 101)
        mod = self.payload("Mods/content", 53)
        cache = self.payload("Cache/content", 29)
        capture = self.payload("Captures/a.png", 13)
        archive = self.payload("Downloads/a.zip", 7)
        inventory = Inventory(games=[game], mods=[self.mod(mod.parent), self.mod(cache.parent, "Shader Cache")],
            files=[self.record(archive), self.record(capture)], screenshots=[self.record(capture)])
        result = self.measure(inventory)
        self.assertEqual(result.totals, dict(Games=101, Mods=53, **{"Other Storage":29, "Captures":13, "Old Files":7}))
        self.assertEqual(sum(v/result.total for _, v, _ in result.segments), 1)

    def test_missing_and_empty_are_distinct(self):
        game = self.game()
        empty = self.measure(Inventory(games=[game]))
        self.assertFalse(empty.partial)
        self.assertEqual(empty.roots[0].status, "Measured")
        (self.root / "Game").rmdir()
        missing = self.measure(Inventory(games=[game]))
        self.assertTrue(missing.partial)
        self.assertEqual(missing.roots[0].status, "Unavailable")
        self.assertEqual(missing.total, 0)

    def test_unverified_install_is_not_mislabeled_measured(self):
        game = replace(self.game(), capabilities=())
        self.payload("Game/content", 10)
        result = self.measure(Inventory(games=[game]))
        self.assertTrue(result.partial)
        self.assertFalse(result.roots[0].valid)
        self.assertEqual(result.total, 0)

    def test_symbolic_links_never_pull_in_other_folders(self):
        game = self.game()
        private = self.payload("Private/content", 900)
        self.payload("Game/content", 10)
        try:
            (self.root / "Game/linked-file").symlink_to(private)
            (self.root / "Game/linked-dir").symlink_to(private.parent, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable")
        result = self.measure(Inventory(games=[game]))
        self.assertEqual(result.total, 10)
        self.assertTrue(result.partial)

    def test_inaccessible_subfolder_is_explicitly_partial(self):
        game = self.game()
        self.payload("Game/content", 10)
        self.payload("Game/Denied/content", 20)
        original = os.scandir
        def scan(path):
            if Path(path).name == "Denied":
                raise PermissionError("Fixture denial")
            return original(path)
        with patch("gg_desktop.overview_storage.os.scandir", side_effect=scan):
            result = self.measure(Inventory(games=[game]))
        self.assertEqual(result.total, 10)
        self.assertTrue(result.partial)
        self.assertIn("Fixture denial", " ".join(result.roots[0].problems))

    def test_entry_and_directory_limits_are_marked_partial(self):
        game = self.game()
        for i in range(5):
            self.payload(f"Game/{i}/content", 11)
        for kwargs in (dict(max_entries=2), dict(max_files=1), dict(max_directories=1)):
            result = self.measure(Inventory(games=[game]), **kwargs)
            self.assertTrue(result.limited)
            self.assertTrue(result.category_partial("Games"))
            self.assertLess(result.total, 55)

    def test_cancel_does_not_change_inventory_or_source_files(self):
        game = self.game()
        source = self.payload("Game/content", 10)
        inventory = Inventory(games=[game])
        before = deepcopy(inventory)
        with self.assertRaises(InterruptedError):
            self.measure(inventory, canceled=lambda: True)
        self.assertEqual(inventory, before)
        self.assertEqual(source.read_bytes(), b"x"*10)

    def test_metadata_only_sparse_logical_bytes_and_volume_reading(self):
        game = self.game()
        with (self.root / "Game/sparse.bin").open("wb") as stream:
            stream.truncate(1024**3)
        with patch("builtins.open", side_effect=AssertionError("Game payload was opened")):
            result = self.measure(Inventory(games=[game]))
        self.assertEqual(result.total, 1024**3)
        self.assertEqual(result.volumes[0].path, self.root.anchor)

    def test_mod_count_uses_individual_packages_and_marks_catalog_limit(self):
        folder = self.payload("Mods/One/content", 10).parent
        catalog = Catalog(entries=[ModEntry("one", "One", str(folder), "MO2", "Detected", kind="mod"),
                                  ModEntry("alias", "Alias", str(folder), "MO2", "Detected", kind="mod")], limited=True)
        result = measure_storage(Inventory(mods=[self.mod(folder.parent)]), catalog_reader=lambda *_a, **_k: catalog)
        self.assertEqual(result.mod_count, 1)
        self.assertEqual(result.mod_unit, "Mods")
        self.assertTrue(result.mod_count_partial)
        self.assertEqual(result.total, 10)

    def test_real_mo2_catalog_counts_packages_not_roots(self):
        from tests.test_mods_functionality import mo2_fixture
        inventory, *_ = mo2_fixture(self.root)
        result = measure_storage(inventory)
        self.assertEqual(result.mod_count, 4)
        self.assertEqual(result.mod_unit, "Mods")
        self.assertGreater(result.totals["Mods"], 0)

    def test_cache_key_changes_with_accepted_scan(self):
        inventory = Inventory(games=[self.game()])
        before = inventory_key(inventory)
        inventory.scanned_at = "New accepted scan"
        self.assertNotEqual(before, inventory_key(inventory))


if __name__ == "__main__":
    unittest.main()
