# Game Grave feature status | engineering preview, not stable 1.0

**Current release decision (October 30, 2026):** NOT READY. The historical v1.9/v2.4 sections below describe internal engineering increments, not public release acceptance. Game DNA, Resurrection Lab, Save Vault, Graveyard and Windows unsigned builds exist; M1-M7 gate evidence is tracked in [RELEASE_1_0_PLAN.md](RELEASE_1_0_PLAN.md). Windows Shell Recycle Bin/Undo QA in noninteractive CI failed; a disposable, byte-verified recovery canary now refuses user-file recycling if Undo cannot be proven. Do not claim that the native Windows recovery scenario has passed. The GitHub Windows installer artifact is unsigned and Pro billing remains unavailable.

This file prevents product ideas from being mistaken for tested capabilities.

## New in v1.9

- **File Detective:** read-only relationship explanations tied to installed Steam/Epic/GOG roots, user-added library roots, known mod-storage roots and Steam Workshop app IDs. Evidence strengths are shown. No confident orphan/deletion claims and no mod-manager dependency parsing.
- **Modlist Guardian foundation:** the File Detective action explicitly explains why recognized mod-manager folders and active game locations are protected; full dependency validation still pending.
- **Make Room v2:** choose GB goal and target drive; display actual OS-reported free capacity plus a 10 GB reserve; review a short prioritized list of unchanged eligible game/mod archive files from the scanned folder and old Steam games. Suggestion sizing is *apparent* and never labeled verified reclaimable space. No automatic removal.
- **Simplicity rule:** default interface favors plain-English explanations and short, guided actions; advanced options stay optional.

## Implemented in this build

- Shareable presentation presets (v1.8): save/apply/delete up to 30 named UI setups locally and export/import portable versioned JSON. Only appearance, layout and sorting/generic Graveyard filters are transferable. Private paths, search terms, scan results, protection settings and deletion/automation permissions are excluded by schema. Import size and values are strictly checked. No cloud account.
- Arbitrary custom accent colors (v1.8): native system color picker, manual #RRGGBB input, persisted custom colors and automatic contrasting text on accent buttons. Existing light/dark/system themes and scales remain available.


- Rebranded to Game Grave (GG) with legacy DustOff settings fallback.
- Customizable views (v1.7): persisted sorting for Steam Games, Mods, and Old Files, plus multi-filter Graveyard views by age, category, status, size and text with sort direction, clickable column headers and up to 30 named saved presets. Bulk-action scope is **visible eligible rows only**; filtering never changes safety eligibility.
- New The Graveyard review tab: old Steam games with known last-play timestamps, old mod storage folders (review only), and old identifiable standalone mod/game archives (user confirmation required before recycling). Includes details and single/selected/all-eligible recycle paths.
- Additional known-folder read-only MMO and mod sources including ESO/Minion, War Thunder, RedM, RuneLite, Guild Wars 2, LOTRO, SWTOR and Path of Exile; installer-path probes for War Thunder game custom content.
- `POST_MVP_PERSONALITY.md`: requested Easter eggs and gamer humor explicitly deferred.


- V1.4 Steam/Vortex/MO2/Workshop inventory, selected old-file Recycle Bin cleanup, schedule opt-in, logs.
- New game/mod ecosystem read-only detection by known paths: Thunderstore, r2modman, Prism, Modrinth, CurseForge, Baldur's Gate 3, The Sims 4, Wabbajack and FiveM.
- Steam shader cache and in-progress download storage recognition. Not deletion.
- Epic Games local install manifests and GOG Windows registry entries, plus user-added game library scanning.
- Separate history of observed disk-free and category changes across manual scans.
- Make Room review planner with explicit target, zero claimed verified space, no automatic actions.
- Folder explanation tool, built-in/user Never Touch protection, visible protected old files.
- In-app Undo Center records recycle operations and attempts Windows Shell restore for uniquely matched items.
- User-selected local save/profile ZIP backup with CRC integrity verification.
- Themes (light/dark/system), accent colors, compact/normal/large scaling, basic/advanced navigation and settings tabs.
- Cancel scan; default no scan at launch.

## Partially implemented / needs Windows QA

- Undo Center: Windows Shell COM matching and restore. Untested on real Windows versions and locales. Missing items are flagged, not silently claimed restored.
- Epic/GOG inventory: depends on launcher metadata. Can miss other launcher installation formats and user-customized locations.
- Mod coverage: not comprehensive; known path probes do not verify active profiles, dependencies or exact ownership.
- Storage history: sampled only when user scans, not a complete causal filesystem timeline.
- Scheduled Downloads recycling: carries v1.4 limitations; must undergo security and user-consent reviews before a commercial release.

## Not implemented (research/workshop backlog)

