import unittest

from gg_desktop import assistant_followup as fu


def chat(*messages):
    return {"messages": list(messages)}


USER = {"role": "user", "text": "clean up my temp files"}


class FollowUp(unittest.TestCase):
    def test_words(self):
        for t in ("proceed", "Proceed.", "yes", "yes please", "ok do it", "go ahead", "run it!", "sure", "let's do it",
                  "turn it on", "sounds good"):
            self.assertTrue(fu.is_go_ahead(t), t)
        for t in ("what can I delete", "clean up my temp files", "yes but why does my game crash so often every night"):
            self.assertFalse(fu.is_go_ahead(t), t)
        self.assertTrue(fu.is_no("no thanks"))
        self.assertTrue(fu.is_no("cancel"))
        self.assertFalse(fu.is_go_ahead("no"))

    def test_offers(self):
        off = chat(USER, {"role": "assistant", "answer": {"intent": "autopilot_off"}, "plan": {"id": "p1", "steps": []}})
        self.assertEqual(fu.last_offer(off).kind, "turn_on")
        self.assertEqual(fu.last_offer(off).request, "clean up my temp files")
        waiting = chat(USER, {"role": "assistant", "answer": {"intent": "autopilot"},
                              "plan": {"id": "p2", "steps": [{"ticked": True, "status": "ready"}]}})
        self.assertEqual((fu.last_offer(waiting).kind, fu.last_offer(waiting).plan_id), ("plan", "p2"))
        done = chat(USER, {"role": "assistant", "answer": {"intent": "autopilot"},
                           "plan": {"id": "p3", "steps": [{"ticked": True, "status": "done"}]}})
        self.assertIsNone(fu.last_offer(done))
        guide = chat(USER, {"role": "assistant", "answer": {"intent": "feature",
                                                             "handoffs": [["Do it for me", "ask:clean temp files"]]}})
        self.assertEqual((fu.last_offer(guide).kind, fu.last_offer(guide).request), ("do", "clean temp files"))
        self.assertIsNone(fu.last_offer(chat(USER, {"role": "assistant", "answer": {"intent": "games"}})))
        self.assertIsNone(fu.last_offer({}))


if __name__ == "__main__":
    unittest.main()
