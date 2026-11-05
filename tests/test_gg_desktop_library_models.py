"""Evidence and full-inventory filtering behind the reference desktop screens."""
from pathlib import Path
from types import SimpleNamespace
import unittest

from core import OldFile, ModFolder
from gg_desktop.library_models import file_kind, launcher_bucket, mod_view, old_file_rows


class ReferenceModelTests(unittest.TestCase):
    def test_mod_relationship_requires_install_path_boundary(self):
        game = SimpleNamespace(name="Cyberpunk 2077", install_path="D:/Games/Cyberpunk")
        mod = ModFolder("Cyberpunk 2077", "D:/Games/Cyberpunk-old/mods", "", "Unmatched folder",
                        (), 1234, 2, False, "Vortex")
        view = mod_view(mod, [game])
        self.assertEqual(view.game, "Unverified")
        self.assertEqual(view.version, "Unknown")
        mod.path = "D:/Games/Cyberpunk/mods"
        self.assertEqual(mod_view(mod, [game]).game, "Cyberpunk 2077")

    def test_longest_verified_parent_wins_without_title_matching(self):
        games = [SimpleNamespace(name="Outer", install_path="D:/Games/Collection"),
                 SimpleNamespace(name="Inner", install_path="D:/Games/Collection/Inner")]
        mod = ModFolder("Some other name", "D:/Games/Collection/Inner/mods", "", "Protected", (), 0, 0, False)
        self.assertEqual(mod_view(mod, games).game, "Inner")

    def test_mixed_launcher_claim_has_one_other_bucket(self):
        self.assertEqual(launcher_bucket("Steam / Epic Games"), "Other")
        self.assertEqual(launcher_bucket("EA"), "EA")
        self.assertEqual(launcher_bucket("Unreal custom library"), "Other")
        self.assertEqual(launcher_bucket("Epic Games"), "Epic")

    def test_filtering_reaches_past_the_former_500_row_cutoff(self):
        files = [OldFile(f"/downloads/old-{i}.zip", i, 0) for i in range(605)]
        result = old_file_rows(files, query="old-604")
        self.assertEqual([f.path for f in result], ["/downloads/old-604.zip"])
        self.assertEqual(old_file_rows(files)[0].size, 604)
        self.assertEqual(len(old_file_rows(files)), 605)

    def test_file_filters_combine_age_type_search_and_sort(self):
        now = 1000 * 86400
        files = [OldFile("/downloads/keep.zip", 500, now - 400 * 86400),
                 OldFile("/downloads/keep.exe", 900, now - 500 * 86400),
                 OldFile("/downloads/young.zip", 1000, now - 40 * 86400)]
        result = old_file_rows(files, query="keep", kinds={"Archives"}, days=365, now=now)
        self.assertEqual([Path(f.path).name for f in result], ["keep.zip"])
        self.assertEqual(file_kind("LOG.DMP"), "Logs / Crash Reports")
        self.assertEqual(file_kind("photo.PNG"), "Media")


if __name__ == "__main__":
    unittest.main()
