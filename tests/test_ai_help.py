"""Offline product-help lookup tests. Never needs installed AI."""
import unittest
from ai_help import help_context


class InAppHelpTests(unittest.TestCase):
    def test_core_help_topics(self):
        topics = {
            "why won't Graveyard delete my protected folder": ("Graveyard", "Never Touch"),
            "where do I recover a lost save with a resurrection kit": ("Resurrection Kit", "Undo Center"),
            "how do I find missing Epic games": ("Epic", "Steam"),
            "is Pro a subscription or a lifetime license": ("lifetime", "subscription"),
            "what's Mod Radar and how do I manage Vortex": ("Mod Radar", "Vortex"),
            "how do I remove old screenshots": ("screenshots", "preview"),
        }
        for question, keywords in topics.items():
            with self.subTest(question=question):
                answer = help_context(question)
                for word in keywords:
                    self.assertIn(word.lower(), answer.lower())

    def test_unknown_question_returns_general_help_without_fabrication(self):
        text = help_context("what should I cook tomorrow")
        self.assertIn("Getting started", text)
        self.assertIn("Never fabricate", text)

    def test_help_context_never_uses_private_content(self):
        text = help_context("why is C:/Secret/Personal/saves protected")
        self.assertNotIn("Secret", text)
        self.assertNotIn("Personal", text)
        self.assertIn("OFFICIAL GAME GRAVE", text)

    def test_bounded_official_context(self):
        text = help_context("scan mods Graveyard undo screenshots license app settings", max_topics=3)
        self.assertLess(len(text), 2200)
        self.assertEqual(text.count("\n- "), 3)


if __name__ == "__main__":
    unittest.main()
