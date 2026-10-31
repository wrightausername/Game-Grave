# Game Grave 1.0 stable: release acceptance plan

**Status:** Engineering preview. This plan is the only version-1.0 release gate, not the old internal v2.x source labels. Reaching a milestone requires evidence and human sign-off for real Windows operations. Green Linux/Windows CI **alone** does not qualify as a commercial release.

| Order | Target | Track | Work to complete | Acceptance |
|---|---|---|---|---|
| M1 | 0.6.0-alpha | [#10](https://github.com/wrightausername/Game-Grave/issues/10) | Core deletion and restore safety, real Recycle Bin and recovery tests, critical path handling | Zero unsafe deletion paths, actual Undo Center verification on Windows 10/11 |
| M2 | 0.7.0-alpha | [#11](https://github.com/wrightausername/Game-Grave/issues/11) | Mod Radar / Game DNA evidence, Steam/Epic/GOG, MO2/Vortex cross-checks, conservative orphan classifications | No unverified or active mod data marked safe to remove; real-game fixtures |
| M3 | 0.8.0-alpha | [#12](https://github.com/wrightausername/Game-Grave/issues/12) | Verified multi-root Resurrection Kits, rehearsal, Living Kits, Time Machine, PC migration, real MO2 QA | Game setup recovers from tested fixtures without live overwrite or false completeness claims |
| M4 | 0.9.0-beta | [#13](https://github.com/wrightausername/Game-Grave/issues/13) | Simplicity, accessibility, keyboard navigation, DPI, performance, polish | New-user tasks and accessibility/large-library acceptance |
| M5 | 0.9.5 | [#14](https://github.com/wrightausername/Game-Grave/issues/14) | Signed Windows installer, upgrade/uninstall, verified updates, privacy, live lifetime-Pro infrastructure | Clean install/upgrade on Windows, paid flow verified if selling Pro |
| M6 | 1.0.0-rc | [#15](https://github.com/wrightausername/Game-Grave/issues/15) | Closed beta, bug fixes, regression, complete release candidate | Human sign-off, zero open critical/P1 release blockers |
| M7 | 1.0.0 | [#16](https://github.com/wrightausername/Game-Grave/issues/16) | Signed, documented, tested GA package and support plan | All prior gates passed with linked evidence, release artifact identical to candidate |

## Engineering status as of 2026-10-30

- **Existing but not release-accepted:** Graveyard, Never Touch, Undo Center, Game DNA, Mod Radar read-only discovery, Save Vault, Resurrection Lab, Free/lifetime-Pro verification foundation, Windows executable CI. None by itself proves actual Windows user safety.
- **M1 actively underway:** merged protections for junction/reparse ancestors, hardlinks and manager storage under Downloads, atomic no-overwrite kit publication, and per-operation disposable Recycle Bin canary with byte-identical restore prerequisite. All existing automated unit tests pass. **The previous CI failure is fixed:** exact `System.FileName` and canonical `undelete` restored a disposable file byte-for-byte in [Windows CI](https://github.com/wrightausername/Game-Grave/actions/runs/41131958400). A broader disposable protection/restore/collision [QA run](https://github.com/wrightausername/Game-Grave/actions/runs/41132234295) also passed and produced a path-free report. M1 is **still open** pending real installed-app, interactive Windows 10/11 user, locale and conflict testing. See [issue #10](https://github.com/wrightausername/Game-Grave/issues/10).
- **M2 and M3 partially implemented:** evidence-first discovery and backup/recovery foundation exist, but real launcher and mod-manager recovery QA has not happened.
- **M4 partial:** themes, scales, views and dialogs exist, but keyboard/screen-reader usability and performance acceptance remain open.
- **M5 partial:** installer definition and [unsigned Inno Setup candidate build with SHA-256](https://github.com/wrightausername/Game-Grave/actions/runs/41129498352) succeeded. Production Authenticode signing, payment/key issuance, secure update channel, privacy/legal sign-off and clean VM QA remain open.
- **M6 and M7 not started:** no human closed beta or certified stable build has occurred. The identical beta-test questionnaire and disposable-data task script are now prepared in [BETA_TEST_PROTOCOL.md](BETA_TEST_PROTOCOL.md); actual enrollment begins only after M1–M5 acceptance, and the questionnaire wording must be frozen for comparability.

## Non-negotiable decisions

1. Free forever plus **one-time lifetime Pro**, not a subscription.
2. No forced account, default telemetry or background full-disk polling.
3. Permanent deletion requires separate explicit confirmation if such a feature is ever introduced. Existing cleanup uses Recycle Bin only; never fallback to irreversible deletion.
4. Undo Center and understandable logs remain in Free. Recycle Bin moves are not immediate disk-space savings.
5. No in-place restore or replacement of existing game, mod or save files without separately verified conflict handling and explicit user approval.
6. Unsupported launchers/managers and unknown mod relationships remain clearly *unknown*, not assumed safe or restorable.
7. No release tag `v1.0.0` or claim of GA until every gate has evidence and a real person has signed off. A green build is not the same as acceptance.

## Operational workflow

Each milestone uses its linked GitHub issue for concrete subtasks, PRs, CI results, Windows QA run records and manual evidence. `release_gate_status.json` starts blocked; `tools/release_audit.py` checks it and the release-tag workflow refuses a 1.0 candidate while any gate remains open. This file is a tracker, not a substitute for independently validating the evidence.

**Current engineering work:** M1 and M2 have received substantial safety/detection hardening but still need representative Windows human QA. M3 continues with exact-sha recovery, conservative path checks and fault injection. M6 beta is planned, not started, and M7 stays blocked. Do not count overlapping engineering progress as completed acceptance gates.


## Engineering progress on 2026-10-31 (NOT milestone acceptance)

All linked code below is integrated through reviewed GitHub pull requests and
automated disposable tests. **Zero M1–M7 human release gates have been marked
passed.** Never confuse a green Windows Server GitHub runner with interactive
consumer Windows 10/11 sign-off. The authoritative block is
[`release_gate_status.json`](release_gate_status.json) and
`python tools/release_audit.py --strict`.

| Track | Engineering built and automatically checked | Still needs real-world evidence / external approval |
|---|---|---|
| **M1** | Background Graveyard/Old Files cleanup ([#47](https://github.com/wrightausername/Game-Grave/pull/47), [#48](https://github.com/wrightausername/Game-Grave/pull/48)), opt-in byte-exact Undo self-test ([#54](https://github.com/wrightausername/Game-Grave/pull/54)), scan-time file identity and approved folder/age confinement ([#58](https://github.com/wrightausername/Game-Grave/pull/58)) | Installed Windows 10 and 11, localized Recycle Bin, UAC, deleted-path conflict, independent user data and recovery safety |
| **M2** | Opt-in exact duplicate archive hashing without delete rights ([#49](https://github.com/wrightausername/Game-Grave/pull/49)); Ghost Watch omissions, linked/hidden/deep files now count as incomplete ([#59](https://github.com/wrightausername/Game-Grave/pull/59)) | Compare actual Steam/Epic/GOG, Vortex and MO2 UI inventories; moved libraries, shared mods, hardlinks, ownership disagreements |
| **M3** | Seven-part native Windows disposable multi-root kit, rehearsal, immutable version, Time Machine, transfer and tamper CI ([#50](https://github.com/wrightausername/Game-Grave/pull/50)) | Real clean MO2 instance reconnect and manual multi-PC game setup restoration with separate backups |
| **M4** | Windows Tk controls, Graveyard Protect/Unprotect, canceled Delete, visual panel and 100–200% scaled UI exercised in CI ([#51](https://github.com/wrightausername/Game-Grave/pull/51)); Steam manifest/account scan accepts in-flight Cancel ([#60](https://github.com/wrightausername/Game-Grave/pull/60)) | Physical monitors and Narrator/screen-reader; keyboard-only and nontechnical user walkthrough; large real library latency |
| **M5** | Signed release verifier and strict provenance ([#53](https://github.com/wrightausername/Game-Grave/pull/53)); safe legacy settings migration ([#55](https://github.com/wrightausername/Game-Grave/pull/55)); actual unsigned EXE launch, install/reinstall/uninstall CI ([#56](https://github.com/wrightausername/Game-Grave/pull/56)); opt-in signed-size-and-SHA installer download, never auto-run ([#62](https://github.com/wrightausername/Game-Grave/pull/62)) | Owner-supplied production Authenticode credentials, signed endpoint, payment/legitimate lifetime Pro service, legal/privacy review, consumer Windows installer and cross-version upgrade |
| **M6** | Frozen Q01–Q12 and T01–T12 privacy-safe beta response analysis prepared ([#52](https://github.com/wrightausername/Game-Grave/pull/52)) | Real independent tester cohort and fixed survey, bug triage, thresholds, signed regression acceptance. No beta has started |
| **M7** | Plain-English user and release/rollback/support runbooks prepared ([#57](https://github.com/wrightausername/Game-Grave/pull/57)) | Signed immutable 1.0.0 artifact, customer support infrastructure, owner authorization and GA publication |
| **Field QA** | One-command optional privacy-safe local Windows evidence tool ([#61](https://github.com/wrightausername/Game-Grave/pull/61)), run as a non-authorizing disposable native Windows CI smoke ([#63](https://github.com/wrightausername/Game-Grave/pull/63)) | Execute on privately controlled consumer Windows PCs with explicit approval, compare with launcher/mod manager UIs and retain redacted evidence |

The owner-requested identical beta questionnaire is unchanged. There is no
automatic beta enrollment, paid Pro key issuer or authorized production
release. Deferring real-world acceptance is a safety requirement, not
permission for a green CI run to mark the product stable.
