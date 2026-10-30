"""Release audit refuses unsupported milestones and fake approval evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.release_audit import IDS, review, main


class ReleaseAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(
            (Path(__file__).resolve().parents[1] / "release_gate_status.json").read_text())

    def test_current_build_is_properly_blocked(self):
        result = review(self.ledger)
        self.assertFalse(result["ready"])
        self.assertEqual(result["milestones"], 7)
        self.assertEqual(len(result["passed"]), 0)
        self.assertGreater(len(result["pending"]), 20)

    def test_strict_command_fails_until_signed_off(self):
        with tempfile.TemporaryDirectory() as home:
            file = Path(home) / "gates.json"
            file.write_text(json.dumps(self.ledger))
            self.assertEqual(main(["--ledger", str(file), "--strict"]), 2)
            self.assertEqual(main(["--ledger", str(file)]), 0)

    def test_single_missing_or_wrong_milestone_fails_closed(self):
        data = copy.deepcopy(self.ledger)
        data["milestones"].pop(3)
        with self.assertRaises(ValueError):
            review(data)
        data = copy.deepcopy(self.ledger)
        data["milestones"][0]["id"] = "M8"
        with self.assertRaises(ValueError):
            review(data)

    def test_forged_pass_without_evidence_or_human_verifier_rejected(self):
        data = copy.deepcopy(self.ledger)
        row = data["milestones"][0]["gates"][0]
        row["status"] = "passed"
        with self.assertRaisesRegex(ValueError, "evidence URL"):
            review(data)
        row["evidence_url"] = "https://github.com/example/example/actions/runs/1"
        with self.assertRaisesRegex(ValueError, "real verifier"):
            review(data)
        row["verified_by"] = "TODO"
        with self.assertRaisesRegex(ValueError, "real verifier"):
            review(data)

    def test_all_passed_is_still_blocked_without_final_status(self):
        data = copy.deepcopy(self.ledger)
        for milestone in data["milestones"]:
            for row in milestone["gates"]:
                row["status"] = "passed"
                row["evidence_url"] = milestone["issue_url"]
                row["verified_by"] = "human QA reviewer"
        self.assertFalse(review(data)["ready"])
        data["status"] = "READY"
        self.assertTrue(review(data)["ready"])
        self.assertEqual(len(review(data)["passed"]), sum(
            len(item["gates"]) for item in data["milestones"]))


if __name__ == "__main__":
    unittest.main()
