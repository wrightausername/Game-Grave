"""Run the complete Overview mouse/keyboard/state matrix three fresh times."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()/"overview-triple-check"
    report = []
    for number in (1, 2, 3):
        target = output/("pass-"+str(number))
        result = subprocess.run([sys.executable, str(root/"tools/overview_human_walkthrough.py"),
            "--all-controls", "--output", str(target)], cwd=root, capture_output=True, text=True, timeout=150)
        if result.returncode:
            print(result.stdout[-2000:]+result.stderr[-6000:], flush=True)
            raise AssertionError(f"Overview click matrix failed in pass {number}")
        cases = json.loads((target/"overview-human-journeys.json").read_text())
        assert all(case["result"] == "passed" for case in cases)
        report.append(dict(pass_number=number, cases=len(cases), results=cases))
        print(f"PASS {number}: {len(cases)} Overview mouse, keyboard and state journeys.", flush=True)
    (output/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS: {sum(run['cases'] for run in report)} checks across three fresh runs; actual Qt mouse/keyboard events, app state, preferences, dialog actions and close/cancel lifecycle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
