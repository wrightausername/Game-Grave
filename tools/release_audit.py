"""Local, deny-by-default Game Grave 1.0 release acceptance report.

This checks that milestones are explicitly signed off with evidence, not that
the evidence is itself truthful. It deliberately never interprets CI as human
Windows QA, and never releases artifacts or accesses the network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


IDS = ("M1", "M2", "M3", "M4", "M5", "M6", "M7")
ISSUE_PREFIX = "https://github.com/wrightausername/Game-Grave/issues/"


def _supported_evidence_url(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 1500 or not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and bool(parsed.path)


def review(document: dict) -> dict:
    """Return all outstanding gates, or fail closed on malformed status data."""
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise ValueError("Release gate ledger has an unsupported schema.")
    if document.get("target_release") != "1.0.0":
        raise ValueError("Release gate ledger does not target Game Grave 1.0.0.")
    if document.get("status") not in ("NOT_READY", "READY"):
        raise ValueError("Release ledger overall status must be NOT_READY or READY.")
    milestones = document.get("milestones")
    if not isinstance(milestones, list) or len(milestones) != len(IDS):
        raise ValueError("The 1.0 release ledger must include all seven milestones.")

    pending, passed = [], []
    for idx, entry in enumerate(milestones):
        if not isinstance(entry, dict) or entry.get("id") != IDS[idx]:
            raise ValueError(f"Missing or out-of-order milestone {IDS[idx]}.")
        if not isinstance(entry.get("title"), str) or not entry["title"].strip():
            raise ValueError(f"{IDS[idx]} is missing its descriptive title.")
        if not isinstance(entry.get("issue_url"), str) or not entry["issue_url"].startswith(ISSUE_PREFIX):
            raise ValueError(f"{IDS[idx]} has no linked Game Grave tracking issue.")
        tasks = entry.get("gates")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"{IDS[idx]} does not declare acceptance gates.")
        unique = set()
        for row in tasks:
            if not isinstance(row, dict):
                raise ValueError(f"{IDS[idx]} has a malformed acceptance gate.")
            name = row.get("name")
            if not isinstance(name, str) or not name.strip() or name in unique:
                raise ValueError(f"{IDS[idx]} has a missing or duplicate gate name.")
            unique.add(name)
            state = row.get("status")
            if state not in ("pending", "passed"):
                raise ValueError(f"{IDS[idx]} gate has unsupported state {state!r}.")
            label = f"{IDS[idx]}: {name}"
            if state == "passed":
                evidence = row.get("evidence_url")
                verifier = row.get("verified_by")
                if not _supported_evidence_url(evidence):
                    raise ValueError(f"{label} is marked passed without an evidence URL.")
                if (not isinstance(verifier, str) or not verifier.strip()
                        or len(verifier) > 150 or verifier.strip().casefold() in
                        {"todo", "tbd", "none", "unknown"}):
                    raise ValueError(f"{label} is marked passed without a real verifier.")
                passed.append(label)
            else:
                pending.append(label)
    complete = (not pending and document["status"] == "READY")
    return {
        "ready": complete,
        "passed": passed,
        "pending": pending,
        "milestones": len(milestones),
        "overall_status": document["status"],
    }


def main(argv=None) -> int:
    command = argparse.ArgumentParser(description="Audit the Game Grave 1.0 release gates.")
    command.add_argument("--ledger", type=Path,
                         default=Path(__file__).resolve().parents[1] / "release_gate_status.json")
    command.add_argument("--strict", action="store_true",
                         help="Exit unsuccessfully until every gate and overall signoff has passed.")
    args = command.parse_args(argv)
    try:
        outcome = review(json.loads(args.ledger.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        print(f"RELEASE BLOCKED: invalid gate ledger: {exc}", file=sys.stderr)
        return 2

    total = len(outcome["passed"]) + len(outcome["pending"])
    status = "READY FOR CANDIDATE REVIEW" if outcome["ready"] else "BLOCKED"
    print(f"Game Grave 1.0.0: {status} ({len(outcome['passed'])}/{total} acceptance gates passed)")
    if outcome["pending"]:
        for name in outcome["pending"]:
            print(f"[PENDING] {name}")
    if not outcome["pending"] and not outcome["ready"]:
        print("[PENDING] Human owner must set overall status READY after final evidence review.")
    # --strict only gates release packaging/tag checks. --report behavior is
    # intentionally successful even while blocked so development CI can run.
    return 0 if outcome["ready"] or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
