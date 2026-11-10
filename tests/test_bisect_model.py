import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from gg_desktop import bisect_apply as real_apply
from gg_desktop import bisect_clues as bcl
from gg_desktop import bisect_model as bm
from gg_desktop.bisect_core import Unit

NOW = 1_800_000_000.0
DAY = 86400.0


def units(n=24):
    return [Unit(f"m{i}", f"Mod {i}", added=NOW - (50 - i) * DAY, kind="code" if i % 6 == 0 else "assets")
            for i in range(n)]


class FakeApply:
    """Stands in for the file writer: records what would be written."""
    COPY = staticmethod(real_apply.copy_name)
    ApplyError = real_apply.ApplyError

    def __init__(self, own_saves=False, fail=None):
        self.own_saves, self.fail, self.calls = own_saves, fail, []

    def keeps_own_saves(self, folder):
        return self.own_saves

    def copy_name(self, name):
        return real_apply.copy_name(name)

    def make_copy(self, folder):
        self.calls.append(("copy", str(folder)))
        return real_apply.CopyInfo(Path("/profiles/GG Bisect - Default"), "Default", 0.0)

    def write_test(self, folder, names):
        if self.fail:
            raise real_apply.ApplyError(self.fail)
        self.calls.append(("write", sorted(names)))
        return list(names)


def mo2(folder="/profiles/Default"):
    return bm.ProfileInfo("MO2:p", "Default", "Mod Organizer 2", Path(folder), "Skyrim", "C:/Games/Skyrim")


def vortex():
    return bm.ProfileInfo("V:p", "Main", "Vortex", None, "Skyrim")


def loaded(root, profile=None, fake=None, us=None):
    model = bm.Model(Path(root), now=lambda: NOW, apply_module=fake or FakeApply())
    model.sync(profile or mo2(), 1)
    model.loaded_at = NOW
    model.load_done((us or units(), {}, ["Install dates are when each mod's folder was created."]), "")
    return model


def run(model, truth, limit=200):
    for _ in range(limit):
        if model.flow.done():
            return model.flow.step()
        step = model.flow.step()
        if model.profile.can_write:
            work = model.apply_job()
            model.apply_done(work(), "")
        crashed = truth <= step.on_keys
        assert model.answer("crash" if crashed else "ok")
    raise AssertionError("no verdict")


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name


