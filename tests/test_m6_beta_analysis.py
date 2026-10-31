"""M6 fixed questionnaire and privacy-safe beta aggregation regression tests."""
import json
import tempfile
import unittest
from pathlib import Path

from beta_analysis import (
    FROZEN_RATING_QUESTIONS, QUESTIONNAIRE_VERSION, TASK_IDS, RATING_IDS,
    analyze_responses, blank_response_form, read_local_response_batch,
    validate_response, write_output_new,
)


def response(os_name="Windows 11"):
    result = blank_response_form(build_id="1.0.0-rc1")
    result["os"] = os_name
    result["tasks"] = {k: "succeeded without assistance" for k in TASK_IDS}
    result["ratings"] = {k: 4 for k in RATING_IDS}
    result["q11"] = "Yes"
    return result


class FrozenBetaAnalyzerTests(unittest.TestCase):
    def test_frozen_survey_text_matches_prepared_protocol(self):
        doc = (Path(__file__).resolve().parents[1] / "BETA_TEST_PROTOCOL.md").read_text(encoding="utf-8")
        for q, wording in FROZEN_RATING_QUESTIONS.items():
            self.assertIn(f"**{q}**:", doc)
            self.assertIn(wording, doc)
        self.assertIn(QUESTIONNAIRE_VERSION, doc)
        self.assertEqual(len(TASK_IDS), 12)
        self.assertEqual(len(RATING_IDS), 10)

    def test_aggregate_reports_task_counts_medians_and_os_coverage(self):
        a, b = response("Windows 10"), response("Windows 11")
        b["tasks"]["T06"] = "failed"
        b["tasks"]["T10"] = "not applicable"
        b["ratings"]["Q06"] = 2
        b["ratings"]["Q09"] = "N/A"
        b["q11"] = "Maybe"
        aggregate = analyze_responses([a, b])
        self.assertEqual(aggregate["response_count"], 2)
        self.assertEqual(aggregate["os_counts"], {"Windows 10": 1, "Windows 11": 1})
        self.assertEqual(aggregate["task_outcomes"]["T06"]["failed"], 1)
        self.assertEqual(aggregate["task_outcomes"]["T10"]["not applicable"], 1)
        self.assertEqual(aggregate["question_ratings"]["Q06"]["median"], 3)
        self.assertEqual(aggregate["question_ratings"]["Q09"]["not_applicable"], 1)
        self.assertEqual(aggregate["install_again"]["Yes"], 1)
        self.assertEqual(aggregate["install_again"]["Maybe"], 1)
        self.assertFalse(aggregate["m6_beta_complete"])
        self.assertFalse(aggregate["m7_1_0_release_authorized"])

    def test_privacy_free_text_and_filenames_never_reproduced_in_aggregate(self):
        a = response()
        secret = "C:/Users/PrivateUser/savedgame.sav"
        a["q12"] = "I did not understand " + secret
        a["issues"] = [{
            "task_id": "T06", "expected": "Restored " + secret,
            "actual": "Could not restore " + secret,
            "steps_disposable": "Never use " + secret,
            "severity": "P1",
        }]
        report = analyze_responses([a])
        text = json.dumps(report)
        self.assertNotIn("PrivateUser", text)
        self.assertNotIn(".sav", text)
        self.assertEqual(report["optional_q12_count"], 1)
        self.assertEqual(report["blocking_p0_p1_reports"], 1)
        self.assertFalse(report["critical_p1_free"])
        self.assertFalse(report["m6_beta_complete"])

    def test_missing_question_or_invalid_score_is_rejected(self):
        base = response()
        base["ratings"].pop("Q07")
        with self.assertRaises(ValueError):
            validate_response(base)
        base = response()
        base["ratings"]["Q07"] = True
        with self.assertRaises(ValueError):
            validate_response(base)
        base["ratings"]["Q07"] = 6
        with self.assertRaises(ValueError):
            validate_response(base)

    def test_incompatible_builds_or_quiz_versions_cannot_be_pooled(self):
        a, b = response(), response()
        b["build_id"] = "1.0.0-rc2"
        with self.assertRaises(ValueError):
            analyze_responses([a, b])
        b["build_id"] = a["build_id"]
        b["questionnaire_version"] = "GG-BETA-Q2"
        with self.assertRaises(ValueError):
            analyze_responses([a, b])

    def test_duplicate_json_keys_rejected_and_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "responses.json"
            data.write_text('{"schema":1,"schema":1,"responses":[]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_local_response_batch(data)
            data.write_text(json.dumps({"schema":1,"responses":[response()]}), encoding="utf-8")
            self.assertEqual(len(read_local_response_batch(data)), 1)
            report = Path(folder) / "summary.json"
            write_output_new(report, analyze_responses([response()]))
            prior = report.read_bytes()
            with self.assertRaises(FileExistsError):
                write_output_new(report, {})
            self.assertEqual(report.read_bytes(), prior)

    def test_blank_form_never_fakes_a_beta_response(self):
        blank = blank_response_form()
        self.assertIsNone(blank["q11"])
        self.assertIsNone(blank["ratings"]["Q01"])
        self.assertEqual(blank["issues"], [])
        with self.assertRaises(ValueError):
            validate_response(blank)


if __name__ == "__main__":
    unittest.main()
