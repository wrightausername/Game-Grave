"""Opt-in AI privacy and failure-mode tests. No Ollama installation required."""
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error

from core import default_settings
from local_ai import (
    AssistantUnavailable, DEFAULT_MODEL, ENDPOINT, aggregate_scan_context,
    ask_local_assistant,
)


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def read(self, _limit):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class OptionalAiTests(unittest.TestCase):
    def test_off_by_default(self):
        settings = default_settings()
        self.assertIs(settings["ai_assistant_enabled"], False)
        self.assertEqual(settings["ai_model"], DEFAULT_MODEL)
        with patch("urllib.request.build_opener") as opener:
            with self.assertRaisesRegex(AssistantUnavailable, "Enable"):
                ask_local_assistant("Hello", settings)
            opener.assert_not_called()

    def test_aggregate_context_never_includes_paths(self):
        row = SimpleNamespace(path="C:/Secret/Personal", name="Sensitive Game")
        inventory = SimpleNamespace(
            games=[row], mods=[row, row], graveyard=[row], screenshots=[row])
        counts = aggregate_scan_context(inventory)
        self.assertEqual(counts, {
            "games": 1, "mods": 2, "screenshots": 1, "graveyard": 1})
        self.assertNotIn("Secret", str(counts))
        self.assertEqual(
            aggregate_scan_context({"games": 5, "path": "private", "mods": -4,
                                    "screenshots": True}),
            {"games": 5},
        )

    def test_localhost_only_and_aggregate_only(self):
        settings = {"ai_assistant_enabled": True, "ai_model": DEFAULT_MODEL}
        inventory = SimpleNamespace(
            games=[SimpleNamespace(path="C:/Sensitive/Secret", name="Hidden")]
        )
        class FakeOpener:
            def open(self, request, timeout):
                self_request["url"] = request.full_url
                self_request["body"] = json.loads(request.data.decode("utf-8"))
                self_request["timeout"] = timeout
                return FakeResponse({"message": {"content": "Review first."}})
        self_request = {}
        with patch("urllib.request.build_opener", return_value=FakeOpener()) as builder:
            answer = ask_local_assistant("Why check mods?", settings, inventory)
        self.assertEqual(answer, "Review first.")
        self.assertEqual(self_request["url"], ENDPOINT)
        self.assertEqual(self_request["body"]["model"], DEFAULT_MODEL)
        self.assertEqual(self_request["body"]["messages"][-1]["content"], "Why check mods?")
        self.assertNotIn("Sensitive", json.dumps(self_request["body"]))
        self.assertNotIn("Hidden", json.dumps(self_request["body"]))
        self.assertIn('"games": 1', self_request["body"]["messages"][0]["content"])
        self.assertEqual(self_request["timeout"], 90)
        self.assertEqual(len(builder.call_args.args), 1)
        self.assertIsInstance(builder.call_args.args[0], urllib.request.ProxyHandler)
        self.assertEqual(builder.call_args.args[0].proxies, {})

    def test_reject_invalid_model_and_long_question_before_network(self):
        with patch("urllib.request.build_opener") as opener:
            for name in ("http://evil.example", "../model", " ", ""):
                with self.assertRaises(AssistantUnavailable):
                    ask_local_assistant("Hello", {"ai_assistant_enabled": True, "ai_model": name})
            with self.assertRaisesRegex(AssistantUnavailable, "800"):
                ask_local_assistant("a" * 801,
                    {"ai_assistant_enabled": True, "ai_model": DEFAULT_MODEL})
            opener.assert_not_called()

    def test_model_not_installed_has_helpful_message(self):
        settings = {"ai_assistant_enabled": True, "ai_model": DEFAULT_MODEL}
        class NoModel:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(request.full_url, 404, "Not found", {}, io.BytesIO())
        with patch("urllib.request.build_opener", return_value=NoModel()):
            with self.assertRaisesRegex(AssistantUnavailable, "ollama pull"):
                ask_local_assistant("Hello", settings)

    def test_local_service_down_has_helpful_message(self):
        settings = {"ai_assistant_enabled": True, "ai_model": DEFAULT_MODEL}
        class Down:
            def open(self, request, timeout):
                raise urllib.error.URLError("Connection refused")
        with patch("urllib.request.build_opener", return_value=Down()):
            with self.assertRaisesRegex(AssistantUnavailable, "No cloud"):
                ask_local_assistant("Hello", settings)


if __name__ == "__main__":
    unittest.main()
