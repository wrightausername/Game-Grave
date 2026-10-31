"""Fail-closed signed Game Grave 1.0 installer check for a trusted release operator.

Does not create signatures, change files, publish releases or accept user data.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_identity import verify_signed_candidate, ReleaseVerificationError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify Game Grave 1.0 signed stable candidate")
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--ledger", type=Path,
                        default=Path(__file__).resolve().parents[1] / "release_gate_status.json")
    parser.add_argument("--trusted-sha256", required=True,
                        help="SHA-256 from a separately authenticated reviewer channel")
    parser.add_argument("--reviewed-source-commit", required=True,
                        help="The independently reviewed source commit SHA, never from this build's own manifest")
    parser.add_argument("--pinned-publisher-thumbprint", required=True,
                        help="Trusted Windows signing certificate thumbprint from a separate secure record")
    args = parser.parse_args(argv)
    try:
        result = verify_signed_candidate(
            args.installer, args.manifest, args.ledger,
            expected_sha256=args.trusted_sha256,
            expected_source_commit=args.reviewed_source_commit,
            trusted_publisher_thumbprint=args.pinned_publisher_thumbprint)
    except (ReleaseVerificationError, OSError, ValueError) as exc:
        print("RELEASE BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    print("The reviewed installer identity passed. Publishing remains a separate authorized action.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
