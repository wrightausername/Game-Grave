# Game Grave (GG): Codex development handoff

This is the **actual evolved source tree** from DustOff v1.5, rebranded and extended through **Game Grave v2.4**.

## Run

- Windows: `Start_GameGrave.bat` (Python 3.10+, tkinter).
- Tests: `python -m unittest discover -s tests -v` (92 tests currently passing in the Linux Python test run).
- Optional unsigned Windows exe: `build_exe.bat` (PyInstaller).

## Implemented in this revision

- Rebrand in UI/documentation; load old DustOff settings when Game Grave settings do not exist.
- Dedicated **The Graveyard** tab built from real scan results, rather than mock data. Shows evidence, age signal, probable relationship, apparent size, protected/review status; age filter.
- Individual/selected/all-eligible recycle actions for *ordinary, narrowly identified standalone old archives only* with a confirmation dialog, re-checks at execution, Undo Center logging. **Not** for games, active addons, managed mod folders, or uncertain data.
- Added known-path scanning for ESO/Minion, War Thunder, RedM, LOTRO, SWTOR, Guild Wars 2, RuneLite, Path of Exile. All are read-only.
- New Graveyard safety regression tests; 39 tests overall.
- v1.7 adds independent saved sorting for games/mods/old files; Graveyard has multi-filter controls, column sorting, ascending/descending order, and named view presets. `view_options.py` owns pure view-only transformations; `tests/test_view_options.py` verifies them. Confirm in Windows UI that layout, state persistence, filter scopes, and selection behave correctly at multiple DPI levels.
- Desired gaming personality + Easter eggs documented for a future polish phase in `POST_MVP_PERSONALITY.md`.

## Priorities for future Codex implementation

1. Actual **Game Relationship Engine** across Steam/Epic/GOG/EA/Ubisoft/Battle.net/Xbox and mod manager profiles: precise evidence, active vs orphaned vs uncertain.
2. Per-ecosystem addon metadata and version parsing (ESO addon descriptors, WoW TOC, Workshop manifests, Vortex/MO2/Thunderstore/Minion, FiveM/RedM, etc.), strict read-only operations.
3. Duplicate mod/archive detection with streaming file hashes and verified disk-reclaim accounting; no deletion on weak signals.
4. Improve age information: launcher play history, manager metadata, file dates labeled clearly; never claim 'never used' solely from mtime.
5. Recycle Bin restore integration and 100% regression tests on real Windows 10/11 PCs, including directory junctions, permissions, multiple volumes, hardlinks, locked files.
6. UI performance for large results, keyboard navigation, accessibility, and an explicit always-protected Never Touch mode. Basic user-configured sorting now exists; benchmark/virtualize for large lists.
7. Only after core/QA: optional retro gaming Easter eggs, accessible joke messages, no effects in safety dialogs.

## Product constraints

Free + one-time lifetime Pro, no subscription. No default telemetry, no cloud requirement. Scanner cannot infer deletion safety from missing manifests or old timestamps. Scans are read-only; destructive actions always explicitly confirmed. No permanent delete fallback. Recycle Bin does not free disk space until emptied; Undo Center is best-effort. Protect active games, saves, worlds, mod profiles, settings, and uncertain data.

The source archive is not a Git repository, so Codex should import it into a **new Game Grave repo/workspace**, not the user's unrelated Comic Beatdowns repository. Do not claim Windows QA was completed on this Linux host.

## v1.8 changes: shareable UI presets and custom color selection

