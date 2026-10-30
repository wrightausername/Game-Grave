"""Opt-in, read-only verification of signed Game Grave stable update metadata.

This module never downloads an EXE, launches installers, changes local files,
schedules background checks, or contacts a network while configuration is blank.
A signed manifest is NOT equivalent to Windows Authenticode verification.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature

from update_config import (
    UPDATE_MANIFEST_URL,
    UPDATE_ED25519_PUBLIC_KEY_BASE64,
    UPDATE_DOWNLOAD_HOST,
    UPDATE_INSTALLED_RELEASE_VERSION,
)

APP_ID = "gamegrave"
MANIFEST_BYTES_LIMIT = 8192
MAX_INSTALLER_BYTES = 5 * 1024**3
_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", re.ASCII)


class UpdateError(ValueError):
    """A configuration, authenticity or read-only discovery error."""


@dataclass(frozen=True)
class VerifiedRelease:
    version: str
    download_url: str
    installer_sha256: str
    size_bytes: int
    channel: str


@dataclass(frozen=True)
class UpdateResult:
    status: str  # "available" or "current"; no installed app is changed
    installed_version: str
    release: VerifiedRelease


def _version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or len(value) > 32 or not _SEMVER.fullmatch(value):
        raise UpdateError("Invalid stable release version.")
    components = tuple(int(part) for part in value.split("."))
    if any(component > 999999 for component in components):
        raise UpdateError("Stable release version component is unreasonably large.")
    return components


def _host(value: str) -> str:
    if (not isinstance(value, str) or not 3 <= len(value) <= 253 or
            not _HOST.fullmatch(value) or
            ".." in value or value.startswith(".") or value.endswith(".")):
        raise UpdateError("Update download host is invalid.")
    return value.lower()


def _https_url(value: str, *, host: str | None = None) -> str:
    """Accept one ordinary HTTPS origin, never credentials, redirects or ports."""
    if not isinstance(value, str) or not 12 <= len(value) <= 2048:
        raise UpdateError("Update URL is missing or malformed.")
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise UpdateError("Update URL is malformed.") from exc
    if (parsed.scheme != "https" or not hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.fragment or parsed.query or
            parsed.path in ("", "/") or
            port not in (None, 443) or
            "\\" in value or any(ord(c) < 32 for c in value)):
        raise UpdateError("Update requires an ordinary HTTPS URL.")
    if parsed.hostname != hostname.lower() or (
            host is not None and hostname.lower() != _host(host)):
        raise UpdateError("Update URL host is not approved.")
    # Reject path canonicalization ambiguity before giving a URL to a browser.
    path = urllib.parse.unquote(parsed.path)
    if (not path.startswith("/") or "//" in path or
            any(segment in (".", "..") for segment in path.split("/")) or
            not re.fullmatch(r"/[A-Za-z0-9._/-]+", parsed.path, re.ASCII) or
            any(c in path for c in ("\\", "\x00", "\r", "\n", "@"))):
        raise UpdateError("Update URL path is not approved.")
    return value


def update_ready(manifest_url: str = UPDATE_MANIFEST_URL,
                 public_key_b64: str = UPDATE_ED25519_PUBLIC_KEY_BASE64,
                 download_host: str = UPDATE_DOWNLOAD_HOST,
                 installed_version: str = UPDATE_INSTALLED_RELEASE_VERSION) -> bool:
    try:
        _version(installed_version)
        _https_url(manifest_url)
        _host(download_host)
        public = base64.b64decode(public_key_b64, validate=True)
        return len(public) == 32
    except (UpdateError, TypeError, ValueError, binascii.Error):
        return False


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise UpdateError("Update metadata has duplicate fields.")
        result[key] = value
    return result


def _reject_nonfinite(_value: str):
    raise UpdateError("Non-finite update metadata is invalid.")


def parse_signed_manifest(raw: bytes, public_key_b64: str,
                          download_host: str) -> VerifiedRelease:
    """Verify signature and exact format before trusting ANY release field."""
    if not isinstance(raw, bytes) or len(raw) > MANIFEST_BYTES_LIMIT:
        raise UpdateError("Update metadata is missing or too large.")
    try:
        doc = json.loads(raw.decode("utf-8"),
                         object_pairs_hook=_reject_duplicate_keys,
                         parse_constant=_reject_nonfinite)
        if not isinstance(doc, dict) or set(doc) != {"payload", "signature"}:
            raise UpdateError("Update metadata envelope is invalid.")
        payload, signature = doc["payload"], doc["signature"]
        if not isinstance(payload, dict) or set(payload) != {
            "schema", "app", "channel", "version", "download_url",
            "installer_sha256", "size_bytes"
        } or (type(payload["schema"]) is not int or payload["schema"] != 1 or
              payload["app"] != APP_ID or payload["channel"] != "stable"):
            raise UpdateError("Update metadata is not a stable Game Grave release.")
        _version(payload["version"])
        url = _https_url(payload["download_url"], host=download_host)
        if (not url.lower().endswith(".exe") or
                not isinstance(payload["installer_sha256"], str) or
                not _DIGEST.fullmatch(payload["installer_sha256"]) or
                type(payload["size_bytes"]) is not int or
                not 0 < payload["size_bytes"] <= MAX_INSTALLER_BYTES):
            raise UpdateError("Update installer identity is invalid.")
        if not isinstance(signature, str):
            raise UpdateError("Update signature is missing.")
        key = base64.b64decode(public_key_b64, validate=True)
        sig = base64.b64decode(signature, validate=True)
        if len(key) != 32 or len(sig) != 64:
            raise UpdateError("Update verification key or signature is invalid.")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(key).verify(
            sig, json.dumps(payload, ensure_ascii=True, sort_keys=True,
                            separators=(",", ":")).encode("utf-8"))
        return VerifiedRelease(
            payload["version"], url, payload["installer_sha256"],
            payload["size_bytes"], payload["channel"])
    except UpdateError:
        raise
    except (UnicodeError, ValueError, TypeError, KeyError, binascii.Error,
            json.JSONDecodeError, InvalidSignature) as exc:
        raise UpdateError("Update metadata could not be verified.") from exc
    except ImportError as exc:
        raise UpdateError("This build is missing the signature verifier.") from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_for_updates(*, manifest_url: str = UPDATE_MANIFEST_URL,
                      public_key_b64: str = UPDATE_ED25519_PUBLIC_KEY_BASE64,
                      download_host: str = UPDATE_DOWNLOAD_HOST,
                      installed_version: str = UPDATE_INSTALLED_RELEASE_VERSION,
                      opener=None) -> UpdateResult:
    """Run only after user clicks Check. No installer download or execute."""
    if not update_ready(manifest_url, public_key_b64, download_host,
                        installed_version):
        raise UpdateError(
            "Update checks are not connected in this unsigned preview. "
            "No network request was made.")
    _https_url(manifest_url)
    request = urllib.request.Request(
        manifest_url, headers={"Accept": "application/json",
                               "User-Agent": "GameGrave-UpdateCheck/1"},
        method="GET")
    try:
        open_request = opener or urllib.request.build_opener(_NoRedirect()).open
        with open_request(request, timeout=8) as response:
            # Even injected transports must not silently switch to a new URL.
            resolved_url = response.geturl() if hasattr(response, "geturl") else manifest_url
            if resolved_url != manifest_url:
                raise UpdateError("Update metadata was redirected unexpectedly.")
            raw = response.read(MANIFEST_BYTES_LIMIT + 1)
    except UpdateError:
        raise
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpdateError(
            "Could not check for updates. Your current Game Grave stays usable offline."
        ) from exc
    release = parse_signed_manifest(raw, public_key_b64, download_host)
    status = "available" if _version(release.version) > _version(installed_version) else "current"
    return UpdateResult(status, installed_version, release)
