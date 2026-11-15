import unittest
from unittest.mock import patch

from gg_desktop import backend, scan_parts


class ScanParts(unittest.TestCase):
    def test_route_parts(self):
        self.assertEqual(scan_parts.for_route("Games", True), ("games",))
        self.assertIsNone(scan_parts.for_route("Games", False))
        self.assertIsNone(scan_parts.for_route("Overview", True))
        self.assertEqual(scan_parts.describe(("mods", "games")), "games and mods")

    def test_only_named_parts_are_scanned(self):
        base = backend.Inventory(steam=["s"], other=["o"], games=["g"], mods=["m"], files=["f"], recordings=["r"],
                                 screenshots=["p"], saves=["v"], warnings=["Old Files folder unavailable (OSError)."],
                                 scanned_at="2026-11-14 10:00")
        called = []
        with patch.object(backend, "find_games", lambda *a, **k: called.append("games") or ["s2"]), \
                patch.object(backend, "find_launcher_games", lambda *a, **k: []), \
                patch.object(backend, "merge_games", lambda s, o: ["g2"]), \
                patch.object(backend, "find_all_mod_storage", lambda *a, **k: called.append("mods") or ["m2"]), \
                patch.object(backend, "scan_old_files", lambda *a, **k: called.append("files") or []), \
                patch.object(backend, "find_old_recordings", lambda *a, **k: called.append("captures") or []), \
                patch.object(backend, "find_old_screenshots", lambda *a, **k: []), \
                patch.object(backend, "build_graveyard", lambda *a, **k: ["grave"]):
            out = backend.scan_inventory({}, lambda: False, parts=("games",), base=base)
        self.assertEqual(called, ["games"])
        self.assertEqual(out.games, ["g2"])
        self.assertEqual((out.mods, out.files, out.recordings, out.saves), (["m"], ["f"], ["r"], ["v"]))
        self.assertEqual(out.graveyard, ["grave"])
        self.assertIn("Old Files folder unavailable (OSError).", out.warnings)
        self.assertTrue(out.scanned_at)


if __name__ == "__main__":
    unittest.main()
