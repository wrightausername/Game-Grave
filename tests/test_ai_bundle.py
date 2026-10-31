"""Automated safety tests for the optional built-in AI installer.

Do not download or execute model files in CI.
"""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import ai_bundle
from ai_bundle import AiSetupError, _download_pinned, _extract_runtime, _hash_file


class Response:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, n):
        result, self._payload = self._payload[:n], self._payload[n:]
        return result


class LocalAiSetupSafetyTests(unittest.TestCase):
    def test_no_install_when_disabled_is_the_default(self):
        from core import default_settings
        self.assertIs(default_settings()["ai_assistant_enabled"], False)

    def test_requires_windows(self):
        with patch.object(ai_bundle.sys, "platform", "linux"):
            with patch.object(ai_bundle, "_download_pinned") as download:
                with self.assertRaisesRegex(AiSetupError, "Windows"):
                    ai_bundle.install_ai()
                download.assert_not_called()

    def test_integrity_verified_before_publishing(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "asset.gguf"
            expected = "a" * 64
            with patch("urllib.request.urlopen", return_value=Response(b"wrong")):
                with self.assertRaisesRegex(AiSetupError, "verification"):
                    _download_pinned("https://example.test/asset", target, expected, 100)
            self.assertFalse(target.exists())
            self.assertFalse(list(Path(root).glob("*.part")))

    def test_verified_bytes_reused_without_network(self):
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "asset.gguf"
            target.write_bytes(b"known good")
            digest = hashlib.sha256(b"known good").hexdigest()
            with patch("urllib.request.urlopen") as network:
                _download_pinned("https://example.test/asset", target, digest, 100)
                network.assert_not_called()

    def test_refuse_insecure_download(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(AiSetupError, "HTTPS"):
                _download_pinned("http://example.test/file",
                                 Path(root) / "file", "a" * 64, 100)

    def test_archive_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            archive = base / "bad.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../outside.txt", "bad")
            with self.assertRaisesRegex(AiSetupError, "Unexpected file"):
                _extract_runtime(archive, base / "stage")
            self.assertFalse((base / "outside.txt").exists())

    def test_extraction_requires_one_server(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            archive = base / "fake.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("README", "No server here")
            with self.assertRaisesRegex(AiSetupError, "expected server"):
                _extract_runtime(archive, base / "stage")

    def test_server_not_started_without_explicit_installed_assets(self):
        with patch.object(ai_bundle.sys, "platform", "win32"):
            with patch.object(ai_bundle, "is_ai_installed", return_value=False):
                with patch.object(ai_bundle.subprocess, "Popen") as popen:
                    with self.assertRaisesRegex(AiSetupError, "Enable AI"):
                        ai_bundle.local_server()
                    popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