class Setup(Case):
    def test_panel_before_anything_is_loaded(self):
        model = bm.Model(Path(self.root), now=lambda: NOW)
        self.assertEqual(model.panel().stage, "unavailable")
        self.assertIn("Scan for Mods", model.notice())
        model.sync(mo2(), 1)
        self.assertEqual(model.panel().stage, "loading")
        self.assertIn("Reading", model.notice())

    def test_setup_panel_explains_clues_and_offers_the_buttons(self):
        model = loaded(self.root)
        panel = model.panel()
        self.assertEqual(panel.stage, "setup")
        keys = {b.key for b in panel.buttons}
        self.assertTrue({"use_checked", "pick_pack", "always_on", "read_reports", "start"} <= keys)
        self.assertEqual([f.key for f in panel.fields], ["last", "started"])
        self.assertEqual(panel.toggles[0].key, "sometimes")
        text = " ".join(t for _, t in panel.lines)
        self.assertIn("Your own profile is never changed", text)
        self.assertIn("GG Bisect - Default", text)
        self.assertNotIn("safe", text.lower())

    def test_other_managers_get_a_list_not_a_write(self):
        model = loaded(self.root, vortex())
        self.assertIn("shows exactly which mods to turn on", " ".join(t for _, t in model.panel().lines))
        self.assertTrue(model.start())
        keys = {b.key for b in model.panel().buttons}
        self.assertTrue({"copy_list", "save_list"} <= keys)
        self.assertNotIn("build", keys)

    def test_a_profile_with_its_own_saves_cannot_start(self):
        model = loaded(self.root, fake=FakeApply(own_saves=True))
        self.assertIn("keeps its own saves", " ".join(t for _, t in model.panel().lines))
        self.assertFalse(model.start())
        start = [b for b in model.panel().buttons if b.key == "start"][0]
        self.assertFalse(start.enabled)

    def test_a_date_that_cannot_be_read_blocks_start_and_says_how_to_type_it(self):
        model = loaded(self.root)
        model.set_field("last", "back when it was fun")
        text = " ".join(t for _, t in model.panel().lines)
        self.assertIn("It last worked", text)
        self.assertIn("2 weeks ago", text)
        self.assertFalse(model.start())
        model.set_field("last", "2 weeks ago")
        self.assertTrue(model.start())

    def test_clues_change_the_table_order_not_the_answer(self):
        model = loaded(self.root)
        before = [r.name for r in model.rows()]
        model.set_field("last", "10 days ago")
        after = [r.name for r in model.rows()]
        self.assertNotEqual(before, after)
        self.assertEqual(set(before), set(after))

    def test_picks_are_validated_and_cleared(self):
        model = loaded(self.root)
        model.use_hints(["m3", "ghost"])
        self.assertEqual(model.hints, ("m3",))
        model.mark_always_on(["m3", "m5", "nope"])
        self.assertEqual(model.always_on, ("m3", "m5"))
        self.assertEqual(model.hints, ())
        model.clear_hints()
        model.clear_always_on()
        self.assertEqual((model.hints, model.always_on), ((), ()))

    def test_switching_profile_clears_picks_but_keeps_the_dates_typed(self):
        model = loaded(self.root)
        model.set_field("last", "last week")
        model.use_hints(["m1"])
        model.sync(vortex(), 1)
        self.assertEqual(model.hints, ())
        self.assertEqual(model.last_text, "last week")
        self.assertTrue(model.loading)

    def test_pack_choices_list_mods_installed_together(self):
        pack = [Unit(f"p{i}", f"Pack {i}", added=NOW - 3 * DAY + i * 30) for i in range(9)]
        model = loaded(self.root, us=units(6) + pack)
        label, keys = model.pack_choices()[0]
        self.assertEqual(len(keys), 9)

    def test_crash_report_clues_show_up_and_a_failed_read_is_reported(self):
        model = loaded(self.root)
        model.reports_job(lambda u, f, p: None)
        self.assertEqual(model.reports_state, "reading")
        model.reports_done(None, "boom")
        self.assertIn("could not be read", model.message)
        clues = bcl.Clues(hits={"m3": 2}, reports_read=4, notes=("a note",))
        model.reports_done((clues, 4), "")
        text = " ".join(t for _, t in model.panel().lines)
        self.assertIn("4 read, 1 mods named", text)

    def test_load_failure_is_shown(self):
        model = bm.Model(Path(self.root), now=lambda: NOW)
        model.sync(mo2(), 1)
        model.load_done(None, "disk gone")
        self.assertIn("could not be read", model.message)


