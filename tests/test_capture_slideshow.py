"""Regression tests for the real screenshot gallery autoplay and safety."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication, QWidget
    from gg_desktop.capture_slideshow import CaptureSlideshow, SLIDE_INTERVAL_MS
    QT_OK = True
except ImportError:
    QT_OK = False


@unittest.skipUnless(QT_OK, "PySide6 preview dependencies not installed")
class CaptureSlideshowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def make_gallery(self, count):
        class Host(QWidget):
            def isActiveWindow(self):
                return True

        host = Host()
        records = [
            SimpleNamespace(path=f"C:/Games/Captures/real-{i:04d}.png",
                            modified=1700000000 + i * 2, size=12)
            for i in range(count)
        ]
        host.inventory = SimpleNamespace(screenshots=records)
        slides = CaptureSlideshow(host, records, parent=host)
        host.show()
        slides.show()
        self.qt.processEvents()
        self.addCleanup(host.close)
        return slides

    def test_every_detected_photo_included_even_past_old_table_limit(self):
        with patch("gg_desktop.capture_slideshow.request_screenshot"):
            gallery = self.make_gallery(810)
            self.assertEqual(len(gallery.records), 810)
            self.assertEqual(gallery.timer.interval(), 5000)
            self.assertEqual(SLIDE_INTERVAL_MS, 5000)
            self.assertEqual(gallery.position.text(), "1 / 810")
            gallery.previous()
            self.assertEqual(gallery.index, 809)
            gallery.next()
            self.assertEqual(gallery.index, 0)

    def test_autoplay_advance_pause_resume_and_hide(self):
        with patch("gg_desktop.capture_slideshow.request_screenshot"):
            gallery = self.make_gallery(3)
            gallery._advance()
            self.assertEqual(gallery.index, 1)
            gallery.toggle_play()
            self.assertFalse(gallery.playing)
            self.assertFalse(gallery.timer.isActive())
            gallery._advance()
            self.assertEqual(gallery.index, 1)
            gallery.toggle_play()
            self.assertTrue(gallery.playing)
            gallery.hide()
            self.assertFalse(gallery.timer.isActive())

    def test_after_manual_deletion_no_unlisted_photo_remains(self):
        with patch("gg_desktop.capture_slideshow.request_screenshot"):
            gallery = self.make_gallery(3)
            gallery.jump_to(2)
            kept = gallery.records[:2]
            gallery.set_records(kept)
            self.assertEqual(len(gallery.records), 2)
            self.assertEqual(gallery.index, 0)
            gallery.set_records([])
            self.assertFalse(gallery.playing)
            self.assertFalse(gallery.play_button.isEnabled())
            self.assertEqual(gallery.position.text(), "0 / 0")


if __name__ == "__main__":
    unittest.main()
