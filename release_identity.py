"""M5/M7 fail-closed local signed Game Grave release identity verifier.

A build manifest alone is self-asserted data and never proves authenticity.
Shipping requires independently supplied trusted SHA-256, reviewed source
commit, pinned Windows publisher certificate, valid Authenticode with timestamp,
AND all seven human-signed release gates. Never signs, uploads or executes an
installer, handles payment keys or contacts the internet.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core import _has_reparse_component
from tools.release_audit import review

MAX_MANIFEST_BYTES = 24 * 1024
MAX_LEDGER_BYTES = 128 * 1024
MANIFEST_KEYS = frozenset({
    "schema", "product", "version", "installer", "installer_sha256",
    "source_commit", "signed", "release_approved", "build_kind",
})
SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
COMMIT_RE = re.compile(r"[0-9a-f]{40}", re.ASCII)
THUMBPRINT_RE = re.compile(r"[A-F0-9]{40}", re.ASCII)


class ReleaseVerificationError(ValueError):
    """A release evidence gate did not pass."""


@dataclass(frozen=True)
class AuthenticodeEvidence:
    status: str
    publisher_thumbprint: str
    timestamp_present: bool


def _reject_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ReleaseVerificationError("Duplicate JSON field in release evidence")
        seen[key] = value
    return seen


def _read_bounded_json(path: Path, limit: int) -> dict:
    if not isinstance(path, Path) or _has_reparse_component(path):
        raise ReleaseVerificationError("Release evidence path is linked or redirected")
    if not path.is_file() or path.stat().st_size > limit:
        raise ReleaseVerificationError("Release evidence is missing or oversized")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReleaseVerificationError("Release evidence JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ReleaseVerificationError("Release evidence is not an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def windows_authenticode(path: Path) -> AuthenticodeEvidence:
    """Query native Windows certificate trust, including a timestamp chain.

    No unquoted shell input, no network request initiated by Game Grave, and
    no installer execution. Windows itself may consult certificate revocation
    providers depending on local trust policy.
    """
    if os.name != "nt":
        raise ReleaseVerificationError("Windows Authenticode verification requires Windows")
    literal = "'" + str(path).replace("'", "''") + "'"
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "$target = " + literal + "\n"
        "$s = Get-AuthenticodeSignature -LiteralPath $target\n"
        "if ($null -eq $s) { throw 'Signature unavailable' }\n"
        "$v = [pscustomobject]@{"
        "status=[string]$s.Status;"
        "thumbprint=[string]$s.SignerCertificate.Thumbprint;"
        "timestamped=[bool]($null -ne $s.TimeStamperCertificate)"
        "}\n"
        "$v | ConvertTo-Json -Compress\n"
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        run = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-EncodedCommand", encoded],
            text=True, capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if run.returncode:
            raise ReleaseVerificationError("Authenticode check did not complete")
        info = json.loads(run.stdout)
        if not isinstance(info, dict) or set(info) != {"status", "thumbprint", "timestamped"}:
            raise ReleaseVerificationError("Authenticode output was malformed")
        if not isinstance(info["timestamped"], bool):
            raise ReleaseVerificationError("Timestamp result was malformed")
        return AuthenticodeEvidence(
            str(info["status"]),
            str(info["thumbprint"]).upper(),
            info["timestamped"],
        )
    except (OSError, TimeoutError, ValueError, UnicodeError,
            subprocess.TimeoutExpired) as exc:
        raise ReleaseVerificationError("Unable to verify Windows publisher signature") from exc


def verify_signed_candidate(
    installer: Path,
    manifest: Path,
    ledger: Path,
    *,
    expected_sha256: str,
    expected_source_commit: str,
    trusted_publisher_thumbprint: str,
) -> dict:
    """Verify exactly reviewed installer bytes and unambiguous human gate ledger.

    The three expected values are supplied independently by the trusted
    release reviewer; taking them from the candidate's own JSON would not
    establish identity.
    """
    if (not isinstance(expected_sha256, str) or
            SHA256_RE.fullmatch(expected_sha256) is None or
            not isinstance(expected_source_commit, str) or
            COMMIT_RE.fullmatch(expected_source_commit) is None or
            not isinstance(trusted_publisher_thumbprint, str) or
            THUMBPRINT_RE.fullmatch(trusted_publisher_thumbprint.upper()) is None):
        raise ReleaseVerificationError("Independent release identity inputs are missing or malformed")
    gate = review(_read_bounded_json(Path(ledger), MAX_LEDGER_BYTES))
    if not gate["ready"]:
        raise ReleaseVerificationError(
            f"1.0 release gates are not accepted ({len(gate['pending'])} still pending)")
    path = Path(installer)
    evidence = Path(manifest)
    if _has_reparse_component(path) or not path.is_file() or not path.name.lower().endswith(".exe"):
        raise ReleaseVerificationError("Installer is missing, linked or not an EXE")
    if path.parent.resolve() != evidence.parent.resolve():
        raise ReleaseVerificationError("Build manifest must accompany the exact installer")
    metadata = _read_bounded_json(evidence, MAX_MANIFEST_BYTES)
    if (set(metadata) != MANIFEST_KEYS or type(metadata.get("schema")) is not int
            or metadata["schema"] != 1 or metadata["product"] != "Game Grave"
            or metadata["version"] != "1.0.0"
            or metadata["installer"] != path.name
            or metadata["installer_sha256"] != expected_sha256
            or metadata["source_commit"] != expected_source_commit
            or metadata["signed"] is not True
            or metadata["release_approved"] is not True
            or metadata["build_kind"] != "signed-stable"):
        raise ReleaseVerificationError("Signed stable build metadata is missing or mismatched")
    before = path.stat()
    digest = _sha256_file(path)
    if digest != expected_sha256:
        raise ReleaseVerificationError("Installer hash differs from independently reviewed bytes")
    signature = windows_authenticode(path)
    if (signature.status != "Valid" or
            signature.publisher_thumbprint != trusted_publisher_thumbprint.upper() or
            signature.timestamp_present is not True):
        raise ReleaseVerificationError("Windows publisher trust, pinned certificate or timestamp failed")
    after = path.stat()
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
         before.st_nlink) !=
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
         after.st_nlink)) or _sha256_file(path) != expected_sha256:
        raise ReleaseVerificationError("Installer changed while verifying signature")
    return {
        "schema": 1,
        "product": "Game Grave",
        "release": "1.0.0",
        "source_commit": expected_source_commit,
        "installer_sha256": digest,
        "publisher_thumbprint": signature.publisher_thumbprint,
        "authenticode_status": "Valid",
        "timestamp_present": True,
        "all_human_release_gates_recorded": True,
        "installer_executed": False,
        "verified": True,
        "note": "Local identity and gate checks passed; distribution still requires authorized publication.",
    }
