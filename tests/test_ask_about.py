import unittest
from types import SimpleNamespace

from gg_desktop import ask_about_core as core


class AskAbout(unittest.TestCase):
    def test_storage_row(self):
        row = SimpleNamespace(name="Battle.net Cache", path=r"C:\ProgramData\Battle.net\Cache", size=2048, newest=1.7e9,
                              related="Battle.net", category="Launcher cache", summary="Launcher cache folder")
        info = core.info_of("storage", row)
        self.assertEqual(info["name"], "Battle.net Cache")
        self.assertIn("storage item", core.question(info))
        a = core.answer(info)
        self.assertIn("Other Storage", a.text)
        self.assertIn("Recycle Bin", a.text)
        self.assertIn("cannot tell whether you still need it", a.text)
        self.assertEqual(a.handoffs, (("Open Other Storage", "Other Storage"),))
        self.assertNotIn("safe to", a.text.lower())

    def test_old_file_without_name_uses_file_name(self):
        info = core.info_of("old_file", SimpleNamespace(path=r"D:\Downloads\setup.exe", size=10, modified=1.6e9))
        self.assertEqual(info["name"], "setup.exe")
        self.assertIn("last changed", core.answer(info).text)

    def test_protected_and_game(self):
        info = core.info_of("grave", SimpleNamespace(name="Skyrim", path=r"C:\x", size=1))
        self.assertIn("Never Touch", core.answer(info, protected=True).text)
        self.assertEqual(core.question(core.info_of("game", SimpleNamespace(name="Elden Ring"))), "Tell me about Elden Ring")
        mod = core.answer(core.info_of("mod", SimpleNamespace(name="SkyUI", path="")))
        self.assertIn("does not delete", mod.text)


if __name__ == "__main__":
    unittest.main()
