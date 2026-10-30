"""WoW addon and settings discovery remains read-only and protected."""
import tempfile
import unittest
from pathlib import Path
from core import is_protected_path
from ecosystems import known_locations, find_ecosystem_storage


class WorldOfWarcraftPathsTests(unittest.TestCase):
    def test_addons_found_with_known_launcher_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            pf = Path(tmp) / "Program Files (x86)"
            root = pf / "World of Warcraft" / "_retail_"
            addons = root / "Interface" / "AddOns"
            addon = addons / "QuestHelper"
            addon.mkdir(parents=True)
            (addon / "QuestHelper.toc").write_text("## Title: Quest Helper")
            settings = root / "WTF" / "Account"
            settings.mkdir(parents=True)
            (settings / "settings.lua").write_text("kept")
            env = {"PROGRAMFILES(X86)": str(pf), "APPDATA": str(Path(tmp)/"AppData"), "LOCALAPPDATA": str(Path(tmp)/"Local")}
            locations = known_locations(home=Path(tmp), env=env)
            self.assertTrue(any(x[0] == "World of Warcraft" and x[1] == addons for x in locations))
            results = find_ecosystem_storage(home=Path(tmp), env=env)
            self.assertTrue(any(x.source == "World of Warcraft" and x.path == str(addons) for x in results))
            self.assertTrue(is_protected_path(settings / "settings.lua"))
            self.assertTrue((addon / "QuestHelper.toc").exists())


if __name__ == "__main__":
    unittest.main()
