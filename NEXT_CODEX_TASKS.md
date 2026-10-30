# Game Grave v2.4 | Next Codex Implementation Tasks

**Engineering update, Oct 30, 2026:** PR #2 implements the Graveyard context menu and user Protect/Unprotect actions with unit tests; ESO/WoW descriptors and standard WoW paths have preliminary support. These changes require review, CI and native Windows QA. Remaining Priority 1 keyboard, scale and recycle testing stays open. See ENGINEERING_UPDATE_2026-10-30.md.

**Priority 1: Graveyard UX without weakening safety.** Add Protect/Unprotect and a right-click menu with Details, Open Folder, Protect/Unprotect, Delete. Hook deletion to existing revalidated Recycle Bin workflow only. Keep status explanations clear to average users. Add keyboard access and tests. Preserve all existing filters, checkboxes, selection and logs. **Do not** delete active games, managed mods, saves, worlds, configurations, or uncertain files.

**Priority 2: Abandoned Addon Detection and broad Mod Radar.** Build cross-launcher, mod-manager and game metadata correlations to identify active, likely orphaned, duplicate and uncertain game-related files. Include FiveM/RedM, ESO/Minion, War Thunder, WoW, FFXIV (policy-sensitive), GW2, LOTRO, RuneLite, SWTOR, Path of Exile, ARK, modpacks and loaders; protect active profiles and configuration files. Provide plain-English evidence and honest apparent-versus-reclaimable size numbers.

**Priority 3: Safety verification.** Real Windows 10/11 integration tests for Recycle Bin/Undo, junctions, permissions, file locks, hardlinks, user protections, signed install/uninstall paths. No silent deletions, no permanent-delete fallback, no false claims that moving files to Recycle Bin frees disk space.

**DEFER UNTIL POST-MVP:** Fun, quirky gaming voice and Easter eggs. See `POST_MVP_PERSONALITY.md`. Never interfere with warnings or cleanup decisions.

**Known state:** Game Grave v2.4 source passes 92 Python tests in Linux; not yet fully Windows-QA-validated. This document only adds the development handoff, not code implementation.
