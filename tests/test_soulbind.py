import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

from gg_desktop import soulbind_core as sb

SKYRIM = ("[General]\r\nsLanguage=ENGLISH\r\n[Controls]\r\nbInvertYValues=0\r\nfMouseHeadingYScale=0.0200\r\n"
          "[Display]\r\nfDefaultWorldFOV=75.0000\r\nfOther=1\r\n")
MINECRAFT = "version:3465\ninvertYMouse:false\nbobView:true\nshowSubtitles:false\ntoggleSprint:false\nscreenEffectScale:1.0\nfov:0.0\n"


class SoulbindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.logged = []

    def log(self, kind, details, **kw):
        self.logged.append((kind, details, kw))

    def test_profile_is_cleaned(self):
        profile = sb.clean_profile({"fov": 200, "invert_y": True, "evil": 1, "subtitles": "yes", "screen_effects": "off"})
        self.assertEqual(profile, {"invert_y": True, "screen_effects": "off"})
        self.assertEqual(sb.clean_profile("junk"), {})

    def test_code_round_trip_and_rejects_junk(self):
        profile = {"invert_y": True, "fov": 100, "screen_effects": "reduced"}
        self.assertEqual(sb.read_code(sb.make_code(profile)), profile)
        for bad in ("", "hello", sb.CODE_PREFIX + "!!!", sb.CODE_PREFIX + "x" * 5000):
            with self.assertRaises(ValueError):
                sb.read_code(bad)
        with self.assertRaises(ValueError):
            sb.read_code(sb.make_code({}))

    def test_adapter_matching(self):
        self.assertEqual(sb.adapter_for("The Elder Scrolls V: Skyrim Special Edition").id, "skyrim-se")
        self.assertEqual(sb.adapter_for("Minecraft").id, "minecraft-java")
        self.assertIsNone(sb.adapter_for("Some Unknown Game"))

    def test_plan_only_counts_settings_found_in_the_file(self):
        adapter = sb.adapter_for("skyrim special edition")
        plan = sb.make_plan(adapter, SKYRIM, {"invert_y": True, "fov": 75, "subtitles": True})
        self.assertEqual([c.pref for c in plan.differing], ["invert_y"])
        self.assertEqual([c.pref for c in plan.matching], ["fov"])
        self.assertEqual(plan.unsupported, ("subtitles",))
        missing = SKYRIM.replace("bInvertYValues=0\r\n", "")
        self.assertEqual(sb.make_plan(adapter, missing, {"invert_y": True}).unsupported, ("invert_y",))

    def test_section_must_match(self):
        adapter = sb.adapter_for("skyrim special edition")
        wrong = "[Other]\nbInvertYValues=0\n"
        self.assertEqual(sb.make_plan(adapter, wrong, {"invert_y": True}).unsupported, ("invert_y",))

    def test_edit_changes_only_the_value(self):
        adapter = sb.adapter_for("skyrim special edition")
        edited = sb.apply_to_text(adapter, SKYRIM, {"invert_y": True, "fov": 90})
        self.assertEqual(edited, SKYRIM.replace("bInvertYValues=0", "bInvertYValues=1")
                         .replace("fDefaultWorldFOV=75.0000", "fDefaultWorldFOV=90.0000"))
        mc = sb.adapter_for("minecraft")
        edited = sb.apply_to_text(mc, MINECRAFT, {"invert_y": True, "screen_effects": "off", "subtitles": True})
        self.assertIn("invertYMouse:true", edited)
        self.assertIn("screenEffectScale:0.0", edited)
        self.assertIn("showSubtitles:true", edited)
        self.assertEqual(edited.count("\n"), MINECRAFT.count("\n"))

    def test_scores_never_overclaim(self):
        adapter = sb.adapter_for("minecraft")
        self.assertEqual(sb.score_for(None, 3).text, "Not supported")
        self.assertEqual(sb.score_for(None, 0).text, "No profile")
        plan = sb.make_plan(adapter, MINECRAFT, {"invert_y": False, "fov": 90})
        score = sb.score_for(plan, 2)
        self.assertEqual((score.text, score.tone), ("Soulbound", "green"))
        self.assertIn("not supported", score.detail)
        plan = sb.make_plan(adapter, MINECRAFT, {"invert_y": True})
        self.assertEqual(sb.score_for(plan, 1).text, "1 to apply")

    def test_apply_backs_up_logs_and_reverts(self):
        adapter = sb.adapter_for("skyrim special edition")
        game = self.root / "SkyrimPrefs.ini"
        game.write_bytes(SKYRIM.encode())
        profile = {"invert_y": True}
        done = sb.apply_profile(adapter, game, profile, root=self.root / "sb", log=self.log,
                                now=datetime(2026, 11, 9, 8, 0, 0))
        self.assertIn(b"bInvertYValues=1", game.read_bytes())
        self.assertEqual(Path(done.backup).read_bytes(), SKYRIM.encode())
        self.assertEqual(self.logged[0][0], "soulbind_apply")
        self.assertIsNone(sb.apply_profile(adapter, game, profile, root=self.root / "sb", log=self.log))
        sb.revert(done.entry_id, root=self.root / "sb", log=self.log)
        self.assertEqual(game.read_bytes(), SKYRIM.encode())
        with self.assertRaises(ValueError):
            sb.revert(done.entry_id, root=self.root / "sb", log=self.log)

    def test_default_logger_writes_the_real_activity_log(self):
        import core
        adapter = sb.adapter_for("skyrim special edition")
        game = self.root / "SkyrimPrefs.ini"
        game.write_bytes(SKYRIM.encode())
        with patch("core.config_dir", return_value=self.root / "cfg"):
            done = sb.apply_profile(adapter, game, {"invert_y": True}, root=self.root / "sb")
            sb.revert(done.entry_id, root=self.root / "sb")
            kinds = [e["kind"] for e in core.get_activity()]
        self.assertEqual(kinds, ["soulbind_revert", "soulbind_apply"])

    def test_revert_refuses_after_a_later_change(self):
        adapter = sb.adapter_for("skyrim special edition")
        game = self.root / "SkyrimPrefs.ini"
        game.write_bytes(SKYRIM.encode())
        done = sb.apply_profile(adapter, game, {"invert_y": True}, root=self.root / "sb", log=self.log)
        game.write_bytes(game.read_bytes() + b"; changed by the game\r\n")
        with self.assertRaises(ValueError):
            sb.revert(done.entry_id, root=self.root / "sb", log=self.log)
        self.assertIn(b"changed by the game", game.read_bytes())

    def test_bom_is_kept(self):
        adapter = sb.adapter_for("fallout 4")
        game = self.root / "Fallout4Prefs.ini"
        game.write_bytes(b"\xef\xbb\xbf" + SKYRIM.encode())
        sb.apply_profile(adapter, game, {"invert_y": True}, root=self.root / "sb", log=self.log)
        self.assertTrue(game.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_config_file_lookup_and_storage(self):
        docs = self.root / "docs"
        target = docs / "My Games" / "Skyrim Special Edition" / "SkyrimPrefs.ini"
        target.parent.mkdir(parents=True)
        target.write_text(SKYRIM)
        adapter = sb.adapter_for("skyrim special edition")
        self.assertEqual(sb.config_file(adapter, {"documents": [docs]}), target)
        self.assertIsNone(sb.config_file(adapter, {"documents": [self.root / "none"]}))
        sb.save_profile({"fov": 100, "bad": 1}, self.root / "store")
        self.assertEqual(sb.load_profile(self.root / "store"), {"fov": 100})


if __name__ == "__main__":
    unittest.main()


class MoreSettings(unittest.TestCase):
    OPTIONS = ("fovEffectScale:1.0\nparticles:0\nautoJump:false\nenableVsync:true\nmaxFps:260\nrenderDistance:12\n"
               "soundCategory_master:1.0\nsoundCategory_music:0.5\nunrelated:keep\n")

    def test_minecraft_takes_the_new_preferences_and_changes_only_those_lines(self):
        adapter = sb.adapter_for("Minecraft")
        profile = {"fov_effects": 25, "particles": "minimal", "auto_jump": True, "vsync": False, "max_fps": 120,
                   "render_distance": 16, "master_volume": 60, "music_volume": 0}
        plan = sb.make_plan(adapter, self.OPTIONS, profile)
        self.assertEqual(len(plan.differing), 8, plan)
        out = sb.apply_to_text(adapter, self.OPTIONS, profile)
        for line in ("fovEffectScale:0.25", "particles:2", "autoJump:true", "enableVsync:false", "maxFps:120",
                     "renderDistance:16", "soundCategory_master:0.60", "soundCategory_music:0.00", "unrelated:keep"):
            self.assertIn(line, out.split("\n"))
        again = sb.make_plan(adapter, out, profile)
        self.assertEqual(again.differing, ())

    def test_a_preference_a_game_does_not_have_is_unsupported_never_added(self):
        adapter = sb.adapter_for("Minecraft")
        plan = sb.make_plan(adapter, "unrelated:1\n", {"max_fps": 60, "always_run": True})
        self.assertEqual(plan.changes, ())
        self.assertEqual(sorted(plan.unsupported), ["always_run", "max_fps"])
        self.assertEqual(sb.apply_to_text(adapter, "unrelated:1\n", {"max_fps": 60}), "unrelated:1\n")

    def test_bethesda_keys_are_matched_only_when_the_file_really_has_them(self):
        adapter = sb.adapter_for("Skyrim Special Edition")
        text = "[Display]\niPresentInterval=1\nfDefaultWorldFOV=90.0000\n[Controls]\nbAlwaysRunByDefault=1\nbMouseAcceleration=1\n"
        plan = sb.make_plan(adapter, text, {"vsync": False, "always_run": True, "mouse_accel": False, "fov": 90})
        self.assertEqual(sorted(c.pref for c in plan.differing), ["mouse_accel", "vsync"])
        self.assertEqual(sorted(c.pref for c in plan.matching), ["always_run", "fov"])

    def test_number_values_show_their_unit_and_stay_in_range(self):
        pref = sb.PREF_BY_ID["master_volume"]
        self.assertEqual(sb.value_text(pref, 60), "60%")
        self.assertEqual(sb.value_text(sb.PREF_BY_ID["fov"], 90), "90°")
        with self.assertRaises(ValueError):
            sb.clean_value(pref, 101)
        self.assertEqual(sb.read_code(sb.make_code({"max_fps": 144, "particles": "all"})), {"max_fps": 144, "particles": "all"})
        self.assertEqual(set(p.group for p in sb.PREFS), set(sb.GROUPS))
