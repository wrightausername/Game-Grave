# Game Grave v2.4 | Gaming Storage Manager

**Status:** Engineering preview, **NOT Game Grave 1.0 stable and NOT ready to sell**. The unsigned Windows EXE and Inno Setup development installer build, Free/lifetime-Pro licensing foundation, and automated safety checks are available; production signing, real Windows installer/recovery QA, billing infrastructure and closed beta are not complete. See [the seven-milestone 1.0 release acceptance plan](RELEASE_1_0_PLAN.md).

**UI redesign approved:** The selected cinematic crimson-and-cyan concept is specified in the [Crimson Command UI Implementation Blueprint](UI_REDESIGN_BLUEPRINT.md). It defines the new all-launchers Games page, direct personal Never Touch unprotect controls in Graveyard, screen components, Qt/Tk migration and safety gates. This is an implementation plan, not a shipped UI.\n\nFor a simple walkthrough without developer jargon, use the [Game Grave user guide](USER_GUIDE.md). The [1.0 release operations, rollback and support checklist](RELEASE_OPERATIONS_1_0.md) documents the remaining independently approved publishing steps. Neither document means this engineering preview is ready for commercial distribution.

**Optional local AI Assistant (experimental):** Off by default in Settings, available in both classic and Crimson preview interfaces. Uses a separately installed local Ollama model; never uploads file contents or changes cleanup safety rules. [Installation, privacy limits, and test instructions](OPTIONAL_AI_ASSISTANT.md).

Game Grave finds games, mod-manager storage, Workshop folders, caches, and leftover installation candidates. It clearly separates *detected data*, *potential review targets*, and *space actually reclaimed*. Scanning never authorizes file deletion.


## Crimson Command: native premium UI engineering preview

The owner's approved cinematic crimson-and-cyan UI is now implemented as a
**separate, opt-in Windows desktop preview**, not as a screenshot or a replacement
for the tested classic program. It shares Game Grave's existing game discovery,
mod safety, Graveyard, Never Touch, Recycle Bin, Undo Center, Save Vault and
Resurrection Kit engines. The classic application and its default entrypoint
remain available during physical Windows 10/11 and Qt redistribution review.

### Windows user preview

