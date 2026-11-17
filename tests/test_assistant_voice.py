import subprocess
import unittest
from types import SimpleNamespace

from gg_desktop import assistant_voice as voice


class Voice(unittest.TestCase):
    def test_speech_text_skips_paths_and_links(self):
        said = voice.clean_for_speech(r"Open D:\Games\Starfield or https://pcgamingwiki.com/x (Double-check: 3 GB)")
        self.assertNotIn("D:\\", said)
        self.assertNotIn("https", said)
        self.assertNotIn("Double-check", said)

    def test_listen_reads_windows_dictation(self):
        cmd = voice.listen_command(8)
        self.assertEqual(cmd[0], "powershell")
        self.assertIn("System.Speech", cmd[-1])
        self.assertIn("FromSeconds(8)", cmd[-1])
        heard = voice.recognize(run=lambda *a, **k: SimpleNamespace(stdout="why does skyrim crash", stderr=""))
        self.assertEqual(heard, ("why does skyrim crash", ""))

    def test_listen_failures_say_why(self):
        words, why = voice.recognize(run=lambda *a, **k: SimpleNamespace(stdout="", stderr="No recognizer is installed"))
        self.assertEqual(words, "")
        self.assertIn("speech recognizer", why)

        def boom(*a, **k):
            raise subprocess.TimeoutExpired("powershell", 1)
        self.assertEqual(voice.recognize(run=boom)[0], "")


try:
    from PySide6 import QtCore  # noqa: F401
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "needs PySide6")
class Charts(unittest.TestCase):
    def test_rows_come_from_the_facts(self):
        from dataclasses import replace
        from gg_desktop import assistant_visuals as visuals
        from tests.test_local_ai_tools import SPECS
        from tests.test_assistant import facts
        f = replace(facts(), hardware=SPECS)
        title, rows = visuals.chart_rows(f, "games")
        self.assertEqual(rows[0][0], "Starfield")
        title, rows = visuals.chart_rows(f, "drives")
        self.assertEqual(rows[0][0], "Drive C")
        title, rows = visuals.chart_rows(f, "space")
        self.assertIn("reported", title)
        self.assertEqual(rows[0][0], "Games")


if __name__ == "__main__":
    unittest.main()
