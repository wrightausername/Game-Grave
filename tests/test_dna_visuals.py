"""Pure logic and optional real-Tk smoke checks for native Game Grave visuals."""
import tempfile
import unittest
from types import SimpleNamespace

from dna_visuals import dna_counts, flow_steps, _dna_draw, _steps_draw
from game_intelligence import build_game_dna

PALETTE = {
    "panel": "#172133", "raised": "#1D2A3C", "text": "#ECF2FC",
    "muted": "#9DAEC5", "line": "#303C50", "accent": "#50DCC5",
    "warn": "#FFCD7E", "blue": "#6B9EFF",
}


class VisualLearningLogicTests(unittest.TestCase):
    def test_empty_scan_does_not_invent_relationships_or_cleanup_authority(self):
        counts = dna_counts({"games": [], "unresolved": []})
        self.assertEqual(counts, {"games": 0, "associated": 0, "review": 0,
                                  "ambiguous": 0, "authorized_removal": 0})

    def test_real_dna_counts_linked_and_ambiguous_evidence_without_deletion(self):
        dna = {"games": [{"assets": [{"protected": True}, {"protected": True}]},
                         {"assets": []}],
               "unresolved": [{"kind": "Mod", "ambiguous": True}, {"kind": "Save"}]}
        counts = dna_counts(dna)
        self.assertEqual(counts["games"], 2)
        self.assertEqual(counts["associated"], 2)
        self.assertEqual(counts["review"], 2)
        self.assertEqual(counts["ambiguous"], 1)
        self.assertEqual(counts["authorized_removal"], 0)

    def test_flow_never_claims_safe_removal_or_launch_verified(self):
        steps = flow_steps()
        self.assertEqual([row[0] for row in steps], ["FIND", "MATCH", "PROTECT"])
        joined = " ".join(str(s) for s in steps).lower()
        self.assertNotIn("safe to delete", joined)
        self.assertNotIn("ready for removal", joined)

    def test_tk_can_render_wide_and_narrow_diagrams_when_display_available(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("No Tk display available on this CI host")
        self.addCleanup(root.destroy)
        root.withdraw()
        canvas = tk.Canvas(root)
        counts = dna_counts({"games": [{"assets": [{"protected": True}]}],
                             "unresolved": [{"ambiguous": True}]})
        for width in (320, 520, 675, 790):
            _dna_draw(canvas, width, counts, PALETTE)
            self.assertGreater(len(canvas.find_all()), 8)
            self.assertGreater(int(canvas.cget("height")), 0)
            _steps_draw(canvas, width, PALETTE)
            self.assertGreater(len(canvas.find_all()), 5)


if __name__ == "__main__":
    unittest.main()