class Testing(Case):
    def test_mo2_flow_requires_building_each_test_before_answering(self):
        fake = FakeApply()
        model = loaded(self.root, fake=fake)
        self.assertTrue(model.start())
        self.assertEqual(model.panel().stage, "testing")
        crash = [b for b in model.panel().buttons if b.key == "crash"][0]
        self.assertFalse(crash.enabled)
        self.assertFalse(model.answer("crash"))
        self.assertIn("Build this test first", model.message)
        model.apply_done(model.apply_job()(), "")
        self.assertTrue([b for b in model.panel().buttons if b.key == "crash"][0].enabled)
        self.assertIn("Ready.", " ".join(t for _, t in model.panel().lines))
        self.assertEqual([c[0] for c in fake.calls], ["copy", "write"])
        self.assertEqual(len(fake.calls[1][1]), 24)
        self.assertTrue(model.answer("crash"))
        self.assertEqual(model.applied, 0)
        self.assertFalse([b for b in model.panel().buttons if b.key == "crash"][0].enabled)

    def test_a_write_problem_is_shown_and_nothing_is_answered(self):
        model = loaded(self.root, fake=FakeApply(fail="Mod Organizer 2 is running."))
        model.start()
        work = model.apply_job()
        try:
            work()
        except real_apply.ApplyError as exc:
            model.apply_done(None, str(exc))
        self.assertIn("is running", model.message)
        self.assertIn("is running", " ".join(t for _, t in model.panel().lines))
        self.assertFalse(model.answer("crash"))

    def test_the_whole_search_finds_the_right_mods_and_reports(self):
        model = loaded(self.root)
        model.start()
        verdict = run(model, {"m4", "m17"})
        self.assertEqual(set(verdict.keys), {"m4", "m17"})
        panel = model.panel()
        self.assertEqual(panel.stage, "done")
        text = " ".join(t for _, t in panel.lines)
        self.assertIn("Mod 4", text)
        self.assertIn("changed nothing in your own profile", text)
        self.assertNotIn("safe", text.lower())
        self.assertEqual({r.status for r in model.rows() if r.key in ("m4", "m17")}, {"Cause"})
        self.assertIn("Cause", {r.status for r in model.rows()})

    def test_manual_managers_search_works_and_gives_the_list(self):
        model = loaded(self.root, vortex())
        model.start()
        self.assertIn("Turn ON these", model.copy_text_for_step())
        verdict = run(model, {"m9"})
        self.assertEqual(verdict.keys, ("m9",))

    def test_a_search_survives_closing_the_app(self):
        model = loaded(self.root)
        model.set_field("last", "30 days ago")
        model.start()
        truth = {"m8"}
        for _ in range(5):
            step = model.flow.step()
            model.apply_done(model.apply_job()(), "")
            model.answer("crash" if truth <= step.on_keys else "ok")
        answered = model.flow.answers
        again = loaded(self.root)
        self.assertEqual(again.flow.answers, answered)
        self.assertEqual(again.panel().stage, "testing")
        self.assertIn("Continuing", again.message)
        again.apply_done(again.apply_job()(), "")
        self.assertEqual(set(run(again, truth).keys), truth)

    def test_a_search_for_changed_mods_is_dropped_with_a_reason(self):
        model = loaded(self.root)
        model.start()
        model.apply_done(model.apply_job()(), "")
        model.answer("crash")
        changed = units()
        changed[2] = Unit("m2", "Mod 2", added=NOW - 1 * DAY)
        again = loaded(self.root, us=changed)
        self.assertIsNone(again.flow)
        self.assertIn("An earlier search was dropped", again.message)
        self.assertIsNone(bm.store.load(Path(self.root), "MO2:p"))

    def test_undo_not_sure_and_stop(self):
        model = loaded(self.root, vortex())
        model.start()
        self.assertFalse(model.undo())
        step = model.flow.step()
        self.assertTrue(model.answer("unsure"))
        self.assertEqual(model.flow.step(), step)
        self.assertTrue(model.answer("crash"))
        self.assertTrue(model.undo())
        self.assertEqual(model.flow.step(), step)
        model.stop()
        self.assertIsNone(model.flow)
        self.assertEqual(model.panel().stage, "setup")
        self.assertIsNone(bm.store.load(Path(self.root), "V:p"))

    def test_done_panel_offers_undo_for_a_wrong_tap_and_start_over(self):
        model = loaded(self.root, vortex())
        model.start()
        run(model, {"m2"})
        buttons = {b.key: b for b in model.panel().buttons}
        self.assertTrue(buttons["undo"].enabled)
        self.assertTrue(model.undo())
        self.assertEqual(model.panel().stage, "testing")
        run(model, {"m2"})
        model.restart()
        self.assertEqual(model.panel().stage, "setup")

    def test_report_is_saved_in_game_graves_own_folder(self):
        model = loaded(self.root, vortex())
        model.start()
        run(model, {"m2"})
        path = model.save_report()
        self.assertTrue(path.is_file())
        self.assertIn(str(Path(self.root) / "bisect" / "reports"), str(path))
        text = path.read_text(encoding="utf-8")
        self.assertIn("Profile: Main", text)
        self.assertIn("Mod 2", text)

    def test_outside_verdict_reads_as_not_a_mod(self):
        model = loaded(self.root, vortex())
        model.start()
        run(model, set())  # crashes only when everything is on? set() <= anything => always crashes
        panel = model.panel()
        text = " ".join(t for _, t in panel.lines)
        self.assertIn("Not a mod", text)


if __name__ == "__main__":
    unittest.main()
