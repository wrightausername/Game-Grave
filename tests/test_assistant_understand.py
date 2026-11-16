"""The built-in assistant understands loose questions: slang, typos, follow-ups, two questions, and never a dead end."""
import unittest
from dataclasses import replace

from gg_desktop import assistant_understand as u
from tests.test_assistant import facts
from tests.test_assistant_answers import SPECS


class LooseQuestions(unittest.TestCase):
    def setUp(self):
        self.facts = replace(facts(), hardware=SPECS)

    def ask(self, q, *context):
        return u.answer(q, self.facts, *context)

    def test_slang_and_typos_land_on_the_right_answer(self):
        cases = {"whats hogging my c drive": "summary", "biggets games": "games", "how much do my pics take up": "captures",
                 "cyber punk size": "profile", "stafield lagging like crazy": "performance", "wat can i delte": "candidates",
                 "tell me about starfeld": "profile", "where r my saves": "saves", "is my rig good enough": "hardware",
                 "storge": "summary", "what about the vids": "captures"}
        for q, intent in cases.items():
            self.assertEqual(self.ask(q).intent, intent, q)

    def test_loose_game_names_are_put_back_exactly(self):
        self.assertIn("starfield", u.normalize("how big is stafield", self.facts))
        self.assertIn("cyberpunk 2077", u.normalize("cyber punk size", self.facts))
        self.assertIsNone(u.fuzzy_game(self.facts, "zelda")[0], "a name it doesn't have is never guessed")

    def test_follow_ups_use_the_last_answer(self):
        prev_q = "how big is starfield"
        prev = self.ask(prev_q).to_dict()
        self.assertIn("Cyberpunk 2077 reports 70.0 GB", self.ask("what about cyberpunk", prev_q, prev).text)
        self.assertIn("Hades reports", self.ask("and hades?", prev_q, prev).text)
        self.assertIn("Cyberpunk 2077 reports", self.ask("cyberpunk", prev_q, prev).text)
        self.assertEqual(self.ask("why?", prev_q, prev).intent, "why")
        listed = self.ask("largest games").to_dict()
        self.assertIn("Cyberpunk 2077", self.ask("the second one", "largest games", listed).text)

    def test_two_questions_get_two_answers(self):
        text = self.ask("how big is starfield and when did i last play cyberpunk").text
        self.assertIn("Starfield reports 120.0 GB", text)
        self.assertIn("You last played Cyberpunk 2077 400 days ago", text)

    def test_a_miss_offers_best_guesses_not_a_dead_end(self):
        a = self.ask("asdkjh qwe")
        self.assertEqual(a.intent, "suggest")
        self.assertNotIn("don't have an answer", a.text)
        self.assertTrue(a.handoffs and all(t.startswith("q:") for _, t in a.handoffs))
        guesses = [label for label, _ in u.suggestions("my screenshots and videos", self.facts)]
        self.assertEqual(guesses[0], "Screenshots and clips")

    def test_never_safe_or_freed(self):
        for q in ("wat can i delte", "whats hogging my c drive", "can i nuke my old files", "asdkjh"):
            a = self.ask(q)
            text = (a.text + " " + a.note).casefold().replace("i can't tell you that something is safe to remove", "")
            for word in ("safe to remove", "safe to delete", "freed"):
                self.assertNotIn(word, text, q)


if __name__ == "__main__":
    unittest.main()