Download the unsigned `GameGrave-Crimson-Preview.exe` artifact from
[Crimson Command Windows preview workflow](https://github.com/wrightausername/Game-Grave/actions/workflows/windows-crimson-preview.yml).
The same archive includes **actual Qt screenshots** of Overview, Games,
Graveyard and Game DNA. An unsigned test executable must not be treated as
a public stable installer.

To run from source on Windows:

```powershell
py -m pip install -r ui-preview-requirements.txt
py launcher.py --ui-preview
# Or: py -m gg_desktop --ui-preview
```

The usual `py launcher.py` still opens the classic Tk application.
Do not run both while carrying out Recycle Bin or restore operations;
wait until the current operation finishes before changing interfaces.

### What the new preview actually does

- **Overview:** locally rendered crimson-moon ruins art, real Windows drive
  capacity, launcher counts, actual findings and manual scan/cancel. No
  fabricated reclaimed-space numbers.
- **Games:** Steam, Epic, GOG, EA, verified Battle.net/Blizzard publisher
  entries, Ubisoft, Riot and user-identified launchers appear in **one
  filterable list** whenever local installation evidence exists. Unsupported
  providers and missing last-play dates show `Unknown`, not imaginary data.
  `Uninstall` is restricted to actual Steam app IDs.
- **Graveyard:** clear protection reason; `Unprotect this item` on **exact
  user-owned Never Touch rules** after confirmation; inherited folder rules
  link to Settings; built-in game/mod/save protection remains mandatory.
  Unprotecting does **not** recycle anything. A separate manual confirmation
  invokes the existing Windows Shell Recycle Bin safety/Undo worker.
- **Screenshots:** separate opt-in local bounded preview, no bulk screenshot
  cleanup or background loading of personal image bytes.
- **Game DNA/Mods:** evidence-aware relationship cards and read-only Mod Radar.
- **Old Files/Undo Center:** approved scoped manual cleanup and verified
  Windows restoration; no permanent-delete fallback.
- **More Tools:** create a new Save Vault backup, create/inspect/restore a
  Resurrection Kit, isolated rehearsal, compare kits, detect missing pieces,
  view kit snapshots and prepare an approved PC-to-PC transfer. Original
  classic UI remains accessible from source for advanced manager reconnect,
  scheduled automation and unusual flows.

**Preview limits:** not production code-signed, not approved for the frozen
closed beta, not yet independently tested with consumer Windows 10/11
physical hardware, Narrator, all game managers, cross-version upgrades or
full commercial PySide6/Qt LGPL compliance. Existing `release_gate_status.json`
still blocks a Game Grave 1.0 release until evidence and human approval.

For detailed component contracts and signoff tests, see
[UI_REDESIGN_BLUEPRINT.md](UI_REDESIGN_BLUEPRINT.md).


## Installing Game Grave on Windows 10 / 11

**Planned customer experience:** Download a signed, versioned `GameGrave_Setup_v*.exe`, follow the installation wizard, then launch Game Grave from the Start Menu. Python is bundled. The installer creates an Add/Remove Programs entry and an uninstaller; desktop shortcut is optional. **Free installs need no license key or account.**

**For developers / testers right now:** The source ZIP is not a setup executable. A [successful unsigned installer candidate build](https://github.com/wrightausername/Game-Grave/actions/runs/41129498352) is available as a temporary GitHub Actions artifact with a SHA-256 manifest. To build locally on Windows with Python and Inno Setup 6, run `powershell -ExecutionPolicy Bypass -File .\build_installer.ps1`; the output uses the version in `installer/GameGrave.iss` (currently `GameGrave_Setup_v2.4.0.exe`). **The developer artifact is unsigned and has not passed clean-PC QA. Do not distribute it as 1.0.**

**Source-only quick run:** Extract this ZIP, install Python 3.10+, then double-click `Start_GameGrave.bat`. This is a *developer fallback*, not the eventual consumer install method. Scan PC does not delete files.

**Licenses:** The Free version never asks for a key. Settings > **Free / Pro** contains the planned one-time lifetime Pro activation flow. **Pro isn't for sale or activatable in this preview** because the licensing server, paid checkout, and signing configuration aren't deployed. No fake Pro keys or paid feature locks are included. See `INSTALLER_AND_LICENSING.md`.

## Resurrection Kit 2.0 (preview)

**Preserve a setup:** Open Save Vault and select one discovered save/profile folder,
or select a folder manually. Click **Preserve setup (Kit)**. You may optionally
include one additional mod/profile folder. Choose a ZIP filename and approve
the listed source directories. Keep the generated \`filename.zip\` **and**
\`filename.zip.ggkit.json\` together. No game installation, mods outside your
selected folders, or cloud data are captured.

**Recover a kit:** Click **Preview / Restore Kit**, choose its \`.ggkit.json\`
manifest and an existing recovery parent folder. Game Grave verifies the ZIP
checksum, individual ZIP CRCs, file count and capacity before requesting
approval. A successful restore creates a fresh \`Game_Restored\` directory with
\`Saves\` and optional \`Mods/Profiles\` subfolders. It **never** overwrites
existing game files or changes a mod manager, so you can inspect and reconnect
recovered files manually.

Close the game and mod manager before creating a kit. Link/junction or unreadable
content is not silently skipped: the operation is refused if it cannot preserve
the selected source reliably. Direct one-click modlist redeployment, automatic
game installation and cloud synchronization are still **not implemented**.
The Windows preview is not cleared for use as someone's sole save backup.

## Resurrection Kits: discover a setup and reconnect MO2 (development preview)

After **Scan PC**, select **Game DNA → Find my setup for a Resurrection Kit**,
or **Save Vault → Find my setup automatically**. Select an installed game,
review the per-category recommendations, choose the save/profile/mod folders
to include, and approve the kit destination. A detected MO2 profile and its
mods are associated only through exact installed-game and MO2 instance paths.
Vortex staged-mod suggestions require matching game-install evidence from a
Vortex saved JSON snapshot. Unknown files remain unknown and protected.
The kit is a ZIP plus an adjacent \`*.ggkit.json\` checksum manifest; keep
both files together.

**Clean MO2 reinstall:** Once the game and MO2 are installed again, scan the PC
and open **Save Vault → Reconnect verified MO2 kit**. Choose the kit manifest,
then review the exact installed-game match, new MO2 profile name and mod
folder destinations. Close MO2 and approve. The program restores **only
missing mod folders** plus a **new profile named \`<Original>_GameGrave\`**,
never merges into existing mods or overwrites any game data. Select the
new profile inside MO2 afterwards. Missing enabled mod folders, a changed
plan, incorrect instance, any existing mod-folder conflict or a running
MO2 instance stops the operation. Other kit roles (including saves) remain
in the portable kit for **Preview / Restore Kit** into a separate recovery
directory, not guessed placement into live save directories.

**Vortex:** Automatic active profile restoration is **not supported**.
Its internal live database is not edited. Save and recovered mod folders
are available through the verified kit and safe staged restore. This is a
tested engineering foundation, not a commercial one-click modpack recovery
guarantee; native Windows tests with real MO2/Vortex and installed games
are mandatory before production use.

## Resurrection Lab: five recovery tools (developer preview)

Open **Save Vault → Resurrection Lab** (also accessible from Game DNA). All five workflows run only when you initiate them:

- **Missing Pieces / Readiness:** select a saved `*.ggkit.json` manifest. Verifies the ZIP and identifies enabled MO2 mod folders missing from the kit. Other dependencies and game compatibility are reported as **unknown**, never guessed.
- **Resurrection Rehearsal:** select a manifest and scratch location with adequate space. A disposable copy is restored and SHA-256 checked, then the app removes its own temporary extraction. This does not launch the game or test manager deployment.
- **Living Kits:** select a previous kit and reselect its corresponding save/mod/profile/config folders. Changes are compared using content hashes. Approve a *new*, independent full archive; previous versions are never overwritten. You can **opt in** to tracking specific local folder paths, check metadata changes on demand, and stop tracking. No default background polling or incremental storage deduplication. The new manual revision does not inherit previous manager-verification claims.
- **Time Machine:** choose two verified kit manifests for the same game, compare changes, and optionally recover an older version into a separate new folder. Use **See kit versions in a folder** to browse unverified manifest filenames before selecting versions.
- **PC-to-PC Resurrection:** copy a verified ZIP+manifest into an exclusive new transfer directory with an offline `READ_ME_FIRST.txt` guide, then take that entire folder to the second PC. The receiving PC must install the game through its official launcher. Kit restore and clean MO2 reconnect remain available; Vortex live-state restoration is not supported.

**Important:** all five features are tested in synthetic CI fixtures on Windows and Ubuntu, not yet approved for important saves or release. Nothing deletes installed games or mod data; new archives, temporary rehearsals and portable transfer copies require approval. A valid archive is not proof of an in-game launch or complete mod dependency coverage.

## What's implemented

| Area | Behavior |
|---|---|
| The Graveyard (v1.8) | Working review tab for aged game-related archives, neglected Steam titles and mod-storage findings. Customizable age/category/safety/size filters, free-text search, sortable columns (name, age, size, category, safety), ascending/descending ordering and up to 30 user-named saved views. Reviewable archives can be recycled individually, selected, or **all currently visible eligible** with explicit confirmation. Filtering never changes underlying safety eligibility. Entire games or mod folders are never deleted here. Age is a heuristic, not proof of abandonment. |
| Steam games | Detects Steam manifests across known libraries. Reads local last-play timestamps where available, and launches *Steam's own* uninstall confirmation for a selected game. |
| Steam folder/mod detection | Finds unregistered `steamapps/common` directories and known mod signatures inside registered games. Unregistered never means “safe to delete.” |
| Workshop | Identifies per-game Workshop directories and local-manifest discrepancies for review only. |
| Vortex & MO2 | Scans common staging/download locations and configured MO2 profile/instance folders, including manually selected custom paths. Does not edit deployment data. |
| Additional mod ecosystems | Read-only known-location detection for Thunderstore, r2modman, Prism Launcher, Modrinth, CurseForge, BG3, Sims 4, Wabbajack, FiveM, RedM, ESO, Minion, War Thunder, LOTRO, SWTOR, Guild Wars 2, RuneLite, Path of Exile, and optional War Thunder user content in confirmed Steam installations. Paths may be customized, so detection can be incomplete. |
| Steam caches/downloads | Detects Steam shader-cache and download staging locations. Does not label live updates as junk. |
| Other launchers | Detects installed Epic Games via local `.item` manifests, GOG installations via Windows registry, and explicitly added game-library folders (unverified). Not comprehensive EA/Ubisoft/Battle.net/Xbox integration yet. |
| Explain a folder | Bounded read-only inspection of a user-selected folder with plain-English descriptions and protection flags. |
| Storage History | Stores up to 40 local on-demand scan snapshots and compares tracked differences. No constant monitoring. |
| Make Room | User enters a GB target and gets conservative review routes. “Verified reclaimable” is **0** until genuine analysis and approval support exist. |
| Old Files | Scans chosen folder by modification date. Explicit selection and approval before moving files into Windows Recycle Bin. |
| Undo Center | Records successful recycling and provides an in-app **best-effort** Windows Shell check/restore. Fails closed if multiple matching items or path conflict. Never guarantees recovery. |
| Never Touch | User-configured protected folders plus built-in checks for save/world/Steam/mod paths; prevents recycling via Game Grave. |
| Save Vault | User selects a particular saves/profiles directory and destination ZIP; archives files and verifies ZIP integrity. Source stays untouched. Restore is manual via Explorer. |
| Interface | Simple and advanced navigation, light/dark/system themes, four accent palettes **plus any custom HEX accent via native color picker**, text scaling, and **persisted sort options** independently for Steam Games, Game Mods, Old Files and the Graveyard. Graveyard saved view presets and filters are persisted in the local settings file. **Shareable UI presets** can save, apply, import or export a complete presentation setup without exposing disk data or permission settings. |
| Cancellation | Cancel an in-progress read-only scan, without trying to terminate file operations destructively. |
| Automation (legacy) | Optional Task Scheduler weekly recycling only for aged, approved Downloads extensions. Disabled by default. No game or mod removal. |
| Activity | Local plain-English activity log and CSV export. |

## Safety contract

- **Never auto-delete games or mods.** All new ecosystem scans are read-only.
- **No permanent file deletion action** is implemented. Manual and opt-in scheduled cleanup use Windows Recycle Bin only. If recycling fails, the tool never silently falls back to permanent deletion.
- **M1 recovery now passes on Windows CI:** The earlier Windows test failure was traced to the Recycle Bin's display name hiding the file extension. Undo now compares the exact `System.FileName` plus original folder, invokes the canonical `undelete` action and verifies the restored file. [Native Windows Recycle Bin/Undo tests](https://github.com/wrightausername/Game-Grave/actions/runs/41131958400) now pass, including a byte-identical disposable round trip. Game Grave still requires a successful reversible **temporary canary** before recycling each user file; if recovery fails, it stops. Interactive installed-app tests on Windows 10 and Windows 11 remain an M1 release blocker. See [M1 tracker](https://github.com/wrightausername/Game-Grave/issues/10).
- File removal in the app needs explicit user approval. Scheduling a predefined Downloads recycling rule requires explicit opt-in; once enabled, that schedule follows the approved rule until disabled.
- **Recycle Bin does not immediately free disk space.** Emptying it can make recovery impossible. The Undo Center works only while Windows retains a uniquely matchable item, and its Windows restore integration still needs real Windows compatibility testing.
- Steam uninstall sends a request to Steam. The user approves there and Game Grave does **not** claim it verified the uninstall.
- Saves/worlds, known managed mods, user-defined Never Touch roots, reparse points, and obvious Windows system paths are intentionally protected from the Old Files recycler.
- Caches can regenerate and game updates can be interrupted. Do not remove cache or staging directories while launchers/games are active.
- Apparent sizes may overlap through hard links, shared downloads, compression and filesystem behavior. **No displayed candidate size is guaranteed reclaimable space.**
- **Manual scan by default:** no full-drive background scanning, cloud service, account, telemetry, or game-update polling.

## Tests

From the `GameGrave` folder:

```sh
python -m unittest discover -s tests -v
```

The automated Python unit test suite passes on Ubuntu and Windows GitHub Actions runners, with additional synthetic GUI smoke tests. **That is not equivalent to real installed-app Windows 10/11 QA.** Windows Shell Recycle Bin behavior, registry discovery, UAC cases, multi-drive handling, antivirus compatibility, Microsoft Store installations, installer/signing, and performance on very large libraries need dedicated Windows QA.

## Business model

Planned product tiers: **Free forever** and **$24.99 one-time lifetime Pro** with no subscriptions. This build includes a secure signed-license verification and activation client, but **no live key-issuing service, checkout, public signing key, or Pro-only feature gates**. All implemented features remain usable in Free. Do not sell or market it as shipping Pro functionality yet.

See `FEATURE_STATUS.md` for what has *not* been implemented despite being discussed during the product workshop.

## Upgrade and Codex notes

- `core.load_settings()` imports legacy DustOff preferences when there are no newer Game Grave settings. Existing DustOff automation task ID is intentionally retained to avoid orphaning an enabled scheduled task. Check previously configured Windows Task Scheduler rules before upgrading.
- `graveyard.py` contains the non-destructive review logic; `tests/test_graveyard.py` covers age/evidence/protection behavior.
- `POST_MVP_PERSONALITY.md` records planned witty gaming personality and Easter eggs. None have been implemented yet.
- Read `CODEX_HANDOFF.md` before extending detection or cleanup.

## Customize your lists (v1.8)

- **Steam Games:** sort oldest/newest last-play first, largest/smallest installation, or alphabetical. Unknown last-play stays at the end of the age sorts.
- **Game Mods:** sort largest/smallest, alphabetical, source, or item count; filter by mod source and search text.
- **Old Files:** sort size, last-modified timestamp, or name.
- **The Graveyard:** mix age threshold, category, status (all/reviewable/protected), minimum size, full-text search, sort key, direction, and direct column-header sorting. These controls only change the displayed inventory, never what may be deleted.
- **Saved Views:** after choosing Graveyard filters, select **Save view**, name it, and recall it later using **Saved views**. Use **Remove saved view** or **Reset filters** to manage personal presets. Up to 30 profiles, kept on this PC.
- **Bulk actions:** “Recycle all visible eligible” refers only to the currently filtered rows. It never silently includes hidden results or protected items. There is still an explicit final confirmation and a fresh file-integrity/protection check.
- Custom filters are presentation only. None triggers disk scanning or deletion by itself.

For a headless Linux/Tk smoke test (optional, not Windows QA), run `DISPLAY=:98 PYTHONPATH=. python tests/smoke_ui.py` under Xvfb.

## Share UI themes and presets (new in v1.8)

1. Open **Settings → Appearance**. Pick a prebuilt accent or choose **custom**, then click **Choose any color…** to open your operating system's color selector. Alternatively enter a six-digit HEX code (for example, `#D01277`) and click **Apply HEX**. Custom colors persist and apply throughout the UI. Primary control foregrounds automatically switch between light and dark for contrast.
2. Open **Settings → Shareable Presets** and choose **Save current setup**. Give the preset a name. Up to 30 named setups can be stored locally.
3. Pick your setup in the **Saved presets** dropdown. **Apply** loads it. **Export to share…** creates a portable `.json` file that friends can import using **Import preset…**. Imports show a preview and ask for confirmation before applying.
4. Portable presets include only appearance, layout, per-page sort settings, and generic Graveyard presentation filters (age, size, safety and sorting). They do **not** include installed game lists, search text, file names, file paths, protected-folder lists, local account information, activity, Recycle Bin contents, scan targets, or deletion/automation settings.
5. Imports accept only a tightly validated v1 JSON schema, maximum 24 KB. They cannot run scripts, enable automatic cleanup, bypass file protections or perform any file operations. Importing an older-age filter does not automatically scan the drive: run **Scan PC** yourself to populate any newly eligible results.

File extension note: standard JSON files can be named `my-theme.ggtheme.json` for easy sharing. This is **not** a marketplace, cloud service, or account-based theme system.

## New in v1.9: understand it, then make room

**File Detective:** Open **Game Mods** or **The Graveyard**, select a finding, then click **Why is this here?**. Game Grave uses observed game paths, mod-manager directories, and Workshop app IDs to explain its best guess. **A name match is only a clue**, never permission to delete. You can inspect a different folder under Game Mods → Identify other folder.

**Modlist Guardian (early foundation):** Installed game folders and managed mods remain protected; the app explains why. It does not yet parse full Vortex/MO2 load orders or verify which individual addon dependencies are safe to remove.

**Make Room:** Enter a free-space goal, choose the drive, click **Find ways to make room**. Game Grave shows the drive's actual free space, space still needed with a 10 GB buffer, a few older mod/archive candidates to review in The Graveyard, and neglected Steam games to review in Steam. It never deletes anything from Make Room, or claims that apparent size equals reclaimable space. On a fresh install, click **Scan PC** first.

**Simple first:** new features are short, guided workflows. The customizable advanced view remains opt-in. None of these v1.9 additions changes scan consent, safety rules, shared presets, or scheduled cleanup permissions.

Test with `python -m unittest discover -s tests -v`, then `PYTHONPATH=. xvfb-run -a python tests/smoke_ui_v19.py` on Linux if Xvfb is installed. This is an engineering preview, not a Windows-certified release.

## Installer + Pro key foundation (v2.0)

- `installer/GameGrave.iss`, `build_installer.ps1`, `build-requirements.txt`: builds a regular Windows setup `.exe` using PyInstaller + Inno Setup 6, with install/uninstall, shortcuts and current-user permissions. The installer does not remove save games, mod folders, scan history or personal settings during uninstall.
- `.github/workflows/windows-installer.yml`: optional Windows GitHub Actions workflow once Game Grave lives in its own repository. It builds an *unsigned* installer artifact for testing.
- `licensing.py` and `license_config.py`: Free-by-default license status, explicit future Pro activation via HTTPS, server-signed Ed25519 offline proof verification and tamper-safe failure to Free. No signing private key in client. No Pro key server is live in this build.
- `tests/test_licensing.py` and `tests/smoke_ui_v20.py`: license forgery, offline receipt, activation, preview availability, settings tab smoke tests.
- Before retail release: implement and secure Pro checkout/key service, decide and build actual paid features, code-sign installer/exe, perform real Windows installer/deletion/recovery/upgrade tests.


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

- **Cleanup History** is in the standard sidebar in simple mode, with expandable session detail.

## M2 Game Intelligence / Mod Radar evidence audit (development preview)

From **Game DNA → Mod Radar audit**, review the currently scanned local records without scanning again, changing files or making cleanup decisions. The audit reports uniquely associated mod storage, unresolved ownership, conflicting game claims, redirected paths and stale/incomplete manager snapshots. **Disabled MO2/Vortex entries are not labeled abandoned or safe to remove.** Files linked only by a user-added library are reported as *unverified*, not confirmed game installations. No removal is approved by this audit.

Launcher path validation is conservative: blank, relative, redirected, drive-root and missing install paths are not accepted as evidence that Epic, GOG, Riot, vendor-registered, or custom games are installed. Game DNA rejects multiple overlapping installation claims rather than assigning one at random. Ghost Watch now labels potential missing/added files as **not observed / possibly added** when source roots differ or sampling is truncated. All of these decisions require real launcher and mod-manager testing before M2 is signed off.

### Steam installation and Workshop evidence improvements (M2)

Steam manifests left behind after a game is removed are **not** by themselves accepted as installed games. Game Grave checks that the manifest app ID matches its filename, the install folder exists, and paths do not redirect through symlinks/junctions. The same caution applies to the File Detective: a redirected folder is not proof of ownership. A path that resembles Steam Workshop content counts as an association only when the actual Steam Workshop scanner identified its source, not just because someone named an unrelated folder `workshop/content/<appid>`. These are read-only evidence corrections, not license checks or cleanup permissions.

### Built-in visual learning: Game DNA + Mod Radar (M2)

Game DNA now includes a responsive, read-only **relationship map** (automatically displayed on taller screens; choose **View visual map** on smaller screens). The diagram explains recorded game locations, uniquely associated mod storage, uncertain/unresolved content and why no automatic removal is permitted. The regular textual relationship and manager profile summaries remain available beneath it. In **Game Mods & Hidden Storage**, Mod Radar now includes a crisp three-stage visual guide: **Find → Match → Protect**. Both are drawn directly by the app with native Tkinter, respect dark/light theme colors, remain sharp at different window sizes and do not create any network, scan, file deletion or backup actions. The descriptions are also available as text for accessibility. More visual explainers will be evaluated after accuracy and accessibility checks, rather than cluttering every screen.

### M2 scanner input safety (engineer preview)

Steam metadata files are read only when they are ordinary, bounded-size files, not symlinks or junction targets. Steam library roots must be existing absolute locations without redirected ancestors, including secondary libraries discovered from `libraryfolders.vdf`. Workshop, Vortex, MO2 and other read-only mod roots are similarly skipped when parent directories traverse a reparse point. This limits false positive attribution and unexpected traversal outside selected library roots, at the cost of marking uncommon symlink-based setups unsupported until reviewed. Missing/oversized metadata does not establish that a game or its mods are unused.

### One-click private M2 QA report

After scanning your computer, open **Game DNA → Export QA**. Game Grave asks for confirmation, then lets you pick a **new** JSON filename (existing files are never overwritten). The export contains only aggregate counts of detected games, mods and unresolved associations, plus whether manager profiles have been inspected. It **never includes game titles, usernames, file paths, mod names or private profiles**, and nothing is uploaded. The report is QA evidence for human review, not proof that Game Grave correctly detects every installation or that cleanup is safe.

### M3 Resurrection Lab: trustworthy comparisons and a visual map

**Time Machine** verifies both complete kit archives and uses a content SHA-256 comparison when ZIP size/CRC32 make two files appear identical. This catches rare CRC32 collisions that could otherwise hide changes. Comparing very large kits may take longer, but it never alters live game files.

Open **Resurrection Lab → See how Resurrection works · visual guide** for a responsive, high-contrast four-stage walkthrough: **PICK → SEAL → REHEARSE → STAGE**. It explains the practical difference between verified archive integrity and an unproven in-game recovery, includes a text counterpart, and does not trigger backups or cleanup on its own.

Before sending a Resurrection Kit to another Windows PC, use the [M3 Windows recovery test matrix](M3_WINDOWS_QA.md). The eventual closed-beta task order and identical questionnaire are defined in [BETA_TEST_PROTOCOL.md](BETA_TEST_PROTOCOL.md), but recruitment is gated until M1–M5 acceptance.

### M4 accessibility and keyboard navigation preview

Game Grave now opens within a conservative primary-screen viewport, rather than forcing a 1290×820 window off the bottom of a smaller laptop display. Visible keyboard focus indicators distinguish buttons in both themes.

Press **F1** to open the keyboard guide, or go to **Settings → Keyboard guide (F1)**. Press **Ctrl+1 through Ctrl+7** to switch between Overview, Game DNA, Game Mods, The Graveyard, Save Vault, Resurrection Lab and Undo Center. Press **F5** for the same read-only Scan PC action as the toolbar, and **Escape** to request cancellation while a scan is running. **No keyboard shortcut authorizes cleanup, deletes files or bypasses a confirmation dialog.**

See [M4 Windows QA](M4_WINDOWS_QA.md) for the required keyboard-only, scaling, color-contrast, Windows Narrator/NVDA and small-monitor checks. Programmatic window fitting is not a claim of complete screen-reader support or that every control is accessible on every screen size.

### M4 large libraries: bounded table rendering

Steam Games, Other Launchers, Game Mods and Old Files use keyboard-focusable **Previous / Next** controls instead of attempting to create thousands of Windows table rows at once. Up to 160 findings appear per page; the label shows your current position and the full count, and **no scan results are discarded**. Search/filter/sort still apply across the entire discovered list. Old Files **Select all shown** selects the *visible page*, and every actual Recycle Bin request still requires normal per-file checks and explicit user confirmation. Steam controls are split into more compact rows to suit smaller displays. The Graveyard's existing safety controls are unchanged.

### M4 short-screen sidebar navigation

The main sidebar now scrolls independently from the current page. On small monitors and large text settings, **Settings, Undo Center and Advanced navigation** remain reachable instead of falling below the window. The mouse wheel over the sidebar scrolls its navigation list; page or table scrolling remains separate. Ctrl+1..7 also scrolls the sidebar to reveal the selected shortcut destination. The edition and cleanup-safety reminder stay outside the scrolling navigation list. This is an engineering UI improvement and **not** final Windows screen-reader certification.

### M4 Graveyard large-list review without mass cleanup

The Graveyard now draws **up to 160 findings per page** even if thousands match a filter. The entire filtered review set remains available with Previous/Next, including its total and eligible counts. Checked items persist while you move among pages in the **same filtered view**. **Check page** and **Check eligible on page** do not silently select findings on other pages. **Clear checks** clears your review selections, not the actual files.

**Recycle eligible on page** covers the currently visible page only. **Recycle checked** can use checked items across pages, but **hard-stops when more than 160 items are selected**, before any removal action or confirmation. All pre-existing protection rules, per-file revalidation, manual approval and Recycle Bin behavior remain unchanged. Changing filters prunes selections that are no longer in view so hidden findings are not silently included. Nothing is permanently deleted by the Graveyard and Recycle Bin contents are not yet freed disk space.

### M5 unsigned installer provenance and CI safety checks

A development-only Windows installer build includes a **SHA-256 checksum** and `.build.json` stating the source commit and explicitly marking the artifact **unsigned / not release-approved**. The Windows installer workflow performs a disposable same-version install, repeat install and uninstall smoke test, including byte-level checks that an unrelated fake game save and local preferences file remain untouched. This is engineering evidence, **not** a signed installer or actual multi-version upgrade certification. Follow [M5 Windows acceptance](M5_WINDOWS_QA.md) for real Windows 10/11 testing, production signing, privacy and one-time Lifetime Pro activation before any sale or public release.

### Secure update checks are opt-in and offline by default

In **Settings → More tools → Check for signed updates**, a user may explicitly request a future stable-release check. Engineering previews show **service not connected** and make no network request. The underlying updater verifies a dedicated Ed25519 signature, exact HTTPS host, SHA-256 installer identity and newer-version status before showing any release information. It **never downloads or runs anything**. Production trust keys, approved endpoints and release sign-off are intentionally unset until a real signed distribution channel exists. These checks do not affect Free, lifetime licensing or Undo Center.
