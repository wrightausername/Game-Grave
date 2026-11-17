import unittest

from gg_desktop import assistant_guide as guide


class Guide(unittest.TestCase):
    def test_starts_only_for_fixing(self):
        self.assertTrue(guide.starts("help me fix Hades"))
        self.assertTrue(guide.starts("troubleshoot my game, it keeps crashing"))
        self.assertFalse(guide.starts("walk me through mod bisect"))
        self.assertFalse(guide.starts("explain it step by step"))

    def test_asks_what_is_wrong_first(self):
        s = guide.begin("help me fix Hades", ["Hades"])
        self.assertEqual((s["problem"], s["game"]), ("", "Hades"))
        body, buttons = guide.ask_problem(s)
        self.assertIn("Hades", body)
        picked = buttons[0][1][2:]
        self.assertEqual(guide.begin(picked, ["Hades"])["problem"], "crash_on_start")

    def test_one_step_at_a_time(self):
        s = guide.begin("help me fix Hades, it won't start", ["Hades"])
        body, buttons = guide.step_view(s)
        self.assertTrue(body.startswith("Step 1 of"))
        self.assertIn(("Check it for me", "q:fix Hades"), buttons)
        self.assertIn(("No, next step", "q:no, next step"), buttons)
        s = guide.advance(s, guide.reply(s, "no, still broken"))
        self.assertEqual(s["at"], 1)
        self.assertEqual(len(s["tried"]), 1)
        s = guide.advance(s, guide.reply(s, "skip"))
        self.assertEqual((s["at"], len(s["tried"])), (2, 1))

    def test_answers(self):
        s = guide.begin("help me fix it, it stutters", [])
        self.assertEqual(guide.reply(s, "yes it worked"), "fixed")
        self.assertEqual(guide.reply(s, "stop"), "stop")
        self.assertEqual(guide.reply(s, "what's my GPU?"), "")

    def test_runs_out_of_steps(self):
        s = guide.begin("help me fix it, it stutters", [])
        while guide.step_view(s) is not None:
            s = guide.advance(s, "next")
        body, buttons = guide.done_view(s)
        self.assertIn("Crash Doctor", body)
        self.assertNotIn("safe", body.casefold())


if __name__ == "__main__":
    unittest.main()
