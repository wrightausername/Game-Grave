# M5 Windows installer, updates and licensing acceptance matrix

**Status: OPEN. Do not publish this as Game Grave 1.0 or sell Lifetime Pro.** This checklist is for a signed release candidate on test PCs, not a substitute for production code signing. Use disposable user profiles and a backup of any information you care about.

| ID | Safe test | Release requirement |
|---|---|---|
| M5-01 | Unsigned engineering candidate on an ephemeral Windows CI runner | Build digest, exact source-commit manifest, installed EXE identical to built EXE, repeat install and uninstall pass |
| M5-02 | Clean Windows 10 standard-account VM | Install and launch without unexpected elevation, account creation or forced network connection |
| M5-03 | Clean Windows 11 standard-account VM | Install, shortcuts, Add/Remove Programs, uninstall success |
| M5-04 | Existing older app build on a dedicated VM | **Real cross-version upgrade** preserves user data, config and prior Undo Center recovery information |
| M5-05 | Uninstall with disposable Save Vault copies and mock game install | Installer removes only app-installed files; Never Touch, saves, mod folders and local backups remain intact |
| M5-06 | Test user with custom installation directory and another Windows profile | No access outside owned install directory, no cross-user settings or uninstaller surprises |
| M5-07 | Windows antivirus and SmartScreen with valid release signing credentials | App and setup have proper Authenticode signatures; timestamp and source identity independently verified |
| M5-08 | Download exact signed candidate and compare published SHA-256 | Exact signed installer and embedded executable correspond to reviewed build; no mutable latest-EXE replacement |
| M5-09 | Optional update discovery with internet unavailable, slow, or altered update metadata | Free stays usable offline, update is opt-in, downgrade/rollback policy documented, no untrusted executable auto-run |
| M5-10 | Fresh Free install without key/network or telemetry | Scan, Graveyard review, Undo Center, safety logs and existing functional features available without payment |
| M5-11 | Production **lifetime** Pro activation with test receipt from a real issuer | Verify HTTPS endpoint, Ed25519 signed entitlement, tampered receipt refusal, key recovery policy, offline license and refund/revoke rules |
| M5-12 | Attempt to buy or activate Pro with backend unavailable | No false promises, no subscription, no invented purchase success; Free remains intact |
| M5-13 | Update-check/checkout/licensing privacy disclosures and support | Plain-language opt-in data disclosure, retention, incident/abuse plan and support contact approved |
| M5-14 | Keyboard, high DPI (100–200%) and cancellation throughout installer and application workflows | All prompts reachable and understandables; no user data erased after canceled setup |

## Current automated engineering checks

When source changes to `build_installer.ps1`, `installer/GameGrave.iss`, `tools/windows_installer_ci_smoke.ps1` or the candidate workflow reach `main`, the `Windows installer candidate (unsigned; manual)` GitHub workflow tests an unsigned build. It verifies a SHA-256 manifest and a source-build JSON, then runs a CI-only isolated install, same-version repeat install and uninstall with bytes-hashed disposable user profile and unrelated game-save sentinels. The workflow does **not** modify live games, install on users' computers or publish a public release.

**Required real-world tests still open:** Windows 10/11 installed-app QA, real prior-version upgrade, per-machine vs per-user installer behavior, program signing/AV reputation, signed distribution, network/update security and production Lifetime Pro issuance/payment. Mark M5 complete only after reviewer sign-off and linked evidence in [M5 issue #14](https://github.com/wrightausername/Game-Grave/issues/14).

The future M6 beta uses the identical test script and questionnaire [BETA_TEST_PROTOCOL.md](BETA_TEST_PROTOCOL.md) once M1–M5 have passed.
