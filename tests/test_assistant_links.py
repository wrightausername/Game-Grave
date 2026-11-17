import tempfile
import unittest
from pathlib import Path

from gg_desktop import assistant_links as links


class Linkify(unittest.TestCase):
    def test_games_tabs_and_paths_become_links(self):
        html = links.linkify("Starfield is in D:\\Games\\Starfield. Open Toolbox.", ["Starfield"])
        self.assertIn('href="game:Starfield"', html)
        self.assertIn('href="path:D:\\Games\\Starfield"', html)   # the full stop after the path is not part of it
        self.assertIn('href="tab:More Tools"', html)                 # Toolbox opens the More Tools route
        self.assertIn(">Toolbox<", html)

    def test_text_is_escaped(self):
        html = links.linkify("<b>1 < 2</b> & more", [])
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;b&gt;", html)

    def test_part_of_a_word_is_not_a_game(self):
        self.assertNotIn("game:", links.linkify("Hadesville is not a game here", ["Hades"]))

    def test_newlines_kept(self):
        self.assertIn("<br>", links.linkify("one\ntwo", []))


class NextQuestions(unittest.TestCase):
    def test_game_follow_ups(self):
        picks = links.next_questions("profile", "when did I last play Hades", "", "Hades")
        self.assertEqual(picks[0], ("Is Hades modded?", "is Hades modded"))
        self.assertLessEqual(len(picks), 3)

    def test_never_repeats_the_question(self):
        picks = links.next_questions("hardware", "check my drivers")
        self.assertNotIn("check my drivers", [ask for _l, ask in picks])

    def test_problem_from_local_ai(self):
        picks = links.next_questions("local_ai", "my game keeps crashing")
        self.assertEqual(picks[0][1], "help me fix my game")


class SearchAndPins(unittest.TestCase):
    def test_search_reads_titles_and_answers(self):
        chats = [{"id": "a", "title": "Space", "messages": [{"role": "assistant", "answer": {"text": "Starfield is big"}}]},
                 {"id": "b", "title": "Mods", "messages": [{"role": "user", "text": "turn off skyui"}]}]
        self.assertEqual(links.search_chats(chats, "starfield"), ["a"])
        self.assertEqual(links.search_chats(chats, "SKYUI off"), ["b"])
        self.assertEqual(links.search_chats(chats, ""), ["a", "b"])

    def test_pins_dedupe_cap_and_remove(self):
        pins = []
        for i in range(links.MAX_PINS + 5):
            pins = links.add_pin(pins, f"q{i}", "a", "now")
        self.assertEqual(len(pins), links.MAX_PINS)
        pins = links.add_pin(pins, f"q{links.MAX_PINS + 4}", "a", "later")
        self.assertEqual(len(pins), links.MAX_PINS)
        self.assertEqual(pins[-1]["when"], "later")
        self.assertEqual(len(links.remove_pin(pins, 0)), links.MAX_PINS - 1)


class Logs(unittest.TestCase):
    def test_key_lines_find_errors_with_context(self):
        text = "boot\nloading SkyUI\nERROR: missing master Foo.esm\nfine\nfine\nException 0xc0000005 in d3d11.dll\n"
        lines = links.key_lines(text)
        self.assertIn("ERROR: missing master Foo.esm", lines)
        self.assertIn("loading SkyUI", lines)
        self.assertIn("Exception 0xc0000005 in d3d11.dll", lines)
        self.assertNotIn("boot", lines)

    def test_repeats_dropped_and_fallback(self):
        self.assertEqual(len(links.key_lines("ERROR 1 failed\nERROR 2 failed\n")), 1)
        self.assertEqual(links.key_lines("a\nb\nc"), ["a", "b", "c"])

    def test_read_log_types_and_utf16(self):
        with tempfile.TemporaryDirectory() as d:
            good = Path(d, "crash.log")
            good.write_text("ERROR here", encoding="utf-16")
            name, text, why = links.read_log(good)
            self.assertEqual((name, why), ("crash.log", ""))
            self.assertIn("ERROR here", text)
            bad = Path(d, "game.exe")
            bad.write_bytes(b"MZ")
            self.assertIsNone(links.read_log(bad)[1])

    def test_error_question(self):
        q = links.error_question("Scan failed", "Access is denied.")
        self.assertIn('"Scan failed"', q)
        self.assertIn("what should I do", q)


if __name__ == "__main__":
    unittest.main()
