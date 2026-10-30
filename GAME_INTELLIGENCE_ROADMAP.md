# Game Grave: gaming intelligence implementation status (October 30, 2026)

This document distinguishes **working foundations** from **full commercial-grade features**.
Game Grave remains local-first, Free + one-time lifetime Pro, with safety and Undo
Center available in Free. Nothing in this intelligence layer authorizes deletion.

## Implemented in this branch

| Vision | What actually works now | What is still missing |
|---|---|---|
| Game DNA | Read-only per-game association for folders contained in recorded installations and exact Steam Workshop app IDs. Unresolved saves/manager folders remain protected. Desktop Game DNA page. | Cross-manager dependency graphs, verified Vortex/MO2 profile ownership, collision handling across moved installs |
| Resurrection Kits | A user-selected save/profile directory is backed up using existing verified Save Vault ZIP, with portable integrity-check manifest; checksum verification is available in code. UI entry in Save Vault. | Full mod archives, load-order reconstruction, conflict checks, guided no-overwrite restoration |
| What Broke My Game? | Comparison of on-demand metadata observations, with actionable file-change review notes. | Verified known-good launch state, crash logs and cause correlation, backed-up config rollback |
| Regret Calculator | Make Room describes unknown/high recovery effort and never inflates verified free space. | Accurate recovery-time estimates, download bandwidth/storage planning, save availability and game usage weighting |
| Ghost Watch | Manual bounded snapshots of recognized mod-folder contents, simple change detection in Game DNA. | Optional incremental change journal reader and noise-filtered notifications (never default background polling) |
| Exodus | Read-only migration checklist for recorded launcher games and associated folders. | Guided archive transfer, checksums, launcher-supported relocation, destination validation |
| Patch Fallout | Review of changed potentially sensitive mod/configuration file extensions. | Trusted per-title/per-version compatibility rule database and mod dependency checks |
| Community Intelligence | Local anonymized category-level rule draft API, no raw paths, no upload. | Explicit opt-in contribution UI, validation service, moderation, review process, signed rule updates |

## Safety and accuracy constraints

1. **No deletion or modification of games and mods by these features.**
2. Known folder associations are **not** proof of activity, abandonment, or safe cleanup.
3. Change snapshots record metadata only, on demand, with caps of 40 roots, 4,000 file entries, and three directory levels. Missing observations under changed roots or scan caps are NOT proof that a file was deleted.
4. Steam Workshop matching is exact app ID association only; subscription state may differ.
5. Recovery Kits preserve **one selected folder**, not an entire game or modlist; users must close running games. A ZIP passing CRC does not establish game-save consistency.
6. A Recycle Bin operation is not equivalent to freeing disk space. Cleanup always follows the preexisting approval and protection mechanisms.
7. Community rule drafts stay **on device** and cannot become automatic deletion rules.

## Production follow-up stages and acceptance criteria

### Phase A: Reliability and relationships
- Native Windows 10/11 CI + human testing on junctions, hardlinks, long paths, locked files and custom game libraries.
- Correct known Windows path semantics; detect mapped/profile locations from actual metadata, never directory-name guesses.
- Finish launcher coverage and read-only addon/profiles dependency rules; automated fixture tests.
- Existing Undo Center / Recycle Bin safety must pass live-Windows regression tests.

### Phase B: Diagnoses and protection
- Per-game opt-in observations with checksummed manifests and incremental updates instead of bounded generic mod folder snapshots.
- "Known-good" only when user confirms a game launched successfully; never automatically infer success.
- Back up configurations before any explicit user-approved rollback; no unsafe overwrites.
- Cross-check exact game/mod versions before claiming a patch incompatibility.

### Phase C: Portable Resurrection / Exodus
- Verified bounded multi-root backups with explicit inclusion/exclusion and source identity.
- Restore planner with destination dry run, conflict review, capacity checks, and no-overwrite default.
- Launcher-specific install/reinstall instructions and tested checksum verification.
- Save and mod profile protection remains free; advanced transfer orchestration may be lifetime Pro.

### Phase D: Community intelligence
- Anonymous opt-in rule suggestions with local privacy preview, signed update channel, review/moderation queue.
- Manual whitelist, test corpus and staged rollout for every rule.
- No raw file paths, filenames, save contents, account identifiers, or telemetry by default.

## Test and UI status

The initial implementation includes `tests/test_game_intelligence.py`.
GitHub Actions runs Python unit tests on Ubuntu and Windows. Real Windows installed
application, ZIP restore, patch compatibility, and long-running scans remain
unverified until separately tested.

The visible Game DNA page is a functional **preview**, not a declaration that
all eight production features are complete.
