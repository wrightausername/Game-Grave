"""Public configuration for opt-in Game Grave update discovery.

All fields deliberately unset while unsigned engineering previews are built.
Production setup requires a dedicated Ed25519 update-signing key, a reviewed
HTTPS metadata endpoint and an exact trusted download host. NEVER place the
private signing key, checkout credentials or signing secrets in this source.
"""
UPDATE_MANIFEST_URL = ""
UPDATE_ED25519_PUBLIC_KEY_BASE64 = ""
UPDATE_DOWNLOAD_HOST = ""
UPDATE_INSTALLED_RELEASE_VERSION = ""  # Set only in a signed 1.0+ installer.
