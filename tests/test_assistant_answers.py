"""Everyday questions get a real answer, not a deflection, and the honesty rules still hold."""
import unittest
from dataclasses import replace

from gg_desktop import assistant_engine as engine
from gg_desktop import hardware_core as hw
from tests.test_assistant import facts, game, inventory

GB = 1024 ** 3
SPECS = hw.Specs(cpu=hw.Cpu("AMD Ryzen 7 7800X3D", 8, 16, 4.2, "AM5"), gpus=(hw.Gpu("NVIDIA GeForce RTX 4070", "32.0"),),
                 memory=hw.Memory(32, 2, 4, "DDR5", 6000, 6000), os_name="Windows 11 Pro", os_version="24H2",
                 drives=(hw.Drive("C", "", 1000 * GB, 180 * GB, "Samsung 990 Pro", "NVMe"),
                         hw.Drive("D", "", 2000 * GB, 90 * GB, "WD Blue", "hard drive")))

QUESTIONS = """how much space do my games take|which game should i uninstall|what can i delete to free up space
how many games do i have|how many mods do i have|do i have any mod conflicts|when did i last play hades
what games haven't i played in a year|how do i back up my saves|where are my saves for cyberpunk
how much space are my screenshots using|is my pc good enough for starfield|how do i update my drivers
how do i stop apps starting with windows|what does the resurrection kit do|how do i share my mod list with a friend
my game keeps crashing what do i do|which mod is crashing my game|how much free space do i have
what's my graphics card|what drive is starfield on|how do i move a game to another drive|what did game grave delete
hi|thanks|what is shader cache|are there any updates for my games|my c drive is almost full
which games take the most room|do i have enough space for a 100gb game|my pc is slow what can i do
how do i make a backup of a game|can game grave install mods|is game grave safe|what's my windows version
list my games|how do i check if my game files are corrupted|why is my game stuttering|cyberpunk size
what launchers do i use|should i get rid of cyberpunk""".replace("\n", "|").split("|")


class EverydayQuestions(unittest.TestCase):
    def setUp(self):
        self.facts = replace(facts(), hardware=SPECS)

    def test_none_is_deflected(self):
        for q in QUESTIONS:
            a = engine.answer(q, self.facts)
            self.assertNotIn(a.intent, ("unknown", "help", "hardware_unread"), q)

    def test_nothing_is_called_safe_or_freed(self):
        for q in QUESTIONS:
            a = engine.answer(q, self.facts)
            text = " ".join([a.text, a.note] + [r.label + " " + r.value + " " + r.detail for r in a.rows]).casefold()
            text = text.replace(engine.SAFETY_TEXT.casefold(), "")
            for word in ("safe to remove", "safe to delete", "freed", "reclaimed"):
                self.assertNotIn(word, text, q)

    def test_direct_answers(self):
        self.assertIn("You have 4 games", engine.answer("how many games do i have", self.facts).text)
        self.assertIn("RTX 4070", engine.answer("what's my graphics card", self.facts).text)
        self.assertIn("270.0 GB free", engine.answer("how much free space do i have", self.facts).text)
        self.assertIn("32 GB DDR5", engine.answer("how much ram do i have", self.facts).text)
        self.assertIn("drive D:", engine.answer("what drive is starfield on", self.facts).text)
        self.assertIn("120.0 GB", engine.answer("how big is starfield", self.facts).text)
        self.assertIn("400 days ago", engine.answer("when did i last play cyberpunk", self.facts).text)
        self.assertIn("no last-played date", engine.answer("when did i last play hades", self.facts).text)
        self.assertTrue(engine.answer("do i have enough space for a 100gb game", self.facts).text.startswith("Yes: C:"))
        self.assertTrue(engine.answer("do i have enough space for a 500gb game", self.facts).text.startswith("No drive"))

    def test_short_names_find_the_game(self):
        a = engine.answer("cyberpunk size", self.facts)
        self.assertEqual(a.intent, "profile")
        self.assertIn("Cyberpunk 2077", a.text)

    def test_ambiguous_short_name_is_not_guessed(self):
        f = facts(inventory(games=[game("Dark Souls Remastered"), game("Dark Souls III")]))
        self.assertIsNone(engine.find_entity(f, "souls size"))

    def test_uninstall_candidates_are_big_and_idle_and_never_a_verdict(self):
        a = engine.answer("which game should i uninstall", self.facts)
        self.assertEqual(a.intent, "candidates")
        self.assertIn("Cyberpunk 2077", a.rows[0].label)
        self.assertNotIn("Starfield (not played", " ".join(r.label for r in a.rows))  # played 3 days ago
        self.assertIn("doesn't mean you're done", a.note)

    def test_hardware_unread_asks_windows(self):
        a = engine.answer("what's my graphics card", facts())
        self.assertEqual(a.intent, "hardware_unread")

    def test_can_run_is_honest(self):
        a = engine.answer("is my pc good enough for starfield", self.facts)
        self.assertIn("can't tell you whether this PC runs Starfield", a.text)

    def test_history_empty_does_not_say_scan(self):
        a = engine.answer("what did game grave delete", self.facts)
        self.assertNotIn("Scan PC", a.text)

    def test_small_talk_is_short(self):
        self.assertEqual(engine.classify("ok thanks man", self.facts)[0], "thanks")
        self.assertEqual(engine.classify("hello there", self.facts)[0], "greet")
        self.assertNotEqual(engine.classify("hello how many games do i have", self.facts)[0], "greet")


if __name__ == "__main__":
    unittest.main()