- `ui_presets.py`: allowlisted, versioned JSON-only export/import of appearance, navigation and list filters. No local paths, filesystem actions or delete/scan permissions ever exported or accepted.
- `ui.py`: Settings > Appearance offers `colorchooser.askcolor` and manual HEX; Settings > Shareable Presets offers named save/apply/delete/export/import with explicit preview/confirmation. 30-preset limit; 24 KB import limit. Accessible foreground selection for accents.
- `core.py`: new local settings `ui_custom_accent` and `ui_presets`, default backward compatible.
- Tests: `test_ui_presets.py` and `tests/smoke_ui_v18.py` for JSON schema/privacy, color, UI load/save/import/export.
- **Future work:** Windows 10/11 testing of native color dialog, contrast checks for arbitrary user-picked accents including low contrast vs background, RTL, keyboard-only navigation and import workflows. Do not implement the Easter-egg backlog until core product and deletion safety QA is complete.

## v1.9: simple, evidence-led cleanup planning

- `file_detective.py`: read-only File Detective. Explains why a file or mod folder appears related to an installed Steam/Epic/GOG game, identified mod-manager storage, Steam Workshop content, an unverified custom library, or only a filename match. All results are protected and never label files as safe to delete. Current matching is limited to scanned roots, not a comprehensive dependency graph.
- `ui.py`: In **Game Mods** choose **Why is this here?** to see a plain-English explanation and confidence/evidence. In **The Graveyard**, the same control explains a selected finding. A user can also inspect another folder without starting a dangerous cleanup operation.
- `space_planner.py`: **Make Room** uses the real drive free-space reading for the target drive, subtracts a user-entered GB goal plus 10 GB reserve, lists a few matching old game/mod archive candidates and Steam games with known old play dates. Individual archive results are checked against changed files, Never Touch protection and matching volume; hardlinked files are de-duplicated in the review list. **Zero verified reclaimable bytes** are advertised because no deletion is proven safe or guaranteed to free space. No automatic removal.
- UI simplified to three questions (how much, where, review), with short buttons and progressive disclosure rather than a dense control panel.
- Regression coverage in `tests/test_relationships.py` and `tests/smoke_ui_v19.py`; execute with `PYTHONPATH=. xvfb-run -a python tests/smoke_ui_v19.py` on Linux. Tests are not Windows QA.

**Next actual production work:** verify mod-manager profile references and dependency graphs; extend launcher coverage; check physical disk allocation/hardlinks and realistic free-space recovery; protect working saves; improve Windows UI scrolling and accessibility; test real Windows Recycle Bin recovery before selling or releasing. Do not call File Detective a perfect ownership detector or the planner a guaranteed one-click cleanup.


## v2.0 installer and license architecture

- Build from Windows with `build_installer.ps1`, which runs tests then PyInstaller and Inno Setup 6; expected release installer `release\GameGrave_Setup_v2.0.0.exe`. No compiled Windows `.exe` is included in the source ZIP. `.github/workflows/windows-installer.yml` is ready for a dedicated repo.
- `licensing.py` verifies a signed Ed25519 lifetime Pro receipt before enabling Pro entitlement. `license_config.py` intentionally leaves activation URL and *public* signing key unset. Do NOT commit private keys or vendor API secrets. Checkout, key issuer, refund/revocation and reactivation policies remain future work.
- Settings > Free / Pro now shows edition status. When unconfigured it truthfully explains that paid activation is unavailable, without collecting a key. Free remains functional and un-gated. An imported preset cannot confer Pro.
- Before any release claiming a working Pro tier, deploy and security-review a key-issuing backend, payment integration, verified receipt protocol, and specific paid feature gates; code-sign Windows installers and validate upgrades/uninstalls, activation recovery and offline behavior on real Windows machines.
- Run `python -m unittest discover -s tests` (77 tests) and `PYTHONPATH=. xvfb-run -a python tests/smoke_ui_v20.py` for Linux simulated UI.


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


## October 30, 2026: restored working context and next Codex tasks

**Baseline:** This package is Game Grave v2.4 source. The current source passes 92 Python unit tests in a Linux-hosted run. Real Windows QA and installer validation are still outstanding. The changes in this handoff are **requirements and documentation only**, not a new implementation release.

### Immediate next implementation: Graveyard usability improvements

