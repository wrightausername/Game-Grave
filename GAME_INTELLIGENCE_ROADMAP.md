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

## MO2 / Vortex relationship iteration (October 30, 2026)

- **Mod Organizer 2:** read-only per-profile `modlist.txt` parser, including enabled, disabled and unmanaged markers. Discovers portable and moved profile folders through the existing scanned `ModOrganizer.ini` paths, and only ties a profile to an installed game when `gamePath` matches its recorded installation root exactly. Entries not found in the configured mods folder are *unverified*, not abandoned.
- **Vortex:** read-only parsing of optional `manual.json`, `startup.json` or `hourly.json` snapshots under `Vortex/temp/state_backups_full`. Inspects profile names and recorded mod states with stale-backup warnings; never opens Vortex's live `State.v2` LevelDB or changes deployment data. Game ownership requires an exact discovered-install-path match, never an approximate game ID or name.
- **UI:** Game DNA includes an explicit **Inspect manager profiles** action, profile summaries, and per-profile recorded status details. Profile inspection is user-triggered and does not start background monitoring.
- **Still missing:** complete native Vortex active state queries, conflict analysis, MO2 plugin dependencies and actual deployment verification. A disabled mod may still be required for another profile. Real Windows 10/11 manager fixtures and junctions need manual QA.

## Resurrection Kit 2.0 (October 30, 2026)

The new flow in **Save Vault** is user-controlled: select one discovered save
location, optionally choose a separate mod/profile folder, then choose where
to store the ZIP. The program writes the ZIP plus a versioned \`*.ggkit.json\`
checksum manifest. Both files must stay together. A kit includes **only selected
folders**, not the game itself or any unselected dependencies.

**Preview / Restore Kit** verifies SHA-256 and ZIP checksums before asking the
user to approve recovery. The user chooses a parent folder and the app creates
a **new, non-overwriting** \`Game_Restored\` directory. Existing game saves,
mod-manager staging and installed games are NEVER replaced automatically. V1
save-folder kits remain readable via the new restore engine. ZIP path traversal,
symlinks, reserved names, case collisions and entry-count/size limits are checked.

**Not yet implemented:** automatically locating every save/mod file; relinking
Vortex/MO2 deployments; safely installing files directly into active games;
one-click complete game recreation; automatic cloud backup; source file
consistency while games are running. Users must close games/mod managers before
backing up and reconnect recovered files manually. Native Windows tests with
real managers and unusual paths remain a release requirement.

## Resurrection Kit 2.1: automatic source discovery + MO2 profile reconnection

**Implemented in this iteration:** After **Scan PC**, open **Game DNA** or **Save Vault** and use **Find my setup automatically**. Pick a recorded installed game, then review read-only evidence suggestions. Sources come from an exact MO2 game-install/instance/profile association, exact Vortex snapshot-to-game association for staged mods, or a save scanner's matching game label. Nothing is included without confirmation. One folder per category is currently supported. Wrong-game, missing-data and mixed-manager findings are not promoted to safe guesses.

For kits created through a verified MO2 discovery, **Reconnect verified MO2 kit** checks the current MO2 instance INI and installed game, validates every ZIP entry and checksum, checks storage capacity and destination conflicts, and requires explicit approval of the exact plan. On success, it creates **missing mod folders only** and a **new `<Profile>_GameGrave` profile** in the recognized instance. It never overwrites existing mods/profiles, touches the game installation, edits the live MO2 configuration, or deletes files. The user selects the new profile inside MO2. This is intended for clean manager installs, not in-place merging into existing modlists. If conflicts or missing enabled mod folders occur, it fails closed; use **Preview / Restore Kit** into a separate recovery folder instead.

Vortex remains **snapshot-informed discovery and portable-kit capture only**. Rebuilding its active profile and deployment automatically requires a supported Vortex API/extension: do not modify `State.v2` directly. If a kit also includes game saves/config files, the MO2 reconnection step leaves those in the verified ZIP rather than guessing live save locations. Restore those through the existing safe staged-recovery workflow. No unsupported claims about seamless one-click complete game restoration.

**Windows release gates:** Real MO2 instances (including moved paths), hardlinks/junctions, antivirus/file locks, Unicode paths, profile switching and game launches after restore. Automated tests are fixtures and are not proof of real-world manager compatibility.

## Resurrection Lab: five working first versions (October 30, 2026)

A new **Resurrection Lab** page, reached from Save Vault or Game DNA, provides:

1. **Missing Pieces Detector / Readiness:** verifies a selected kit and checks whether enabled mods named in a preserved MO2 modlist actually have folders in the ZIP. Reports missing components, omitted saves/configs and unknown dependencies. No invented download URLs, compatible-version claims, or unjustified 100% recoverability scores.
2. **Resurrection Rehearsal:** optional, user-approved extraction into a unique temporary scratch directory, SHA-256 file-by-file comparison to archive contents, and cleanup of only the program-owned temporary directory. Does **not** run the game, test the installed manager or promise save consistency.
3. **Living Kits:** on-demand review of real changes between a complete v2 kit and user-reselected source folders. Creates a new independent, verified full ZIP only on approval. No background watching or incremental block-level deduplication yet. Manager auto-reattachment evidence is *not carried over* to the new kit until rescanned/reverified.
4. **Time Machine:** lists local adjacent kit manifests, compares two fully verified snapshots for added/changed/missing paths using ZIP CRC and size, and offers staged recovery of the older version into a fresh folder. No automatic in-place file rollback; CRC is a change heuristic, not a cryptographic identity proof.
5. **PC-to-PC Resurrection:** copies the verified archive + companion manifest into a new portable folder with a plain-language recovery guide; rechecks the copied kit. Install the game via the supported launcher on the target PC. Existing staged recovery and verified MO2 reconnect support the imported kit. No game executable or license transfers, Vortex live-profile restore, peer-to-peer streaming, or cloud services.

**Release gates:** Real Windows 10/11 installed-application QA, mod manager/game integration tests, large (>40K file) setups, file locks, junctions, Unicode paths, disk-full power-loss recoverability, AV interference and usability on laptop displays. These are real features with known limited scopes, not retail-ready exhaustive recovery promises.

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
