# Game Grave: Windows installer and lifetime license design (engineering preview)

## What is built and what isn't

- **Built now:** A Windows *build pipeline* that creates a normal `GameGrave_Setup_v<internal-version>.exe` installer using PyInstaller + Inno Setup. Installer provides a wizard, Start Menu / optional desktop shortcuts, installed-program entry, upgrade path and uninstaller. This Linux-produced source ZIP does **not** contain the finished Windows installer executable.
- **Built now:** Settings > **Free / Pro** screen. Free users do not register or enter a license key. A Pro activation client verifies server-issued Ed25519-signed, lifetime-only receipts and persists only the signed receipt locally.
- **Not built:** Payment checkout, key issuing/revocation service, live activation API, code-signing certificate, GUI recovery QA on Windows, Pro-only feature gating, self-updater. The activation endpoint and public signing key in `license_config.py` are deliberately unset. Clicking Activate Pro displays an accurate 'coming later' message. No key can unlock Pro until a real service is deployed.
- **Not for sale yet.** It would be deceptive to ship a Pro option without an issuer and paid features. The current build keeps all working features available to Free users.

## Build and test a professional Windows installer

1. On Windows 10/11 (64-bit), install Python 3.10+ and [Inno Setup 6](https://jrsoftware.org/isinfo.php).
2. Open PowerShell in the project directory and run `powershell -ExecutionPolicy Bypass -File .\build_installer.ps1`.
3. The script runs tests, bundles the Tkinter app and dependencies using PyInstaller, then invokes Inno Setup.
4. The deliverable is `release\GameGrave_Setup_v2.0.0.exe`. Run it on a *different* test PC / clean VM. Confirm Start Menu launch, optional desktop shortcut, Add/Remove Programs entry, uninstall, repeat-install upgrade and that user settings survive.
5. Alternatively, once this project is in its own GitHub repository, run the included **Build unsigned Windows installer** workflow. Download the produced installer artifact from that workflow.
6. For a real release, acquire and use a legitimate Windows Authenticode code-signing certificate. Sign both the bundled app exe and the installer; timestamp the signatures. Unsigned preview builds will commonly trigger Microsoft SmartScreen.

**Safe uninstall:** Files inside the installed program directory are removed. Local user preferences, scan history and any signed Pro receipt live under `%LOCALAPPDATA%\Game Grave` and are preserved by default. No installed games/mods/saves are touched by uninstall.

## Secure Free / Lifetime Pro plan

**Free:** No key, no account, no activation request and no mandatory internet. Core scanning, safety checks, Graveyard review, Undo Center and user customization remain accessible. Future Pro features must never lock basic file safety behind a paywall.

**Pro:** One-time lifetime purchase, no subscription. The eventual store/server creates a random human-readable license key. On explicit user request only, the app sends that key via HTTPS to the activation API. Server checks paid entitlement and per-license activation policy, and returns a JSON payload signed by a **private Ed25519 signing key that is NEVER shipped in the app**. The app validates the signature using a baked-in public key; it never trusts an unsigned `"pro": true` preference or a forged response. The signed entitlement remains usable offline. If the license server is down, the saved validated receipt continues to work. Server-side refund/revocation and reactivation policies still need product/legal decisions; permanent offline receipts cannot be instantly revoked.

Expected activation request:

```json
{"product":"gamegrave","license_key":"GG-EXAMPLE-KEY"}
```

Server response signature schema (the signature is calculated over `payload` serialized as sorted, compact, ASCII JSON):

```json
{
  "payload":{"app":"gamegrave","edition":"pro","license_id":"opaque-id","type":"lifetime","schema":1},
  "signature":"BASE64_SIGNATURE_FROM_PRIVATE_SIGNING_KEY"
}
```

No valid Pro receipt or signing secret is included. `license_config.py` must eventually contain the real HTTPS activation URL and **public** key. Keep checkout tokens, private signing keys, admin secrets and license databases server-side only. Never print raw purchase keys or include them in activity logs/analytics/crash reports. Privacy disclosures should explain the one-time key submission when Pro activation goes live.

**Future release work:** Implement the license service, key format, purchases/refunds and help recovery for lost keys; choose seat limits and offline-policy expectations; implement actual Pro entitlements; add purchase link; add Windows QA and signed installers; test malware/AV false positives, upgrades, and license portability. Maintain older signed-receipt compatibility during public-key rotation. Consider a recovery flow in case the user's computer fails.

## M5 Windows installer lifecycle CI (2026-10-30)

An unsigned installer candidate is not a signed or approved public release. The manual/CI build now emits three matching artifacts: a versioned setup EXE, its SHA-256 file, and a `.build.json` build-provenance report containing the exact source commit, installer hash and explicit `signed: false` / `release_approved: false`. Do not treat that JSON as a cryptographic attestation; it is metadata plus an independently checkable file hash.

The **Windows installer candidate** GitHub workflow additionally performs a CI-only, isolated local installer lifecycle test before uploading any artifact. It installs into a disposable directory, runs the same installer again, verifies the installed executable matches the PyInstaller output byte-for-byte, uninstalls, and checks that an unrelated synthetic game-save file and a synthetic `%LOCALAPPDATA%\Game Grave` preferences sentinel are byte-identical. The smoke script refuses to run outside GitHub Actions. If the unit tests have already created a Game Grave settings folder, the smoke script hashes those existing settings files before installation and verifies they survive byte-for-byte; it creates its own uniquely named sentinel using exclusive file creation without overwriting anything. Failures block artifact upload.

**This is NOT a full version-to-version upgrade test**, Authenticode signature, production entitlement backend, verified Windows 10/11 GUI experience, SmartScreen reputation or license/payment approval. Those remain M5 release blockers. Do not sell Pro or label these CI artifacts as a stable installer.

## Signed, opt-in update discovery foundation

`updates.py` and `update_config.py` provide an **inert-by-default** secure foundation for future stable releases. The only user-facing action is **Settings → More tools → Check for signed updates**. The engine refuses unsigned, forged, stale-channel, malformed, redirected or host-unapproved release metadata and compares strict semantic versions. Only an explicit click initiates a GET. A production release must supply a dedicated, authentic public Ed25519 verification key, pinned HTTPS metadata URL, approved HTTPS installer-download host and true signed installed release version. The repo intentionally does not contain those public-production settings or any private signing key.

The UI presently **never downloads, launches or installs an update**, regardless of what metadata says. Showing signed metadata and an expected file SHA-256 is not equivalent to verifying the downloaded Windows PE's Authenticode signature. This remains a mandatory independent test before enabling any secure update installer flow. There is no background polling, auto-update toggle, telemetry requirement or forced account. Free stays usable without internet.

### M5 Pro activation transport and local proof safety

The optional (not-yet-connected) Pro activation client now rejects URL credentials, insecure schemes, nonstandard HTTPS ports, query strings and fragments. A product license key is submitted **only** after the user explicitly activates, and redirects are refused so a paid key is not forwarded to a different endpoint. Server responses must carry a valid server-signed lifetime Ed25519 receipt; invalid responses never replace existing proof.

After signature verification, the client writes the receipt to an **unpredictable, exclusively-created temporary file** in the same settings directory and atomically replaces only Game Grave's activation receipt. A previous user's unrelated `.tmp` file is never overwritten, and failure to write leaves the previous signed receipt unchanged while cleaning up only our unique temporary output. These are synthetic security regression checks, not a deployment of Pro checkout, signing keys, or entitlement recovery. Free remains available offline without a key.
