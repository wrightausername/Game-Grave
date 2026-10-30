"""M5 authenticated on-demand update discovery. All manifests and keys are synthetic."""
import base64
import io
import json
import unittest
from dataclasses import replace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from updates import (
    UpdateError, check_for_updates, parse_signed_manifest, update_ready,
    _https_url, MANIFEST_BYTES_LIMIT,
)


class Response(io.BytesIO):
    def __init__(self, data, url="https://updates.example.test/stable.json"):
        super().__init__(data)
        self.url = url
    def geturl(self):
        return self.url


class SignedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode("ascii")
        self.metadata = "https://updates.example.test/stable.json"
        self.host = "downloads.example.test"
        self.installed = "1.0.0"
        self.payload = {
            "schema": 1, "app": "gamegrave", "channel": "stable",
            "version": "1.0.1",
            "download_url": "https://downloads.example.test/releases/GameGrave_Setup_v1.0.1.exe",
            "installer_sha256": "ab" * 32,
            "size_bytes": 12_345_678,
        }

    def signed(self, payload=None):
        data = self.payload if payload is None else payload
        sig = self.private.sign(json.dumps(data, sort_keys=True, ensure_ascii=True,
                                           separators=(",", ":")).encode("utf-8"))
        return json.dumps({"payload": data,
                           "signature": base64.b64encode(sig).decode("ascii")},
                          separators=(",", ":")).encode("utf-8")

    def args(self):
        return dict(manifest_url=self.metadata, public_key_b64=self.public,
                    download_host=self.host, installed_version=self.installed)

    def test_not_configured_never_contacts_network_and_remains_optional(self):
        self.assertFalse(update_ready())
        touched = []
        with self.assertRaisesRegex(UpdateError, "No network request was made"):
            check_for_updates(opener=lambda *a, **kw: touched.append(a))
        self.assertEqual(touched, [])
        self.assertFalse(touched)

    def test_valid_signature_reports_newer_without_downloading_installer(self):
        requests = []
        def server(req, timeout=8):
            requests.append((req, timeout))
            return Response(self.signed())
        result = check_for_updates(**self.args(), opener=server)
        self.assertEqual(result.status, "available")
        self.assertEqual(result.installed_version, "1.0.0")
        self.assertEqual(result.release.version, "1.0.1")
        self.assertEqual(result.release.installer_sha256, "ab" * 32)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0].full_url, self.metadata)
        self.assertEqual(requests[0][0].get_method(), "GET")
        self.assertEqual(requests[0][1], 8)
        self.assertNotIn("GameGrave_Setup", requests[0][0].full_url)

    def test_current_and_older_signed_metadata_do_not_trigger_downgrade(self):
        for version in ("1.0.0", "0.9.9"):
            with self.subTest(version=version):
                result = check_for_updates(**self.args(), opener=lambda req, timeout=8:
                    Response(self.signed({**self.payload, "version": version})))
                self.assertEqual(result.status, "current")

    def test_tampered_signed_metadata_or_fake_signature_fails_closed(self):
        envelope = json.loads(self.signed())
        envelope["payload"]["download_url"] = "https://evil.example.test/evil.exe"
        with self.assertRaises(UpdateError):
            parse_signed_manifest(json.dumps(envelope).encode(), self.public, self.host)
        envelope = json.loads(self.signed())
        envelope["signature"] = base64.b64encode(b"\x00" * 64).decode()
        with self.assertRaises(UpdateError):
            parse_signed_manifest(json.dumps(envelope).encode(), self.public, self.host)

    def test_strict_schema_and_urls_are_enforced_even_if_signed(self):
        cases = (
            {"channel": "preview"},
            {"app": "another-app"},
            {"schema": True},
            {"version": "1.0.1-rc1"},
            {"version": "01.0.1"},
            {"version": "1.0.99999999999999999999999999"},
            {"download_url": "http://downloads.example.test/releases/update.exe"},
            {"download_url": "https://evil.example.test/releases/update.exe"},
            {"download_url": "https://downloads.example.test@evil.example.test/release.exe"},
            {"download_url": "https://downloads.example.test:8443/release.exe"},
            {"download_url": "https://downloads.example.test/release.exe?secret=yes"},
            {"download_url": "https://downloads.example.test/releases/../update.exe"},
            {"download_url": "https://downloads.example.test/releases/%2e%2e/update.exe"},
            {"download_url": "https://downloads.example.test/release.zip"},
            {"installer_sha256": "AB" * 32},
            {"installer_sha256": "x" * 64},
            {"size_bytes": True},
            {"size_bytes": 0},
            {"size_bytes": 6 * 1024 ** 3},
        )
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(UpdateError):
                parse_signed_manifest(self.signed({**self.payload, **changed}),
                                      self.public, self.host)

    def test_duplicate_keys_nonfinite_oversize_and_extra_fields_rejected(self):
        dup = (b'{"payload":{},"payload":{},"signature":"fake"}')
        for raw in (dup, b'NaN', b'{"payload": NaN, "signature": "fake"}',
                    b"z" * (MANIFEST_BYTES_LIMIT + 1),
                    self.signed({**self.payload, "unexpected": "yes"})):
            with self.subTest(head=raw[:30]), self.assertRaises(UpdateError):
                parse_signed_manifest(raw, self.public, self.host)

    def test_redirected_metadata_is_never_accepted_even_with_valid_signature(self):
        with self.assertRaisesRegex(UpdateError, "redirected"):
            check_for_updates(**self.args(), opener=lambda req, timeout=8:
                Response(self.signed(), url="https://updates.example.test/unexpected.json"))

    def test_https_config_requires_pinned_host_valid_key_and_version(self):
        self.assertTrue(update_ready(**self.args()))
        for broken in (
            {"manifest_url": "http://updates.example.test/stable.json"},
            {"manifest_url": "https://name@updates.example.test/stable.json"},
            {"public_key_b64": ""},
            {"download_host": "downloads.example.test/evil"},
            {"installed_version": "2.4-preview"},
        ):
            with self.subTest(broken=broken):
                self.assertFalse(update_ready(**{**self.args(), **broken}))
        self.assertEqual(
            _https_url("https://downloads.example.test:443/release.exe",
                       host="downloads.example.test"),
            "https://downloads.example.test:443/release.exe")


if __name__ == "__main__":
    unittest.main()