1. Keep the app simple, readable, and approachable for nontechnical Windows gamers. Default to plain-language controls and hide advanced diagnostics unless requested.
2. In **The Graveyard**, add clear user-controlled **Protect / Unprotect** actions for user-selected eligible findings, without ever removing built-in protection for saves, worlds, active mod setups, system paths, or unknown content. User protections are persisted and explained.
3. Add a right-click context menu to Graveyard list items: **Details**, **Open Folder**, **Protect / Unprotect**, **Delete** (or "Move to Recycle Bin" when supported). Right-click should select the correct row; keyboard access should have an equivalent context-menu method. Disabled unsafe actions must explain why.
4. Context-menu Delete must call the exact same centralized, revalidated, user-confirmed safe cleanup method as the main button. Never introduce an alternate deletion path, permanent-delete fallback, or automatic delete. The right-click action is available only for narrowly verified standalone archives currently eligible for recycling; installed games, addon folders and uncertain items remain protected.
5. Preserve the existing Graveyard checkboxes and eligible selection / all-visible-eligible cleanup, saved filters, evidence descriptions, and Cleanup History. Follow the selected view rather than every unseen scan result. All cleanup remains explicitly confirmed.
6. Test selection correctness, filters, popup positioning, mouse/keyboard flows, path protection, stale file revalidation, and failed/partial Recycle Bin operations on Windows 10/11. Unit test the context-menu safety routing.

### Core game-aware detection and addon roadmap (highest product priority)

- Build the **Abandoned Addon Detection** relationship engine with corroborated evidence: (a) actively used by an installed game/profile, (b) probably orphaned from a removed game, (c) uncertain, or (d) duplicate installer/archive. Show source, size (apparent vs actual reclaimed), game/manager relationship, why flagged, and reversibility.
- Enumerate game/mod ecosystems without touching running game processes or anti-cheat: Steam/Workshop, Epic, GOG, Xbox/EA/Ubisoft/Battle.net/Rockstar; Vortex, MO2, Wabbajack, Nexus download archives; FiveM/RedM; CurseForge, Modrinth/Prism, Thunderstore/r2modman; BepInEx, MelonLoader, REFramework, UE4SS, tModLoader, OpenIV, ScriptHook V, and other game-specific loaders when safe.
- Explicit MMO/live-service coverage: Elder Scrolls Online + Minion (AddOns and SavedVariables); World of Warcraft; War Thunder user-created content; Guild Wars 2, Final Fantasy XIV, LOTRO, RuneLite, SWTOR, Path of Exile, ARK and similar relevant ecosystems. Respect each game's actual allowed mod rules. Treat protected/in-use content conservatively.
- Detect mod installers and archives scattered across Downloads and configurable directories, duplicate downloads, abandoned instances, old profiles, and stray files. File extensions, timestamps, or missing manifests alone **never** establish orphaned status or safe deletion. Profiles, saves, settings, scripts, worlds and live mods are protected by default.
- Maintain offline-first read-only discovery and explicit, reversible-where-available cleanup with logs, Never Touch rules, and Undo Center in **Free**. Do not conflate moving items to Recycle Bin with physical space reclaimed.

### Deferred phase: quirky gaming personality and Easter eggs

Approved by the product owner, but **do not implement until core detection, safety workflow, Windows QA, and UI simplicity have reached acceptance**. The definitive feature note is `POST_MVP_PERSONALITY.md`.
- Witty gamer-friendly microcopy, retro easter eggs, optional hidden achievements and modest cosmetic animation.
- Never joke inside data-loss warnings, consent screens, evidence, errors or recovery UI. No fake results, fake deletions, unrequested audio, or disruptive motion.

### Repo/Codex status

The user's connected GitHub currently exposes `wrightausername/Comic-Beatdowns` only. That is a separate project and **must not** receive Game Grave files. A dedicated Game Grave repository or a local Codex workspace created from this source archive is required before these tasks can be committed. Do not claim this handoff has been pushed to GitHub or run by Codex.
