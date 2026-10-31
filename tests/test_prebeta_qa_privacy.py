"""Pre-beta report is strictly aggregate and NEVER self-certifies milestones."""
from __future__ import annotations

import json
import unittest

from prebeta_qa import build_prebeta_report


class FieldReportPrivacyTests(unittest.TestCase):
    def test_unsafe_raw_filenames_game_names_and_paths_never_escape(self):
        user_value = "C:/Users/PrivatePerson/SavedGames/important.sav"
        m2 = {
            "games_by_launcher": {"Steam": 3, user_value: 99},
            "mod_roots_by_source": {"Vortex": 2, user_value: 99},
            "recorded_manager_profiles": 4,
            "conflicting_ownership_claims": 1,
            "unresolved_locations": 3,
            "private_mod_profile_name": user_value,
        }
        m3 = {
            "all_passed": False,
            "checks": [
                {"test": user_value, "status": "PASS"},
                {"test": "bad", "status": "FAIL", "reason": user_value},
            ],
            "user_path": user_value,
        }
        outcome = build_prebeta_report(
            os_release="Windows 11", os_build="26100",
            m2_report=m2, m3_report=m3, m1_status="PASS",
            errors={"M1": "RuntimeError", "M2": user_value})
        payload = json.dumps(outcome)
        self.assertNotIn("PrivatePerson", payload)
        self.assertNotIn(".sav", payload)
        self.assertEqual(outcome["m2_games_by_launcher"]["Steam"], 3)
        self.assertEqual(outcome["m2_mod_roots_by_source"]["Vortex"], 2)
        self.assertEqual(outcome["m3_disposable_tests"]["failed"], 1)
        self.assertEqual(outcome["error_kinds"]["M2"], "Other")
        self.assertFalse(outcome["m6_beta_authorized"])
        self.assertFalse(outcome["m7_1_0_release_approved"])
        self.assertFalse(outcome["automatic_delete_authorized"])

    def test_incomplete_empty_report_does_not_fake_pass(self):
        report = build_prebeta_report(
            os_release="not real", os_build="garbled",
            m1_status="NOT_RUN", m2_report=None, m3_report=None)
        self.assertEqual(report["windows_release"], "Unknown Windows")
        self.assertEqual(report["windows_build"], "unknown")
        self.assertEqual(report["m2_read_only_scan"], "FAIL")
        self.assertEqual(report["m3_disposable_tests"]["executed"], 0)
        self.assertFalse(report["m3_disposable_tests"]["all_passed"])
        self.assertFalse(report["m1_windows_10_11_human_acceptance"])

    def test_all_synthetic_pass_still_never_means_stable(self):
        report = build_prebeta_report(
            os_release="Windows 10", os_build="19045", m1_status="PASS",
            m2_report={"games_by_launcher": {"Steam": 2}},
            m3_report={"all_passed": True, "checks": [
                {"test": "A", "status": "PASS"},
                {"test": "B", "status": "PASS"}]})
        self.assertEqual(report["m3_disposable_tests"]["passed"], 2)
        self.assertTrue(report["m3_disposable_tests"]["all_passed"])
        for flag in ("m1_windows_10_11_human_acceptance",
                     "m2_human_launcher_comparison",
                     "m4_physical_dpi_and_accessibility_verified",
                     "m5_signed_installer_and_paid_entitlements_verified",
                     "m7_1_0_release_approved"):
            self.assertFalse(report[flag])

    def test_unknown_recovery_status_is_rejected(self):
        with self.assertRaises(ValueError):
            build_prebeta_report(
                os_release="Windows 10", os_build="19045",
                m1_status="DELETED", m2_report=None, m3_report=None)

    def test_invalid_counts_cannot_be_inflated(self):
        report = build_prebeta_report(
            os_release="Windows 10", os_build="19045", m1_status="FAIL",
            m2_report={"games_by_launcher": {"Steam": True, "Epic Games": -42}},
            m3_report=None)
        self.assertEqual(report["m2_games_by_launcher"]["Steam"], 0)
        self.assertEqual(report["m2_games_by_launcher"]["Epic Games"], 0)


if __name__ == "__main__":
    unittest.main()
