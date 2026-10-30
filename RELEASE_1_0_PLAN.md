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
- **M1 actively underway:** reject junction/reparse ancestors and hardlinks in the recycler; use atomic no-overwrite kit publication. Regression tests are necessary but real Windows integration QA remains.
- **M2 and M3 partially implemented:** evidence-first discovery and backup/recovery foundation exist, but real launcher and mod-manager recovery QA has not happened.
- **M4 partial:** themes, scales, views and dialogs exist, but keyboard/screen-reader usability and performance acceptance remain open.
- **M5 partial:** installer definition and unsigned build process exist. Production Authenticode signing, payment/key issuance, secure update channel, privacy/legal sign-off and clean VM QA remain open.
- **M6 and M7 not started:** no human closed beta or certified stable build has occurred.

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

**Immediately next:** complete M1, not another speculative feature rollout. Tests should be run against disposable files first, then manually against real Windows 10 and 11 QA machines before progressing.
