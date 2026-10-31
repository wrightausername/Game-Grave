"""Local-only M6 beta template/aggregate CLI. Does not recruit or contact testers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from beta_analysis import (
    QUESTIONNAIRE_VERSION, analyze_responses, blank_response_form,
    read_local_response_batch, write_output_new,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Frozen Game Grave beta response tools")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--blank-form", type=Path,
                       help="Create an empty questionnaire record (no fabricated answers)")
    group.add_argument("--analyze", type=Path,
                       help="Read an explicitly selected local JSON batch of completed responses")
    parser.add_argument("--output", type=Path, help="New aggregate JSON output path")
    args = parser.parse_args(argv)
    try:
        if args.blank_form:
            write_output_new(args.blank_form, blank_response_form())
            print("Created blank GG-BETA-Q1 record. Read BETA_TEST_PROTOCOL.md "
                  "for the unchanged wording and safe task order.")
        else:
            if not args.output:
                parser.error("--output is required with --analyze")
            entries = read_local_response_batch(args.analyze)
            outcome = analyze_responses(entries)
            write_output_new(args.output, outcome)
            print(f"Analyzed {outcome['response_count']} responses from "
                  f"{QUESTIONNAIRE_VERSION}. Saved counts-only local report.")
            print(f"P0/P1 issue reports: {outcome['blocking_p0_p1_reports']}. "
                  "Human beta/release gate remains OPEN.")
        return 0
    except (OSError, ValueError) as exc:
        print("Response file not accepted: " + type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
