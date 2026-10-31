"""M6 frozen closed-beta response validation and privacy-preserving analysis.

No uploads, contacts, tracking, enrollment, user IDs, paths, or unredacted
free-text exports. This is preparation, NOT authorization to start a beta.
All acceptance thresholds and tester independence require human approval.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import median

SCHEMA = 1
QUESTIONNAIRE_VERSION = "GG-BETA-Q1 / 2026-10-30"
TASK_IDS = tuple(f"T{i:02}" for i in range(1, 13))
RATING_IDS = tuple(f"Q{i:02}" for i in range(1, 11))
TASK_OUTCOMES = (
    "succeeded without assistance", "succeeded with assistance",
    "failed", "not applicable",
)
Q11_OPTIONS = ("Yes", "Maybe", "No")
ISSUE_SEVERITIES = ("P0", "P1", "P2", "P3")
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_RESPONSES = 200
MAX_ISSUES_PER_RESPONSE = 25

# Exact text from BETA_TEST_PROTOCOL.md, version Q1; do not edit mid-beta.
FROZEN_RATING_QUESTIONS = {
    "Q01": "It was easy to understand what Game Grave does before I started scanning.",
    "Q02": "I could tell which game and mod information Game Grave had actually verified.",
    "Q03": "The Game DNA relationship graphic helped me understand what belongs together.",
    "Q04": "The Mod Radar visual explanation helped me understand why some files require review.",
    "Q05": "I understood the difference between apparently occupied space and disk space I would actually free.",
    "Q06": "The Graveyard clearly explained which items were protected and why.",
    "Q07": "I felt confident that Game Grave would not delete my real games, mods, or saves without permission.",
    "Q08": "The Undo Center recovery steps were easy to follow for my disposable test file.",
    "Q09": "The Resurrection Kit preview and rehearsal made its limitations clear.",
    "Q10": "The interface was easy to navigate, read, and use at my screen size.",
}
Q11_TEXT = "Would you install Game Grave again on your own gaming PC?"
Q12_TEXT = "What was the single most confusing, unsafe-feeling, broken, or missing part of your experience?"


def _exact_keys(data: object, keys: set[str], *, optional: set[str] | None = None) -> None:
    if not isinstance(data, dict):
        raise ValueError("Expected an object")
    optional = optional or set()
    if set(data) - (keys | optional) or keys - set(data):
        raise ValueError("Beta response has missing or unsupported fields")


def validate_response(response: dict) -> dict:
    """Reject partial, mixed-version, malformed or unexpected records.

    Returns the original JSON object for in-memory aggregate use only. It is
    never written back to output or included in errors.
    """
    _exact_keys(response, {"schema", "questionnaire_version", "build_id", "os",
                           "tasks", "ratings", "q11", "issues"}, {"q12"})
    if response["schema"] != SCHEMA or isinstance(response["schema"], bool):
        raise ValueError("Unsupported beta response schema")
    if response["questionnaire_version"] != QUESTIONNAIRE_VERSION:
        raise ValueError("Questionnaire differs from frozen GG-BETA-Q1 wording")
    build_id = response["build_id"]
    if not isinstance(build_id, str) or not re.fullmatch(r"[A-Za-z0-9._+:-]{4,80}", build_id):
        raise ValueError("A non-personal, explicit tested build ID is required")
    if response["os"] not in ("Windows 10", "Windows 11"):
        raise ValueError("Only supported Windows beta OS groups are accepted")
    _exact_keys(response["tasks"], set(TASK_IDS))
    for outcome in response["tasks"].values():
        if outcome not in TASK_OUTCOMES:
            raise ValueError("Invalid task outcome")
    _exact_keys(response["ratings"], set(RATING_IDS))
    for rating in response["ratings"].values():
        if rating != "N/A" and not (type(rating) is int and 1 <= rating <= 5):
            raise ValueError("Ratings must be 1–5 or N/A, never missing or boolean")
    if response["q11"] not in Q11_OPTIONS:
        raise ValueError("Q11 must be Yes, Maybe or No")
    if "q12" in response and (not isinstance(response["q12"], str)
                              or len(response["q12"]) > 2000):
        raise ValueError("Optional Q12 must be short text")
    if not isinstance(response["issues"], list) or len(response["issues"]) > MAX_ISSUES_PER_RESPONSE:
        raise ValueError("Issue list exceeds the safe local analysis limit")
    for issue in response["issues"]:
        _exact_keys(issue, {"task_id", "expected", "actual", "steps_disposable", "severity"})
        if issue["task_id"] not in TASK_IDS or issue["severity"] not in ISSUE_SEVERITIES:
            raise ValueError("Issue task or severity is invalid")
        for field in ("expected", "actual", "steps_disposable"):
            if not isinstance(issue[field], str) or len(issue[field]) > 1200:
                raise ValueError("Issue text must be bounded")
    return response


def analyze_responses(responses: list[dict]) -> dict:
    """Return counts and medians only. Never return question/issue free text."""
    if not isinstance(responses, list) or not 1 <= len(responses) <= MAX_RESPONSES:
        raise ValueError("Choose between 1 and 200 responses")
    values = [validate_response(item) for item in responses]
    builds = {item["build_id"] for item in values}
    if len(builds) != 1:
        raise ValueError("Different tested builds must be analyzed separately")
    tasks = {}
    for task in TASK_IDS:
        count = Counter(row["tasks"][task] for row in values)
        tasks[task] = {status: count[status] for status in TASK_OUTCOMES}
    ratings = {}
    for question in RATING_IDS:
        chosen = [row["ratings"][question] for row in values]
        real = [n for n in chosen if type(n) is int]
        frequency = Counter(real)
        ratings[question] = {
            "median": median(real) if real else None,
            "distribution": {str(n): frequency[n] for n in range(1, 6)},
            "not_applicable": len(chosen) - len(real),
        }
    issues = [issue for row in values for issue in row["issues"]]
    severity = Counter(issue["severity"] for issue in issues)
    task_issues = Counter(issue["task_id"] for issue in issues)
    willingness = Counter(row["q11"] for row in values)
    return {
        "schema": SCHEMA,
        "questionnaire_version": QUESTIONNAIRE_VERSION,
        "tested_build_id": next(iter(builds)),
        "response_count": len(values),
        "tester_independence_verified": False,
        "os_counts": {os_name: sum(row["os"] == os_name for row in values)
                      for os_name in ("Windows 10", "Windows 11")},
        "task_outcomes": tasks,
        "question_ratings": ratings,
        "install_again": {option: willingness[option] for option in Q11_OPTIONS},
        "issue_severity_counts": {level: severity[level] for level in ISSUE_SEVERITIES},
        "issue_task_counts": {task: task_issues[task] for task in TASK_IDS},
        "optional_q12_count": sum(bool(row.get("q12", "").strip()) for row in values),
        "blocking_p0_p1_reports": severity["P0"] + severity["P1"],
        "critical_p1_free": severity["P0"] + severity["P1"] == 0,
        "m6_beta_complete": False,
        "m7_1_0_release_authorized": False,
        "note": (
            "Counts do not establish independent testers, release acceptance, "
            "human reproduction of issues or preapproved thresholds. "
            "No user-submitted free text, IDs or local paths are included."
        ),
    }


def _reject_duplicate_keys(items):
    output = {}
    for key, value in items:
        if key in output:
            raise ValueError("Duplicate JSON key")
        output[key] = value
    return output


def read_local_response_batch(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("A local response JSON file smaller than 4 MiB is required")
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Malformed response JSON") from exc
    _exact_keys(payload, {"schema", "responses"})
    if payload["schema"] != SCHEMA or isinstance(payload["schema"], bool):
        raise ValueError("Unsupported response batch format")
    return payload["responses"]


def blank_response_form(build_id: str = "1.0.0-rc-placeholder") -> dict:
    """Template with no inferred or fabricated tester answers."""
    return {
        "schema": SCHEMA, "questionnaire_version": QUESTIONNAIRE_VERSION,
        "build_id": build_id, "os": None,
        "tasks": {task: None for task in TASK_IDS},
        "ratings": {question: None for question in RATING_IDS},
        "q11": None, "q12": "", "issues": [],
    }


def write_output_new(path: Path, value: dict) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Output exists; no report overwritten")
    with target.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
