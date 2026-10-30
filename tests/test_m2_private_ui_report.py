"""M2 one-click report whitelist excludes all raw paths and private item names."""
import json
import unittest

from mod_radar_audit import private_audit_summary


class PrivateM2AuditTests(unittest.TestCase):
    def test_private_report_exposes_counts_only(self):
        audit = {
            "recorded_games": 1, "manager_profiles": 1,
            "scanned_mod_locations": 3, "scanned_save_locations": 2,
            "associated_mod_locations": 1, "unassigned_mod_locations": 2,
            "ambiguous_claims": 1, "redirected_locations": 0,
            "stale_manager_snapshots": 1, "incomplete_manager_snapshots": 1,
            "enabled_profile_references": 2,
            "disabled_profile_references": 1, "unresolved_records": 2,
            "examples": [{"path": r"C:\Users\PRIVATE_USER\MY_GAME"}],
            "source": "PRIVATE_MOD_NAME", "reason": "PRIVATE_PROFILE_NAME",
        }
        result = private_audit_summary(audit, profiles_examined=True)
        output = json.dumps(result)
        for word in ("PRIVATE_USER", "PRIVATE_MOD_NAME", "MY_GAME", "PRIVATE_PROFILE_NAME",
                     "examples", "source", "reason"):
            self.assertNotIn(word, output)
        self.assertEqual(result["recorded_games"], 1)
        self.assertFalse(result["raw_file_paths_included"])
        self.assertFalse(result["m2_release_accepted"])
        self.assertEqual(result["removal_authorizations"], 0)
        self.assertTrue(result["manager_profiles_examined"])

    def test_missing_profile_scan_is_not_zero_manager_evidence(self):
        result = private_audit_summary({"recorded_games": 0}, profiles_examined=False)
        self.assertFalse(result["manager_profiles_examined"])
        self.assertEqual(result["manager_profiles"], 0)

    def test_count_data_must_be_nonnegative_integer(self):
        for invalid in ("1", -1, 1.5, True, None):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                private_audit_summary({"recorded_games": invalid})


if __name__ == "__main__":
    unittest.main()
