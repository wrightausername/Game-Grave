# Game Grave v2.4 | Gaming Storage Manager

**Status:** Working Windows Python desktop app / engineering preview. Includes a professional **Windows installer build recipe** and secure Free / future lifetime Pro licensing foundation. **The source archive is not an installer executable and has not passed real Windows release QA. Not ready to sell.**

Game Grave finds games, mod-manager storage, Workshop folders, caches, and leftover installation candidates. It clearly separates *detected data*, *potential review targets*, and *space actually reclaimed*. Scanning never authorizes file deletion.

## Installing Game Grave on Windows 10 / 11

**Planned customer experience:** Download one normal `GameGrave_Setup_v2.0.0.exe`, follow the installation wizard, then launch Game Grave from the Start Menu. Python is bundled. The installer creates an Add/Remove Programs entry and an uninstaller; desktop shortcut is optional. **Free installs need no license key or account.**

**For developers / testers right now:** This ZIP contains *source* and the Windows installer project, not a ready-built setup `.exe` (a Windows toolchain is needed). On Windows with Python 3.10+ and Inno Setup 6 installed, run `powershell -ExecutionPolicy Bypass -File .\build_installer.ps1`. Find the standalone installer in `release\GameGrave_Setup_v2.0.0.exe`. Or import the source into a dedicated Game Grave GitHub repo and run the included Windows installer workflow.

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

102 Python unit tests passed on the 2026-10-30 development branch on Linux (pending native Windows CI and QA), plus a virtual desktop smoke test opening the core pages and switching themes/layouts. **That is not equivalent to real Windows testing.** Windows Shell Recycle Bin behavior, registry discovery, UAC cases, multi-drive handling, antivirus compatibility, Microsoft Store installations, installer/signing, and performance on very large libraries need dedicated Windows QA.

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
