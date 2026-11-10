"""Prompts (message boxes, dialogs, input boxes) must be dark with light text, so they stay readable."""
import unittest

from gg_desktop import theme


class PromptTheme(unittest.TestCase):
    def test_dialogs_are_dark_with_light_text(self):
        css = theme.STYLE
        for selector in ("QDialog", "QMessageBox", "QInputDialog", "QFileDialog"):
            self.assertIn(selector, css)
        rule = next(line for line in css.splitlines() if line.startswith("QDialog, QMessageBox"))
        self.assertIn("background:#0B121A", rule)
        self.assertIn("color:#F4F7FC", rule)

    def test_message_box_labels_and_buttons_are_styled(self):
        self.assertIn("QMessageBox QLabel", theme.STYLE)
        self.assertIn("QMessageBox QPushButton", theme.STYLE)


if __name__ == "__main__":
    unittest.main()
