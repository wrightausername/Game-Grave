"""Regression coverage for the pre-release Game Grave legal notice.

The information-only About notice does NOT substitute for acceptance of a
public EULA, Privacy Notice, or purchase agreement.
"""
import unittest

from gg_desktop.legal_notice import LEGAL_NOTICE, LEGAL_NOTICE_VERSION


class LegalNoticeTests(unittest.TestCase):
    def test_notice_is_substantial_and_covers_actual_risks(self):
        required = (
            "WHAT GAME GRAVE DOES", "NO AUTOMATIC AUTHORITY TO DELETE",
            "RECYCLE BIN", "GAME SAVES", "STORAGE FIGURES",
            "GAMEPLAY PERFORMANCE", "SCREENSHOTS", "OPTIONAL NETWORK",
            "AI OUTPUT", "OWNERSHIP", "PURCHASES", "USER RESPONSIBILITIES",
            "AS IS", "LIMITATION OF LIABILITY", "SECURITY & PRIVACY",
            "CONSUMER RIGHTS", "Privacy Notice", "EULA",
        )
        self.assertGreater(len(LEGAL_NOTICE), 8500)
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.casefold(), LEGAL_NOTICE.casefold())

    def test_no_unqualified_guarantee_or_fake_user_acceptance(self):
        self.assertIn("non-waivable", LEGAL_NOTICE)
        self.assertIn("legal review", LEGAL_NOTICE.lower())
        self.assertIn("does not mean you have agreed", LEGAL_NOTICE)
        self.assertIn("November 2026", LEGAL_NOTICE_VERSION)
        self.assertNotIn("99% protected", LEGAL_NOTICE)
        self.assertNotIn("no liability under any circumstances", LEGAL_NOTICE.lower())

    def test_about_page_wires_read_only_scrollable_notice(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "gg_desktop" / "screens.py").read_text(encoding="utf-8")
        self.assertIn("from gg_desktop.legal_notice import LEGAL_NOTICE", source)
        self.assertIn('legal_text.setObjectName("aboutLegalNotice")', source)
        self.assertIn("legal_text.setReadOnly(True)", source)
        self.assertIn("legal_text.setPlainText(LEGAL_NOTICE)", source)
        self.assertIn("settings_pages.addWidget(about)", source)


if __name__ == "__main__":
    unittest.main()