### Next production priorities
0. Complete Abandoned Addon Detection relationship engine: verify game installs, mod-manager profiles, orphan evidence, duplicates and preservation of configs. Current path signatures and timestamps cannot prove abandonment or safe deletion.

1. **Extend** Game Relationship Engine (v1.9 covers only confirmed folder/manager/Workshop relationships) correlating ownership across every supported launcher, mod manager, profile and drive with evidence and confidence scoring.
2. Comprehensive support for EA App, Battle.net, Ubisoft Connect, Rockstar, Xbox/Microsoft Store game metadata, portable managers and moved game libraries.
3. Validated Vortex/MO2/Thunderstore deployment and profile dependency inspection, so the app can distinguish active, disabled, shared and unknown data without breaking modlists.
4. Verified unique-on-disk and reclaimable-size accounting across hard links, sparse files, compression and cross-volume paths.
5. Safer cleanup planning with item-level dry run, non-overlapping calculation, drive-aware plans, consistency checks, and user-approved restore points.
6. Robust Windows OS Recycle Bin restore, conflicts, localization, permission handling and testing on real Windows 10/11 PCs.
7. Broader built-in save detection, tested automated backups and guided restore without overwrite, cloud-save status checks.
8. Accessibility testing with real users, keyboard-only and screen-reader QA; responsive scrollable UI at all DPI sizes.

### Future / experimental
- Incremental filesystem snapshot/USN change journal reader; optional low-resource local file-growth alerts.
- Uninstall Watchdog, old patch/update leftover forensic detection and supported launcher repair/uninstall helpers.
- Exact duplicate installer/archive/recording detection using file hashes with shared-storage awareness.
- Gaming recording gallery, modpack-space analysis, old-version suggestions.
- Game hibernation and verified restoration, migrations between drives or PCs.
- Repair workflows with rollback, Steam Workshop subscription management where available.
- Local natural-language Ask Game Grave feature grounded in actual scan evidence.
- Game-specific signatures expanding beyond the existing generic mod markers.
- Release packaging, signed installer, recovery QA, licensing/payment, privacy documentation.

## Product principles that cannot be sacrificed

- Free forever + one-time lifetime Pro, never subscriptions.
- No forced account, no telemetry by default, offline-first functionality.
- Most core scan and safety features including Undo Center in Free.
- Permanent deletion always requires separate explicit confirmation (not offered by this build).
- No deceptive 'safe' badges for uncertain files or invented free-space estimates.
- Default simple navigation. Advanced controls opt-in and user-customizable.
- No 24/7 polling for every major game update.

### Deferred personality work
- Finish and validate the core product first, then implement optional quirky gamer copy and accessible Easter eggs as specified in `POST_MVP_PERSONALITY.md`.


## v2.0: Windows installation and Free / Pro foundation

**Implemented in source:** Inno Setup 6 script with per-user install/uninstall, Windows build script, GitHub Actions Windows installer CI workflow, Free/Pro settings page, signed lifetime Pro receipt verification, explicit HTTPS activation client, and tests. Free works without account/license and no features are artificially gated.

**Not implemented:** A compiled setup executable from this Linux environment, live license issuing server, checkout, purchase processing, API endpoint, production public signing key, feature gating for real Pro exclusives, Windows Authenticode signing, installer QA on actual Windows. A Pro key cannot currently be bought or activated and preview UI says so.


## v2.4 testing update: focus on safety and clarity

- **Clear shader cache…** is available on the **Steam Games** page for an installed game.
  - Detects only Steam's `steamapps/shadercache/<appID>` belonging to the selected installed Steam game, cross-checked against its manifest.
  - Shows count and apparent byte size, warns about recompilation/stutter/redownloads, and requires explicit user confirmation.
  - Recycles verified *individual files*, not save/mod folders or the shared NVIDIA/AMD/Windows driver caches. Re-scan and Recycle Bin emptying are separate.
  - Rejects unexpected symbolic links, reparse points, hardlinked files, missing manifests, and files changed since inspection. A locked/in-use file is skipped and logged.
- **The Graveyard** now has visible checkboxes for bulk selection and an extra approval path if users explicitly want to override their own Never Touch protection on an individual ordinary mod archive. Installed games, managed mods, saves and system folders remain blocked; other unsafe folders are *never* bulk-overridden.
- **Cleanup History (Advanced → Activity)** groups sessions into expandable rows with individual results and paths. Shader and Graveyard cleanup record start, per-file results, and finish.
- The desktop still defaults to simple mode. No automatic shader-cache cleaning or automatic protection overrides.
- **Limitations:** Windows Recycle Bin behavior, actual freed space, live installer operation and game/driver lock handling still need real Windows testing. The Windows installer preview is unsigned and installs a separate Python runtime if unavailable.
