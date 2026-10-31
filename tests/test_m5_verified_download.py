"""M5 verified offline-integrity downloader: no actual network or installer execution."""
from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_download import download_verified_installer
from updates import VerifiedRelease, UpdateError


class Remote(io.BytesIO):
    def __init__(self, data: bytes, url: str | None = None):
        super().__init__(data)
        self.url = url
    def geturl(self):
        return self.url


class VerifiedDownloadTests(unittest.TestCase):
    URL = "https://updates.example.com/stable/GameGrave_Setup_v1.0.1.exe"
    HOST = "updates.example.com"

    def setUp(self):
        f = tempfile.TemporaryDirectory()
        self.addCleanup(f.cleanup)
        self.root = Path(f.name) / "UserSelectedInstallerFolder"
        self.root.mkdir()
        self.destination = self.root / "GameGrave_Setup_v1.0.1.exe"
        self.body = b"tiny disposable fake exe bytes, not executable"
        self.release = VerifiedRelease(
            "1.0.1", self.URL, hashlib.sha256(self.body).hexdigest(),
            len(self.body), "stable")

    def fetch(self, payload=None, url=None, **kwargs):
        blob = self.body if payload is None else payload
        source = lambda request, timeout: Remote(blob, url or self.URL)
        return download_verified_installer(
            self.release, self.destination, download_host=self.HOST,
            approved=True, opener=source, **kwargs)

    def test_bounded_signed_hash_and_new_file_published_without_execution(self):
        progress = []
        outcome = self.fetch(progress=lambda a, b: progress.append((a, b)))
        self.assertEqual(self.destination.read_bytes(), self.body)
        self.assertEqual(outcome["sha256"], hashlib.sha256(self.body).hexdigest())
        self.assertFalse(outcome["installer_executed"])
        self.assertFalse(outcome["windows_authenticode_verified"])
        self.assertEqual(progress, [(len(self.body), len(self.body))])
        self.assertFalse(list(self.root.glob("*.partial")))

    def test_no_approval_does_not_make_request_or_file(self):
        with self.assertRaises(PermissionError):
            download_verified_installer(
                self.release, self.destination, download_host=self.HOST,
                approved=False, opener=lambda *_a, **_k: self.fail("network"))
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_wrong_hash_and_incorrect_length_leave_no_exe_or_partial(self):
        for body in (b"same length but different bytes xyz", b"too short", self.body + b"X"):
            with self.subTest(body=body):
                with self.assertRaises(UpdateError):
                    self.fetch(payload=body)
                self.assertFalse(self.destination.exists())
                self.assertFalse(list(self.root.glob(".gg-update-*.partial")))

    def test_redirect_to_other_origin_refused_before_writing_data(self):
        with self.assertRaisesRegex(UpdateError, "redirected"):
            self.fetch(url="https://unsafe.example.com/evil.exe")
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".gg-update-*.partial")))

    def test_existing_user_file_is_never_overwritten(self):
        self.destination.write_bytes(b"pre-existing unrelated bytes")
        with self.assertRaises(FileExistsError):
            self.fetch()
        self.assertEqual(self.destination.read_bytes(), b"pre-existing unrelated bytes")

    def test_stop_download_does_not_leave_partial_executable(self):
        with self.assertRaises(InterruptedError):
            self.fetch(canceled=lambda: True)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_pinned_host_and_https_must_match(self):
        with self.assertRaises(UpdateError):
            download_verified_installer(
                self.release, self.destination, download_host="other.example.com",
                approved=True, opener=lambda *_a, **_k: self.fail("network"))
        self.assertFalse(self.destination.exists())

    def test_no_publish_fallback_on_unsupported_filesystem(self):
        with patch("update_download.os.link", side_effect=OSError("no hardlinks")):
            with self.assertRaises(OSError):
                self.fetch()
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".gg-update-*.partial")))


if __name__ == "__main__":
    unittest.main()
