"""Optional, explicit, signed lifetime Pro licensing. Free never needs a key.

Pro grants MUST originate from a server-side private Ed25519 signing key. No
unsigned setting or HTTP response can unlock Pro. The activation endpoint is
left unconfigured in preview builds; this is not a pretend working key system.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core import config_dir
from license_config import ACTIVATION_URL, ED25519_PUBLIC_KEY_BASE64

PRODUCT_ID = "gamegrave"
RECEIPT_NAME = "pro_license.json"
MAX_RECEIPT_BYTES = 8192
MAX_RESPONSE_BYTES = 8192
MAX_KEY_LENGTH = 100


class LicenseError(ValueError):
    """An activation, signature or entitlement validation failure."""


@dataclass(frozen=True)
class Edition:
    name: str
    message: str
    license_id: str = ""

    @property
    def is_pro(self) -> bool:
        return self.name == "Pro"


def free_edition() -> Edition:
    return Edition("Free", "Free forever. No key or account needed.")


def activation_ready(url: str = ACTIVATION_URL, public_key: str = ED25519_PUBLIC_KEY_BASE64) -> bool:
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    if not isinstance(public_key, str):
        return False
    try:
        return len(base64.b64decode(public_key, validate=True)) == 32
    except (ValueError, base64.binascii.Error):
        return False


def normalize_key(value: str) -> str:
    """Avoid storing license keys; normalize only for user-initiated activation."""
    if not isinstance(value, str):
        raise LicenseError("Enter a valid license key.")
    key = re.sub(r"\s+", "", value).upper()
    if (not 12 <= len(key) <= MAX_KEY_LENGTH or
            not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", key)):
        raise LicenseError("The key format doesn't look right. Check it and try again.")
    return key


def _payload_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("utf-8")


def verify_receipt(receipt: dict, public_key_b64: str) -> Edition:
    """Verify an immutable, server-signed lifetime Pro entitlement.

    Expected envelope {"payload": {"app": "gamegrave", "edition": "pro",
    "license_id": "opaque-id", "type": "lifetime", "schema": 1},
    "signature": "base64-Ed25519-signature"}.
    """
    if not isinstance(receipt, dict) or set(receipt) != {"payload", "signature"}:
        raise LicenseError("The activation receipt is invalid.")
    payload, signature = receipt["payload"], receipt["signature"]
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise LicenseError("The activation receipt is invalid.")
    if (payload.get("app") != PRODUCT_ID or payload.get("edition") != "pro" or
            payload.get("type") != "lifetime" or payload.get("schema") != 1 or
            not isinstance(payload.get("license_id"), str) or
            not 1 <= len(payload["license_id"]) <= 120 or
            set(payload) != {"app", "edition", "type", "schema", "license_id"}):
        raise LicenseError("The receipt does not grant Game Grave lifetime Pro.")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise LicenseError("This build is missing the Pro license verifier.") from exc
    try:
        public_key = base64.b64decode(public_key_b64, validate=True)
        sig = base64.b64decode(signature, validate=True)
        if len(public_key) != 32 or len(sig) != 64:
            raise LicenseError("Invalid license signature.")
        Ed25519PublicKey.from_public_bytes(public_key).verify(sig, _payload_bytes(payload))
    except (ValueError, TypeError, InvalidSignature, base64.binascii.Error) as exc:
        raise LicenseError("This license couldn't be verified.") from exc
    return Edition("Pro", "Lifetime Pro is activated on this PC.", payload["license_id"])


def receipt_path() -> Path:
    return config_dir() / RECEIPT_NAME


def read_edition(path: Path | None = None, public_key: str = ED25519_PUBLIC_KEY_BASE64) -> Edition:
    """Bad, modified or missing proof ALWAYS fails closed to Free."""
    target = path if path is not None else receipt_path()
    try:
        if target.stat().st_size > MAX_RECEIPT_BYTES:
            return free_edition()
        receipt = json.loads(target.read_text(encoding="utf-8"))
        return verify_receipt(receipt, public_key)
    except (OSError, ValueError, UnicodeError, TypeError):
        return free_edition()


def activate_key(key: str, *, url: str = ACTIVATION_URL,
                 public_key: str = ED25519_PUBLIC_KEY_BASE64,
                 opener=None, destination: Path | None = None) -> Edition:
    """Call the license server only on an explicit Activate click.

    The server verifies payment, key limits and returns a SIGNED entitlement;
    server response alone is NEVER trusted. Key is not saved or logged.
    """
    normalized_key = normalize_key(key)
    if not activation_ready(url, public_key):
        raise LicenseError("Pro activation is not available in this preview yet. Free is fully usable.")
    body = json.dumps({"product": PRODUCT_ID, "license_key": normalized_key}).encode("utf-8")
    request = urllib.request.Request(url, body,
        {"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        response = (opener or urllib.request.urlopen)(request, timeout=10)
        with response as res:
            data = res.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise LicenseError("The activation response was too large.")
        envelope = json.loads(data.decode("utf-8"))
        edition = verify_receipt(envelope, public_key)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LicenseError("Can't reach the activation service. Check your connection and try again.") from exc
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise LicenseError("The activation service returned an invalid response.") from exc
    target = destination if destination is not None else receipt_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
        tmp.replace(target)
    except OSError as exc:
        raise LicenseError("Pro was verified but couldn't be saved. Check folder permissions.") from exc
    return edition


def remove_local_activation(path: Path | None = None) -> None:
    """Deactivate this installation locally only; does not revoke server license."""
    target = path if path is not None else receipt_path()
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        raise LicenseError("Couldn't remove the local activation file.") from exc
