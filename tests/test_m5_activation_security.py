"""M5 paid-key and local receipt hardening with synthetic signed credentials."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from licensing import LicenseError, activation_ready, activate_key, read_edition


class RedirectingServer(io.BytesIO):
    def geturl(self):
        return "https://attacker.example/steal-key"


class ActivationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode()
        self.endpoint = "https://license.example.test/api/activate"
        self.payload = {
            "app": "gamegrave", "edition": "pro", "type": "lifetime",
            "schema": 1, "license_id": "fake-opaque-paid-entitlement"
        }

    def signed(self):
        contents = json.dumps(self.payload, sort_keys=True, ensure_ascii=True,
                              separators=(",", ":")).encode("utf-8")
        signature = base64.b64encode(self.private.sign(contents)).decode()
        return json.dumps({"payload": self.payload,
                           "signature": signature}).encode("utf-8")

    def activate(self, path, server=None):
        return activate_key(
            "GG-AAAA-BBBB-CCCC", url=self.endpoint, public_key=self.public,
            opener=server or (lambda req, timeout=10: io.BytesIO(self.signed())),
            destination=path)

    def test_receipt_write_never_overwrites_unrelated_shared_tmp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pro_license.json"
            old_temp = path.with_suffix(".tmp")
            old_temp.write_bytes(b"IMPORTANT DATA NOT RELATED TO GAME GRAVE")
            edition = self.activate(path)
            self.assertTrue(edition.is_pro)
            self.assertTrue(read_edition(path, self.public).is_pro)
            self.assertEqual(old_temp.read_bytes(),
                             b"IMPORTANT DATA NOT RELATED TO GAME GRAVE")
            self.assertEqual(list(Path(directory).glob(".pro_license.json.*.tmp")), [])
            self.assertNotIn("GG-AAAA-BBBB-CCCC", path.read_text())

    def test_existing_signed_receipt_survives_failed_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pro_license.json"
            self.activate(path)
            before = path.read_bytes()
            with patch("licensing.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaisesRegex(LicenseError, "couldn't be saved"):
                    self.activate(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(read_edition(path, self.public).is_pro)
            self.assertEqual(list(Path(directory).glob(".pro_license.json.*.tmp")), [])

    def test_server_redirect_is_refused_even_if_response_contains_valid_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pro_license.json"
            with self.assertRaisesRegex(LicenseError, "redirected unexpectedly"):
                self.activate(path, server=lambda req, timeout=10:
                              RedirectingServer(self.signed()))
            self.assertFalse(path.exists())

    def test_activation_config_rejects_credential_exposure_and_nonstandard_ports(self):
        safe = ("https://license.example.test",
                "https://license.example.test/api/activate",
                "https://license.example.test:443/api/activate")
        for url in safe:
            with self.subTest(url=url):
                self.assertTrue(activation_ready(url, self.public))
        bad = (
            "http://license.example.test/api/activate",
            "https://u:p@license.example.test/api/activate",
            "https://license.example.test:8080/api/activate",
            "https://license.example.test/api/activate?key=secret",
            "https://license.example.test/api/activate#fragment",
            "https://license.example.test/api/\nactivate",
            "https://license.example.test\\@attack.example/api/activate",
        )
        for url in bad:
            with self.subTest(url=url):
                self.assertFalse(activation_ready(url, self.public))

    def test_forged_online_response_does_not_clobber_existing_paid_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pro_license.json"
            self.activate(path)
            before = path.read_bytes()
            bogus = b'{"payload":{"app":"gamegrave","edition":"pro"},"signature":"forged"}'
            with self.assertRaises(LicenseError):
                self.activate(path, server=lambda req, timeout=10: io.BytesIO(bogus))
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(read_edition(path, self.public).is_pro)


if __name__ == "__main__":
    unittest.main()
