"""Windows Recycle Bin identity safety: exact names, never Explorer display names."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import recovery


class RecoveryFilenameTests(unittest.TestCase):
    def test_shell_lookup_uses_full_filename_not_display_name(self):
        script = recovery._bin_script(r"C:\Users\Player\Downloads\foo.txt")
        self.assertIn("System.Recycle.DeletedFrom", script)
        self.assertIn("System.FileName", script)
        self.assertIn("[System.IO.Path]::Combine($from, $fileName)", script)
        self.assertNotIn("[System.IO.Path]::Combine($from, $item.Name)", script)
        self.assertNotIn("GetDetailsOf($item, 1)", script)

    def test_shell_refuses_missing_exact_name_property_instead_of_guessing(self):
        script = recovery._bin_script(r"C:\Users\Player\Downloads\archive.zip")
        self.assertIn("if (-not $from -or -not $fileName) { continue }", script)
        self.assertIn("OrdinalIgnoreCase", script)
        self.assertIn("if ($matches.Count -eq 1)", script)

    def test_restore_rechecks_original_path_before_invoking_windows_shell(self):
        script = recovery._bin_script(r"C:\A\file.txt", restore=True)
        self.assertIn("'ORIGINAL_EXISTS'", script)
        self.assertLess(script.find("if (Test-Path -LiteralPath $original)"),
                        script.find("$matches[0].InvokeVerb('undelete')"))

    def test_full_path_with_apostrophes_is_escaped_as_powershell_literal(self):
        script = recovery._bin_script(r"C:\Player's Downloads\archive.zip")
        self.assertIn("C:\\Player''s Downloads\\archive.zip", script)
        self.assertNotIn("C:\\Player's Downloads\\archive.zip", script)

    def test_unverified_shell_result_never_becomes_restored(self):
        with tempfile.TemporaryDirectory() as td:
            absent = Path(td) / "long-gone.zip"
            row = {"id": "qa-1", "path": str(absent), "state": "Not checked"}
            writes = []
            with patch.object(recovery, "get_records", return_value=[row]), \
                    patch.object(recovery, "_run_ps", return_value="NOT_FOUND"), \
                    patch.object(recovery, "_write", side_effect=lambda rows: writes.append(rows)):
                status = recovery.restore("qa-1")
            self.assertEqual(status, "NOT_FOUND")
            self.assertEqual(row["state"], "Not found")
            self.assertNotEqual(row["state"], "Restored")
            self.assertEqual(len(writes), 1)


if __name__ == "__main__":
    unittest.main()
