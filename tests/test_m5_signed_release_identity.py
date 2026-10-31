"""M5/M7 signed installer preflight: synthetic files only; no actual signing.

Tests mock Authenticode. They verify fail-closed policy, not a production
signature or a released installer.
"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release_identity import (
    AuthenticodeEvidence, ReleaseVerificationError, verify_signed_candidate,
)


class SignedReleasePreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.installer = self.root / "GameGrave_Setup_v1.0.0.exe"
        self.installer.write_bytes(b"disposable unsigned fixture only")
        self.digest = hashlib.sha256(self.installer.read_bytes()).hexdigest()
        self.commit = "a" * 40
        self.thumbprint = "B" * 40
        self.manifest = self.root / "GameGrave_Setup_v1.0.0.build.json"
        self.meta = {
            "schema": 1,
            "product": "Game Grave",
            "version": "1.0.0",
            "installer": self.installer.name,
            "installer_sha256": self.digest,
            "source_commit": self.commit,
            "signed": True,
            "release_approved": True,
            "build_kind": "signed-stable",
        }
        self.ledger = self.root / "release_gate_status.json"
        source = Path(__file__).resolve().parents[1] / "release_gate_status.json"
        self.raw_ledger = json.loads(source.read_text(encoding="utf-8"))
        self.write()

    def write(self):
        self.manifest.write_text(json.dumps(self.meta), encoding="utf-8")
        self.ledger.write_text(json.dumps(self.raw_ledger), encoding="utf-8")

    def pass_all_gates_for_synthetic_policy_test(self):
        self.raw_ledger["status"] = "READY"
        for milestone in self.raw_ledger["milestones"]:
            for gate in milestone["gates"]:
                gate.update({
                    "status": "passed",
                    "evidence_url": "https://example.org/synthetic-test-only",
                    "verified_by": "Synthetic Test Reviewer",
                })
        self.write()

    def check(self):
        return verify_signed_candidate(
            self.installer, self.manifest, self.ledger,
            expected_sha256=self.digest,
            expected_source_commit=self.commit,
            trusted_publisher_thumbprint=self.thumbprint,
        )

    def test_real_pending_release_gates_refuse_before_signature_check(self):
        with patch("release_identity.windows_authenticode") as sig:
            with self.assertRaisesRegex(ReleaseVerificationError, "pending"):
                self.check()
        sig.assert_not_called()

    def test_synthetic_full_gates_and_mocked_signature_pass_policy_only(self):
        self.pass_all_gates_for_synthetic_policy_test()
        evidence = AuthenticodeEvidence("Valid", self.thumbprint, True)
        with patch("release_identity.windows_authenticode", return_value=evidence) as verify:
            result = self.check()
        self.assertTrue(result["verified"])
        self.assertTrue(result["all_human_release_gates_recorded"])
        self.assertFalse(result["installer_executed"])
        verify.assert_called_once_with(self.installer)

    def test_unsigned_manifest_never_passes_even_with_mocked_valid_signature(self):
        self.pass_all_gates_for_synthetic_policy_test()
        self.meta["signed"] = False
        self.meta["release_approved"] = False
        self.meta["build_kind"] = "unsigned-engineering-candidate"
        self.write()
        with patch("release_identity.windows_authenticode") as verify:
            with self.assertRaisesRegex(ReleaseVerificationError, "metadata"):
                self.check()
        verify.assert_not_called()

    def test_altered_installer_or_expected_hash_rejected(self):
        self.pass_all_gates_for_synthetic_policy_test()
        self.installer.write_bytes(b"tampered byte contents")
        with patch("release_identity.windows_authenticode") as verify:
            with self.assertRaisesRegex(ReleaseVerificationError, "hash"):
                self.check()
        verify.assert_not_called()

    def test_publisher_certificate_and_timestamp_must_both_match(self):
        self.pass_all_gates_for_synthetic_policy_test()
        for evidence in (
            AuthenticodeEvidence("Valid", "C" * 40, True),
            AuthenticodeEvidence("UnknownError", self.thumbprint, True),
            AuthenticodeEvidence("Valid", self.thumbprint, False),
        ):
            with self.subTest(value=evidence), \
                 patch("release_identity.windows_authenticode", return_value=evidence):
                with self.assertRaisesRegex(ReleaseVerificationError, "publisher trust"):
                    self.check()

    def test_installer_replacement_during_signature_check_is_refused(self):
        self.pass_all_gates_for_synthetic_policy_test()
        def change_candidate(_path):
            self.installer.write_bytes(b"tamper after first digest")
            return AuthenticodeEvidence("Valid", self.thumbprint, True)
        with patch("release_identity.windows_authenticode", side_effect=change_candidate):
            with self.assertRaisesRegex(ReleaseVerificationError, "changed"):
                self.check()

    def test_duplicate_json_fields_are_rejected(self):
        self.pass_all_gates_for_synthetic_policy_test()
        self.manifest.write_text('{"schema":1,"schema":1}', encoding="utf-8")
        with patch("release_identity.windows_authenticode") as verify:
            with self.assertRaises(ReleaseVerificationError):
                self.check()
        verify.assert_not_called()

    def test_independent_sha_and_commit_are_required(self):
        self.pass_all_gates_for_synthetic_policy_test()
        with self.assertRaises(ReleaseVerificationError):
            verify_signed_candidate(
                self.installer, self.manifest, self.ledger,
                expected_sha256="0" * 64,
                expected_source_commit=self.commit,
                trusted_publisher_thumbprint=self.thumbprint)
        with self.assertRaises(ReleaseVerificationError):
            verify_signed_candidate(
                self.installer, self.manifest, self.ledger,
                expected_sha256=self.digest,
                expected_source_commit="invalid",
                trusted_publisher_thumbprint=self.thumbprint)


if __name__ == "__main__":
    unittest.main()
