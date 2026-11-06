"""Local mod descriptions, profile isolation and bounded conflict evidence."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from core import ModFolder, SteamGame
from gg_desktop.backend import Inventory
from gg_desktop.models import merge_games
from gg_desktop.mods_data import (Catalog, Dependency, ModEntry, Profile, base_catalog,
    build_catalog, identity, inspect_metadata, mod_page, text_file)
from gg_desktop.mod_conflicts import inspect_conflicts, version_satisfies


def mo2_fixture(root):
    manager = root / "MO2"
    storage, profiles = manager / "mods", manager / "profiles"
    storage.mkdir(parents=True)
    (profiles / "Default").mkdir(parents=True)
    (profiles / "Separate").mkdir()
    game = root / "Games" / "Skyrim"
    game.mkdir(parents=True)
    ini = manager / "ModOrganizer.ini"
    ini.write_text(f"[General]\ngamePath={game}\nselected_profile=Default\n[Settings]\nbase_directory={manager}\n", encoding="utf-8")
    steam = [SteamGame("489830", "Skyrim Special Edition", str(root), str(game), 1000, None, "Unknown")]
    mods = [ModFolder(name, str(path), str(manager), state, ("MO2 INI: " + str(ini),), 1000, 1, False, "Mod Organizer 2")
            for name, path, state in (("mods", storage, "MO2: installed mods"), ("profiles", profiles, "MO2: profiles / saves protected"))]
    inventory = Inventory(steam=steam, games=merge_games(steam, []), mods=mods, scanned_at="Disposable mod QA")
    for name, payload in {
        "MountainTextures": {"Name": "Mountain Textures", "UniqueID": "Example.Mountains", "Description": "High resolution mountain textures.",
                             "Author": "Local Author", "Version": "2.0", "Dependencies": [{"UniqueID": "Example.Framework", "MinimumVersion": "2.0"}]},
        "SnowTextures": {"name": "Snow Textures", "id": "snow", "description": "Snow surfaces and texture replacements.", "version": "1.2"},
        "Framework": {"name": "Framework", "id": "Example.Framework", "version": "1.0"},
        "Disabled": {"name": "Disabled mod", "description": "Installed but disabled in the saved profile."},
    }.items():
        folder = storage / name
        folder.mkdir()
        (folder / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
        (folder / "textures").mkdir()
        (folder / "textures" / "mountain.dds").write_bytes(b"Disposable texture file")
    (profiles / "Default" / "modlist.txt").write_text("+MountainTextures\n+SnowTextures\n-Framework\n-Disabled\n+MissingFolder\n", encoding="utf-8")
    (profiles / "Separate" / "modlist.txt").write_text("-MountainTextures\n-SnowTextures\n+Framework\n", encoding="utf-8")
    return inventory, storage, profiles, ini


class ModsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="GG-mods-unit-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_saved_profiles_descriptions_and_exact_game(self):
        inventory, storage, profiles, _ = mo2_fixture(self.root)
        before = deepcopy(inventory)
        catalog = build_catalog(inventory)
        mountain = next(e for e in catalog.entries if e.path == str(storage / "MountainTextures"))
        self.assertEqual(mountain.name, "Mountain Textures")
        self.assertEqual(mountain.description, "High resolution mountain textures.")
        self.assertEqual(mountain.author, "Local Author")
        self.assertEqual(mountain.version, "2.0")
        self.assertEqual(mountain.dependencies, [Dependency("Example.Framework", ">=2.0")])
        self.assertEqual(set(mountain.profiles.values()), {"+", "-"})
        self.assertEqual(mountain.game_key, inventory.games[0].key)
        self.assertEqual(len(catalog.profiles), 2)
        self.assertTrue(next(p for p in catalog.profiles if p.name == "Default").selected)
        self.assertEqual(inventory, before)

    def test_enabled_overlap_and_disabled_dependency(self):
        inventory, *_ = mo2_fixture(self.root)
        catalog = build_catalog(inventory)
        report = inspect_conflicts(catalog)
        overlap = [f for f in report.findings if f.kind.startswith("File overlap")]
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0].paths, ["textures/mountain.dds"])
        self.assertEqual(overlap[0].count, 1)
        names = {e.key: e.name for e in catalog.entries}
        self.assertEqual({names[k] for k in overlap[0].mods}, {"Mountain Textures", "Snow Textures"})
        self.assertTrue(any(f.kind == "Required dependency not enabled" for f in report.findings))
        self.assertTrue(any(f.kind == "Enabled folder unavailable" for f in report.findings))
        self.assertFalse(any("Disabled mod" in [names[k] for k in f.mods] for f in report.findings))
        self.assertNotIn("All clear", report.summary())
        self.assertIn("unverified", report.summary())

    def test_profiles_do_not_leak_enabled_state(self):
        inventory, _, profiles, _ = mo2_fixture(self.root)
        (profiles / "Default" / "modlist.txt").write_text("+MountainTextures\n-SnowTextures\n-Framework\n")
        (profiles / "Separate" / "modlist.txt").write_text("-MountainTextures\n+SnowTextures\n+Framework\n")
        report = inspect_conflicts(build_catalog(inventory))
        self.assertFalse(any(f.kind.startswith("File overlap") and "Mountain" in f.detail for f in report.findings))
        overlaps = [f for f in report.findings if f.kind.startswith("File overlap")]
        self.assertEqual(len(overlaps), 1)  # Snow / Framework only in Separate.
        self.assertTrue(any(f.kind == "Required dependency not enabled" for f in report.findings))

    def test_changed_profile_requires_refresh(self):
        inventory, _, profiles, _ = mo2_fixture(self.root)
        catalog = build_catalog(inventory)
        (profiles / "Default" / "modlist.txt").write_text("-MountainTextures\n")
        report = inspect_conflicts(catalog)
        self.assertTrue(report.limited)
        self.assertTrue(any("Refresh details" in warning for warning in report.warnings))
        profile_key = next(p.key for p in catalog.profiles if p.name == "Default")
        self.assertFalse(any(f.profile == profile_key for f in report.findings))

    def test_manager_paths_changed_after_scan_are_not_followed(self):
        inventory, _, _, ini = mo2_fixture(self.root)
        (self.root / "Other").mkdir()
        with ini.open("a") as stream:
            stream.write("mod_directory=" + str(self.root / "Other") + "\n")
        catalog = build_catalog(inventory)
        self.assertTrue(catalog.limited)
        self.assertFalse(catalog.profiles)
        self.assertFalse(any(e.kind == "mod" for e in catalog.entries))

    def test_unknown_and_ambiguous_game_not_name_matched(self):
        inventory, _, _, ini = mo2_fixture(self.root)
        text = ini.read_text().replace(str(self.root / "Games" / "Skyrim"), str(self.root / "Other" / "Skyrim"))
        ini.write_text(text)
        self.assertTrue(all(not e.game_key for e in build_catalog(inventory).entries))

    def test_cancellation_preserves_input(self):
        inventory, *_ = mo2_fixture(self.root)
        before = deepcopy(inventory)
        with self.assertRaises(InterruptedError):
            build_catalog(inventory, lambda: True)
        catalog = build_catalog(inventory)
        with self.assertRaises(InterruptedError):
            inspect_conflicts(catalog, lambda: True)
        self.assertEqual(inventory, before)

    def test_metadata_limit_and_markup_and_no_config_secrets(self):
        folder = self.root / "Untrusted"
        folder.mkdir()
        (folder / "manifest.json").write_text(json.dumps({"name": "<b>Test</b>", "description": "<img src='https://bad'>Readable description",
            "author": "Creator", "apiKey": "DO-NOT-EXPORT", "website": "file:///etc/passwd"}))
        entry = ModEntry("one", "Untrusted", str(folder), "Custom", "Unknown", kind="mod")
        inspect_metadata(entry)
        self.assertEqual(entry.name, "Test")
        self.assertEqual(entry.description, "Readable description")
        self.assertFalse(entry.page)
        self.assertNotIn("DO-NOT-EXPORT", repr(entry))
        with self.assertRaises(ValueError):
            text_file(folder / "manifest.json", 5)

    def test_fomod_and_addon_notes_and_readme(self):
        for name in ("Fomod", "Addon", "Readme"):
            (self.root / name).mkdir()
        (self.root / "Fomod" / "fomod").mkdir()
        (self.root / "Fomod" / "fomod" / "info.xml").write_text("<fomod><Name>Castle</Name><Description>A restored castle.</Description><Version>3</Version></fomod>")
        (self.root / "Addon" / "Addon.toc").write_text("## Title: Better UI\n## Notes: Resizes the map.\n## Author: Map maker\n## Dependencies: LibMaps\n")
        (self.root / "Readme" / "README.md").write_text("# Heading\n\nAdds configurable weather effects.\n")
        entries = []
        for name in ("Fomod", "Addon", "Readme"):
            entry = ModEntry(name, name, str(self.root / name), "Custom", "Unknown")
            inspect_metadata(entry)
            entries.append(entry)
        self.assertEqual(entries[0].description, "A restored castle.")
        self.assertEqual(entries[1].dependencies, [Dependency("LibMaps")])
        self.assertIn("weather effects", entries[2].description)

    def test_declared_hosts_and_optional_dependencies_not_missing_mods(self):
        inventory, storage, profiles, _ = mo2_fixture(self.root)
        manifest = storage / "MountainTextures" / "manifest.json"
        manifest.write_text(json.dumps({"name": "Mountains", "dependencies": ["? optionalMod", "base >= 1.0", "java >= 17"]}))
        (profiles / "Default" / "modlist.txt").write_text("+MountainTextures\n")
        report = inspect_conflicts(build_catalog(inventory))
        self.assertFalse(any(f.kind == "Required dependency not enabled" for f in report.findings))
        self.assertEqual(len([f for f in report.findings if f.kind == "Requirement unverified"]), 2)

    def test_numeric_versions_and_unknown_syntax(self):
        for actual, requirement, expected in (("1.10", ">=1.2", True), ("1.0", ">=2", False),
            ("v2.0", "2", True), ("2.0-beta", ">=1", None), ("1", "^1.0", None), ("1", "*", True)):
            self.assertIs(version_satisfies(actual, requirement), expected)

    def test_enabled_dependency_version_is_checked(self):
        inventory, _, profiles, _ = mo2_fixture(self.root)
        (profiles / "Default" / "modlist.txt").write_text("+MountainTextures\n+Framework\n")
        report = inspect_conflicts(build_catalog(inventory))
        self.assertTrue(any(f.kind == "Dependency version mismatch" for f in report.findings))

    def test_no_profiles_is_explicitly_limited(self):
        report = inspect_conflicts(Catalog())
        self.assertTrue(report.limited)
        self.assertTrue(report.warnings)

    def test_directory_and_file_budgets_report_partial_coverage(self):
        inventory, *_ = mo2_fixture(self.root)
        with patch("gg_desktop.mods_data.MAX_MODS", 3):
            catalog = build_catalog(inventory)
        self.assertTrue(catalog.limited)
        catalog = build_catalog(inventory)
        with patch("gg_desktop.mod_conflicts.MAX_PATHS", 1):
            report = inspect_conflicts(catalog)
        self.assertTrue(report.limited)
        self.assertTrue(any("bounded" in w for w in report.warnings))

    def test_symlinks_and_linked_metadata_are_not_read(self):
        inventory, storage, _, _ = mo2_fixture(self.root)
        secret = self.root / "secret.json"
        secret.write_text('{"description":"MUST-NOT-READ"}')
        link = storage / "MountainTextures" / "modinfo.json"
        try:
            link.symlink_to(secret)
            (storage / "LinkedMod").symlink_to(storage / "SnowTextures", target_is_directory=True)
        except OSError:
            self.skipTest("Symlink privilege unavailable")
        with self.assertRaises(ValueError):
            text_file(link)
        catalog = build_catalog(inventory)
        self.assertFalse(any(e.path.endswith("LinkedMod") for e in catalog.entries))
        self.assertNotIn("MUST-NOT-READ", repr(catalog))

    def test_source_page_validation_and_workshop_links(self):
        self.assertTrue(mod_page("https://www.nexusmods.com/skyrimspecialedition/mods/1"))
        self.assertTrue(mod_page("https://steamcommunity.com/sharedfiles/filedetails/?id=12345"))
        for value in ("javascript:alert(1)", "https://nexusmods.com.evil/a", "https://u:p@github.com/a", "https://github.com/a?secret=1", "file:///tmp/a"):
            self.assertFalse(mod_page(value))
        workshop = self.root / "workshop"
        (workshop / "12345").mkdir(parents=True)
        row = ModFolder("Workshop", str(workshop), str(self.root), "Protected", (), 0, 0, False, "Steam Workshop")
        catalog = build_catalog(Inventory(mods=[row]))
        node = next(e for e in catalog.entries if e.kind == "mod")
        self.assertEqual(node.page, "https://steamcommunity.com/sharedfiles/filedetails/?id=12345")

    def test_vortex_snapshot_rules_and_stale_state(self):
        manager = self.root / "Vortex"
        staging = manager / "skyrimse" / "mods"
        for name in ("stage-one", "stage-two"):
            (staging / name).mkdir(parents=True)
        backup = manager / "temp" / "state_backups_full" / "manual.json"
        backup.parent.mkdir(parents=True)
        data = {"persistent": {"profiles": {"p1": {"gameId": "skyrimse", "name": "Primary", "modState": {"one": {"enabled": True}, "two": {"enabled": True}}}},
            "mods": {"skyrimse": {"one": {"installationPath": "stage-one", "attributes": {"modName": "One", "description": "Local snapshot description", "apiKey": "SECRET"},
                "rules": [{"type": "conflicts", "reference": {"id": "two"}}, {"type": "requires", "reference": {"id": "absent"}}]},
                "two": {"installationPath": "stage-two"}}}}}
        backup.write_text(json.dumps(data))
        stale = time.time() - 10 * 86400
        os.utime(backup, (stale, stale))
        row = ModFolder("Vortex", str(staging), str(manager), "Vortex: mod staging", (), 0, 0, False, "Vortex")
        catalog = build_catalog(Inventory(mods=[row]))
        self.assertTrue(catalog.profiles[0].stale)
        report = inspect_conflicts(catalog)
        self.assertTrue(report.limited)
        self.assertTrue(any(f.kind == "Declared manager incompatibility" for f in report.findings))
        self.assertTrue(any(f.kind == "Required dependency not enabled" for f in report.findings))
        exported = json.dumps(report.export(catalog))
        self.assertNotIn("SECRET", exported)
        self.assertIn("Local snapshot description", exported)

    def test_vortex_live_database_is_never_opened(self):
        staging = self.root / "Vortex" / "skyrimse" / "mods"
        staging.mkdir(parents=True)
        (staging.parent.parent / "State.v2").mkdir()
        row = ModFolder("Vortex", str(staging), str(staging.parent.parent), "Vortex: mod staging", (), 0, 0, False, "Vortex")
        catalog = build_catalog(Inventory(mods=[row]))
        self.assertTrue(catalog.limited)
        self.assertTrue(any("live State.v2 was not opened" in w for w in catalog.warnings))

    def test_metadata_does_not_assume_unknown_description(self):
        folder = self.root / "NoMetadata"
        folder.mkdir()
        entry = ModEntry("x", "NoMetadata", str(folder), "Test", "Unknown")
        inspect_metadata(entry)
        self.assertTrue(entry.description.startswith("No description"))
        self.assertEqual(entry.version, "Unknown")

    def test_local_case_variants_overlap_but_documentation_does_not(self):
        inventory, storage, profiles, _ = mo2_fixture(self.root)
        (profiles / "Default" / "modlist.txt").write_text("+MountainTextures\n+SnowTextures\n")
        original = storage / "SnowTextures" / "textures" / "mountain.dds"
        original.rename(original.with_name("MOUNTAIN.DDS"))
        for name in ("MountainTextures", "SnowTextures"):
            (storage / name / "README.md").write_text("Repeated docs")
        report = inspect_conflicts(build_catalog(inventory))
        self.assertEqual([f.count for f in report.findings if f.kind.startswith("File overlap")], [1])

    def test_fabric_wildcard_dependencies_keep_their_ids(self):
        folder = self.root / "FabricMod"
        folder.mkdir()
        (folder / "fabric.mod.json").write_text(json.dumps({"id": "localmod", "depends": {"minecraft": "*", "fabric-api": ">=1.0"}}))
        entry = ModEntry("one", "Local", str(folder), "Custom", "Unknown")
        inspect_metadata(entry)
        self.assertEqual(entry.dependencies, [Dependency("minecraft", "*"), Dependency("fabric-api", ">=1.0")])

    def test_steam_mod_markers_reveal_packages_without_executing_them(self):
        game = self.root / "Game"
        mod = game / "Mods" / "Example"
        mod.mkdir(parents=True)
        (mod / "manifest.json").write_text('{"name":"Example","description":"Adjustable local map."}')
        (game / "Mods" / "Packed.jar").write_bytes(b"not executed or unpacked")
        row = ModFolder("Game", str(game), str(self.root), "Installed: possible mods", ("mods", "../outside"), 100, 1, False)
        catalog = build_catalog(Inventory(mods=[row]))
        self.assertEqual(len(catalog.entries), 3)
        self.assertTrue(any(e.description == "Adjustable local map." for e in catalog.entries))
        self.assertTrue(any("Packed contents" in e.description for e in catalog.entries))

    def test_custom_library_is_not_verified_game_ownership(self):
        inventory, *_ = mo2_fixture(self.root)
        from dataclasses import replace
        inventory.games = [replace(inventory.games[0], launcher="Custom library", capabilities=("inspect",), claimed_by=("Custom library",))]
        self.assertTrue(all(not e.game_key for e in build_catalog(inventory).entries))

    def test_declared_incompatibility_respects_numeric_version_condition(self):
        inventory, storage, profiles, _ = mo2_fixture(self.root)
        (storage / "MountainTextures" / "manifest.json").write_text(json.dumps({"name": "Mountains", "breaks": {"snow": "<2.0"}}))
        (profiles / "Default" / "modlist.txt").write_text("+MountainTextures\n+SnowTextures\n")
        catalog = build_catalog(inventory)
        self.assertTrue(any(f.kind == "Declared incompatibility" for f in inspect_conflicts(catalog).findings))
        next(e for e in catalog.entries if e.name == "Snow Textures").version = "3.0"
        self.assertFalse(any(f.kind == "Declared incompatibility" for f in inspect_conflicts(catalog).findings))

    def test_mo2_storage_remains_browsable_without_accepted_profiles(self):
        inventory, storage, *_ = mo2_fixture(self.root)
        inventory.mods = inventory.mods[:1]
        catalog = build_catalog(inventory)
        self.assertTrue(catalog.limited)
        self.assertFalse(catalog.profiles)
        self.assertTrue(any(e.path == str(storage / "MountainTextures") for e in catalog.entries))

    def test_shared_mo2_storage_with_conflicting_games_has_no_dna_guess(self):
        from dataclasses import replace
        inventory, _, _, ini = mo2_fixture(self.root)
        other_game = self.root / "OtherGame"
        other_game.mkdir()
        inventory.games.append(replace(inventory.games[0], key="other", install_path=str(other_game)))
        other_ini = ini.with_name("OtherInstance.ini")
        other_ini.write_text(ini.read_text().replace(inventory.games[0].install_path, str(other_game)))
        for row in inventory.mods:
            row.indicators += ("MO2 INI: " + str(other_ini),)
        catalog = build_catalog(inventory)
        self.assertTrue(all(not e.game_key for e in catalog.entries))
        self.assertEqual(len(catalog.profiles), 2)
        self.assertTrue(catalog.limited)


if __name__ == "__main__":
    unittest.main()
