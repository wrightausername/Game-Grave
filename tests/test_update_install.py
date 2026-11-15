import unittest

from gg_desktop import update_install_core as core


class UpdateInstall(unittest.TestCase):
    def test_script_records_only_on_success_and_quotes(self):
        s = core.install_script(r"C:\Users\o'neil\AppData\GG\Setup.exe", "preview-run-42", r"C:\state.json", r"C:\GG.exe")
        self.assertIn("'C:\\Users\\o''neil\\AppData\\GG\\Setup.exe'", s)
        self.assertIn("if ($p.ExitCode -eq 0)", s)
        self.assertIn("'/SILENT','/NORESTART','/CLOSEAPPLICATIONS'", s)
        self.assertIn("WriteAllText", s)          # no BOM, so update_check can read the state back
        self.assertLess(s.index("ExitCode -eq 0"), s.index("installed_tag"))

    def test_bad_tag_refused(self):
        with self.assertRaises(core.UpdateInstallError):
            core.install_script("a", "x'; Remove-Item C:\\", "b", "c")

    def test_questions(self):
        self.assertIn("SHA-256", core.download_question("preview-run-1", 120.4))
        self.assertIn("120 MB", core.download_question("preview-run-1", 120.4))
        q = core.install_question("preview-run-1")
        self.assertIn("Game Grave closes", q)
        self.assertIn("not touched", q)
        self.assertEqual(core.progress_text(1048576 * 5, 1048576 * 10), "Downloading the update: 5 of 10 MB")


if __name__ == "__main__":
    unittest.main()
