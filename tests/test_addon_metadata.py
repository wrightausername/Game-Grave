"""Local addon metadata recognition is bounded and never authorizes removal."""
import tempfile
import unittest
from pathlib import Path

from core import ModFolder
from addon_metadata import inspect_addon_metadata, MAX_DESCRIPTOR
from file_detective import investigate


class AddonMetadataTests(unittest.TestCase):
    def test_eso_manifest_dependencies_and_settings_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            addons = Path(tmp) / "Elder Scrolls Online" / "live" / "AddOns"
            d = addons / "MyAddon"
            d.mkdir(parents=True)
            (d / "MyAddon.txt").write_text(
                "## Title: My Addon\n## APIVersion: 101040\n## DependsOn: LibAddonMenu-2.0 LibFoo\n")
            parsed = inspect_addon_metadata(d)
            self.assertEqual(parsed.ecosystem, "ESO")
            self.assertIn("LibFoo", parsed.dependencies)
            verdict = investigate(d)
            self.assertEqual(verdict.headline, "Recognized addon descriptor")
            self.assertTrue(verdict.protected)
            self.assertIn("does not establish", verdict.explanation)

    def test_wow_toc_and_manager_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "World of Warcraft" / "_retail_" / "Interface" / "AddOns" / "Foo"
            d.mkdir(parents=True)
            (d / "Foo.toc").write_text(
                "## Title: Foo Bar\n## Interface: 110200\n## Dependencies: LibBar")
            mod = ModFolder(d.name, str(d), str(d.parent), "Installed addons", (), 100, 2,
                            False, "World of Warcraft", "Review in game")
            verdict = investigate(d, mods=[mod])
            self.assertIn("Local World of Warcraft descriptor", " ".join(verdict.evidence))
            self.assertEqual(inspect_addon_metadata(d).title, "Foo Bar")
            self.assertTrue(verdict.protected)

    def test_rejects_unrelated_or_too_large_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "Other Game" / "AddOns" / "Foo"
            d.mkdir(parents=True)
            (d / "Foo.txt").write_text("## Title: Foo")
            self.assertIsNone(inspect_addon_metadata(d))
            eso = Path(tmp) / "Elder Scrolls Online" / "live" / "AddOns" / "Foo"
            eso.mkdir(parents=True)
            (eso / "Foo.txt").write_bytes(b"x" * (MAX_DESCRIPTOR + 1))
            self.assertIsNone(inspect_addon_metadata(eso))


if __name__ == "__main__":
    unittest.main()
