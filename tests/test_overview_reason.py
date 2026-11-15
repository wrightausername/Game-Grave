import unittest


class UnknownReason(unittest.TestCase):
    def test_reasons(self):
        try:
            from gg_desktop.overview_storage_ui import unknown_reason
        except ImportError:
            self.skipTest("needs Qt")
        self.assertEqual(unknown_reason("Old Files", ["Old Files folder unavailable (FileNotFoundError)."])[0], "folder not found")
        self.assertIn("Scan Now", unknown_reason("Old Files", [])[1])
        self.assertEqual(unknown_reason("Captures", ["Recordings partially unavailable (OSError)."])[0], "folders not readable")
        self.assertNotIn("safe", " ".join(unknown_reason("Other Storage", [])).lower())


if __name__ == "__main__":
    unittest.main()
