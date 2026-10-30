"""Non-destructive M3 visual guide semantics and responsive layout checks."""
import unittest

from resurrection_visuals import resurrection_steps, render_resurrection_flow


COLORS = {
    "panel": "#172133", "raised": "#1D2A3C", "text": "#ECF2FC",
    "muted": "#9DAEC5", "line": "#303C50",
    "accent": "#50DCC5", "blue": "#6B9EFF", "warn": "#FFCD7E",
}


class FakeCanvas:
    def __init__(self):
        self.commands = []
        self.settings = {}
    def delete(self, name):
        self.commands.clear()
    def create_rectangle(self, *args, **kwargs):
        self.commands.append(("rectangle", args, kwargs))
    def create_text(self, *args, **kwargs):
        self.commands.append(("text", args, kwargs))
    def create_line(self, *args, **kwargs):
        self.commands.append(("line", args, kwargs))
    def configure(self, **kwargs):
        self.settings.update(kwargs)


class ResurrectionVisualTests(unittest.TestCase):
    def test_steps_match_safe_user_approved_workflow(self):
        stages = resurrection_steps()
        self.assertEqual([s[0] for s in stages],
                         ["PICK", "SEAL", "REHEARSE", "STAGE"])
        self.assertIn("SHA-256", str(stages))
        self.assertIn("untouched", str(stages))
        self.assertNotIn("guaranteed compatible", str(stages))

    def test_graphic_is_responsive_and_not_an_action_control(self):
        canvas = FakeCanvas()
        narrow = render_resurrection_flow(canvas, 420, COLORS)
        self.assertEqual(narrow, 204)
        self.assertEqual(len([row for row in canvas.commands
                              if row[0] == "rectangle" and row[2].get("width")]), 4)
        wide = render_resurrection_flow(canvas, 980, COLORS)
        self.assertEqual(wide, 112)
        self.assertEqual(len([row for row in canvas.commands
                              if row[0] == "line"]), 3)
        self.assertIn("height", canvas.settings)
        self.assertGreaterEqual(len([row for row in canvas.commands if row[0] == "text"]), 12)


if __name__ == "__main__":
    unittest.main()
