import unittest
from datetime import datetime
from types import SimpleNamespace as NS

from gg_desktop import autopilot_core as core
from gg_desktop import autopilot_run as run
from gg_desktop import fixgame_core as fx


def env(**kw):
    base = dict(runner=None, games=lambda: [NS(name="Elden Ring", launcher="Steam", app_id="1245620",
                                                install_path=r"C:\Steam\common\ELDEN RING")],
                game_crashes=lambda g: [NS(when=datetime(2026, 11, 14, 21, 5), module="nvwgf2umx.dll")] * 2,
                list_processes=lambda r: [NS(name="RTSS.exe", pid=7, kb=1000), NS(name="chrome.exe", pid=8, kb=10)],
                read_runtimes=lambda: (True, False, True), log=lambda *a: None, opened=[],
                search_updates=lambda: [], cache={})
    base.update(kw)
    e = NS(**base)
    e.open_url = e.opened.append
    e.install_vcredist = lambda: 0
    return e


class FixGame(unittest.TestCase):
    def test_requests(self):
        self.assertTrue(fx.wants_fix("elden ring keeps crashing"))
        self.assertTrue(fx.wants_fix("my game won't launch"))
        self.assertFalse(fx.wants_fix("turn off the crash fix mod"))
        self.assertFalse(fx.wants_fix("clean my temp files"))

    def test_check_finds_causes_and_offers_fixes(self):
        plan = core.plan_for("Elden Ring keeps crashing, fix it")
        e = env()
        run.prepare(plan, e)
        check = plan.steps[0]
        self.assertEqual(check.status, "done")
        self.assertIn("2 crashes", check.result)
        self.assertIn("NVIDIA graphics driver", check.result)
        self.assertIn("RivaTuner", check.result)
        self.assertIn("32-bit", check.result)
        keys = [s.key for s in plan.steps]
        self.assertIn("verify_game", keys)
        self.assertIn("install_vcredist", keys)
        close = next(s for s in plan.steps if s.key == "close_app")
        self.assertFalse(close.ticked, "overlays are offered, never ticked for you")
        self.assertNotIn("safe", check.result.lower())

    def test_fixes_run(self):
        e = env()
        step = core.Step("verify_game", {"name": "Elden Ring", "url": "steam://validate/1245620"})
        run.run_change(step, e)
        self.assertEqual(e.opened, ["steam://validate/1245620"])
        bad = run.run_change(core.Step("verify_game", {"url": "https://evil"}), e)
        self.assertEqual(bad.status, "problem")
        done = run.run_change(core.Step("install_vcredist", {}), e)
        self.assertEqual(done.status, "done")

    def test_no_game_named_and_other_launchers(self):
        plan = core.plan_for("my game won't start")
        run.prepare(plan, env(read_runtimes=lambda: (True, True, True), list_processes=lambda r: []))
        self.assertIn("Name the game", plan.steps[0].result)
        self.assertEqual([s.key for s in plan.steps], ["check_game_fix", "check_drivers"])
        self.assertIn("Epic", fx.verify_words(NS(launcher="Epic", app_id="")))
        self.assertTrue(fx.safe_download("https://aka.ms/vs/17/release/vc_redist.x64.exe"))
        self.assertFalse(fx.safe_download("http://aka.ms/x"))
        self.assertFalse(fx.safe_download("https://example.com/vc_redist.exe"))


if __name__ == "__main__":
    unittest.main()
