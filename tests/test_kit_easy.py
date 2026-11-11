"""Easy Resurrection Kit planning: what is offered for one game, and only from proof."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import kit_easy
import resurrection_v2 as kit


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        profile = self.root / "User"
        self.env = {"USERPROFILE": str(profile), "LOCALAPPDATA": str(profile / "AppData" / "Local"),
                    "APPDATA": str(profile / "AppData" / "Roaming")}
        steamapps = self.root / "Steam" / "steamapps"
        self.install = steamapps / "common" / "Skyrim Special Edition"
        (self.install / "Data").mkdir(parents=True)
        (self.install / "SkyrimSE.exe").write_bytes(b"m" * 100)
        (self.install / "Data" / "a.esp").write_bytes(b"a" * 50)
        (steamapps / "appmanifest_489830.acf").write_text("x")
        self.game = SimpleNamespace(name="The Elder Scrolls V: Skyrim Special Edition", launcher="Steam", app_id="489830",
                                    install_path=str(self.install), install_evidence="Steam manifest")
        self.saves = profile / "Documents" / "My Games" / "Skyrim Special Edition" / "Saves"
        self.saves.mkdir(parents=True)
        (self.saves / "s.ess").write_bytes(b"s" * 10)
        plugins = Path(self.env["LOCALAPPDATA"]) / "Skyrim Special Edition"
        plugins.mkdir(parents=True)
        (plugins / "plugins.txt").write_text("*a.esp\n")

    def roles(self, plan):
        return [p.role for p in plan.parts]

    def test_whole_install_manifest_load_order_come_with_the_game(self):
        plan = kit_easy.build_plan(self.game, environ=self.env)
        self.assertEqual(self.roles(plan), ["Game", "Launcher", "LoadOrder"])
        game = plan.parts[0]
        self.assertEqual((game.files, game.bytes), (2, 150))
        self.assertEqual(plan.parts[2].origin, "%LOCALAPPDATA%\\Skyrim Special Edition")

    def test_saves_only_from_the_scanner_label_or_an_owner_link(self):
        near = SimpleNamespace(game="Skyrim Special", path=str(self.saves))
        self.assertNotIn("Saves", self.roles(kit_easy.build_plan(self.game, saves=[near], environ=self.env)))
        exact = SimpleNamespace(game=self.game.name, path=str(self.saves))
        plan = kit_easy.build_plan(self.game, saves=[exact], environ=self.env)
        saves = next(p for p in plan.parts if p.role == "Saves")
        self.assertIn("save scanner", saves.why)
        self.assertEqual(saves.origin, "%DOCUMENTS%\\My Games\\Skyrim Special Edition\\Saves")
        linked = kit_easy.build_plan(self.game, links=[{"category": "Saves", "path": str(self.saves)}], environ=self.env)
        self.assertIn("You linked", next(p for p in linked.parts if p.role == "Saves").why)
        self.assertTrue(any("Saves are never matched by name" in n for n in kit_easy.build_plan(self.game, environ=self.env).notes))

    def test_folders_inside_the_install_are_not_offered_twice(self):
        inside = self.install / "Data"
        plan = kit_easy.build_plan(self.game, links=[{"category": "Mods / Addons", "path": str(inside)}], environ=self.env)
        self.assertNotIn("Mods", self.roles(plan))

    def test_mo2_profile_and_mods_from_verified_discovery(self):
        profile, mods = self.root / "MO2" / "profiles" / "Default", self.root / "MO2" / "mods"
        profile.mkdir(parents=True)
        mods.mkdir()
        (profile / "modlist.txt").write_text("+A\n")
        (mods / "A").mkdir()
        (mods / "A" / "a.esp").write_bytes(b"1")
        discovery = {"candidates": [
            {"role": "Profiles", "path": str(profile), "evidence": "Exact MO2 gamePath match", "default": True, "manager": "MO2", "profile": "Default"},
            {"role": "Mods", "path": str(mods), "evidence": "MO2 configured installed-mod storage", "default": True, "manager": "MO2"}]}
        plan = kit_easy.build_plan(self.game, discovery=discovery, environ=self.env)
        sources, origins, manager = kit_easy.to_sources(plan)
        self.assertEqual(set(sources), {"Game", "Launcher", "LoadOrder", "Profiles", "Mods"})
        self.assertEqual(manager["kind"], "MO2")
        self.assertEqual(manager["profile"], "Default")

    def test_links_in_the_install_block_that_part_only(self):
        try:
            (self.install / "Data" / "Link").symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available here")
        plan = kit_easy.build_plan(self.game, environ=self.env)
        game = plan.parts[0]
        self.assertTrue(game.problem)
        self.assertNotIn("Game", kit_easy.to_sources(plan)[0])

    def test_to_sources_feeds_the_engine_end_to_end(self):
        plan = kit_easy.build_plan(self.game, saves=[SimpleNamespace(game=self.game.name, path=str(self.saves))], environ=self.env)
        sources, origins, manager = kit_easy.to_sources(plan)
        out = self.root / "Kits"
        out.mkdir()
        made = kit.create_complete_kit(self.game.name, sources, out / "k.zip", manager, origins=origins)
        self.assertEqual(set(made["roles"]), {"Game", "Launcher", "Saves", "LoadOrder"})
        self.assertEqual(made["files"], 2 + 1 + 1 + 1)

    def test_unticked_parts_are_left_out_and_sizes_follow(self):
        plan = kit_easy.build_plan(self.game, environ=self.env)
        plan.parts[0].on = False
        self.assertNotIn("Game", kit_easy.to_sources(plan)[0])
        self.assertEqual(plan.total_bytes, plan.parts[1].bytes + plan.parts[2].bytes)

    def test_destination_names_never_collide(self):
        first = kit_easy.default_destination("Skyrim: SE?", self.root)
        self.assertEqual(first.name, "Skyrim_ SE Kit.zip")
        first.write_text("x")
        self.assertEqual(kit_easy.default_destination("Skyrim: SE?", self.root).name, "Skyrim_ SE Kit 2.zip")

    def test_readiness(self):
        plan = kit_easy.build_plan(self.game, environ=self.env)
        self.assertTrue(kit_easy.readiness(plan, self.root)["ok"])
        for p in plan.parts:
            p.on = False
        self.assertFalse(kit_easy.readiness(plan, self.root)["ok"])
        plan.parts[0].on = True
        plan.parts[0].bytes = 1 << 60
        self.assertIn("free space", kit_easy.readiness(plan, self.root)["why"])

    def test_templatize_never_keeps_a_user_name(self):
        self.assertIsNone(kit_easy.templatize(self.root / "Elsewhere", self.env))
        self.assertEqual(kit_easy.templatize(Path(self.env["APPDATA"]) / "X" / "Y", self.env), "%APPDATA%\\X\\Y")


if __name__ == "__main__":
    unittest.main()


class Overlap(PlanTests):
    def test_settings_folder_that_contains_the_saves_is_not_a_second_part(self):
        parent = self.saves.parent
        plan = kit_easy.build_plan(self.game, environ=self.env,
                                   links=[{"category": "Saves", "path": str(self.saves)},
                                          {"category": "Configs / Settings", "path": str(parent)}])
        configs = next(p for p in plan.parts if p.role == "Configs")
        self.assertIn("overlaps", configs.problem)
        sources, origins, manager = kit_easy.to_sources(plan)
        self.assertNotIn("Configs", sources)
        out = self.root / "K"
        out.mkdir()
        kit.create_complete_kit(self.game.name, sources, out / "k.zip", manager, origins=origins)

    def test_an_empty_folder_is_not_offered_as_a_part(self):
        empty = self.root / "EmptySaves"
        empty.mkdir()
        plan = kit_easy.build_plan(self.game, environ=self.env, links=[{"category": "Saves", "path": str(empty)}])
        saves = next(p for p in plan.parts if p.role == "Saves")
        self.assertIn("no files", saves.problem)
        self.assertNotIn("Saves", kit_easy.to_sources(plan)[0])

    def test_gog_copy_uses_its_own_load_order_folder(self):
        gog = Path(self.env["LOCALAPPDATA"]) / "Skyrim Special Edition GOG"
        gog.mkdir()
        (gog / "plugins.txt").write_text("*gog.esp\n")
        self.game.launcher = "GOG"
        plan = kit_easy.build_plan(self.game, environ=self.env)
        part = next(p for p in plan.parts if p.role == "LoadOrder")
        self.assertEqual(part.origin, "%LOCALAPPDATA%\\Skyrim Special Edition GOG")
        self.assertNotIn("Launcher", [p.role for p in plan.parts])
