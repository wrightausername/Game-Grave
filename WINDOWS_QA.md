# Windows QA checklist before release

The code was built and tested in a Linux environment with Windows code paths mocked or unexecuted.
The following must be verified on native Windows 10 and Windows 11.

- [ ] Source launch from Start_GameGrave.bat for standard user; clean PC without Python install should show helpful message.
- [ ] Windows `.exe` packaging, new modules included, digital signature and installer checks.
- [ ] Steam default/nonstandard libraries; Steam uninstall confirmation and declined uninstall path.
- [ ] Epic `.item` manifests on real user installations and GOG 32/64-bit registry keys.
- [ ] Vortex hardlink deployments, MO2 profiles, moved mod storage, non-English folder names, junctions.
- [ ] Prism, Modrinth, CurseForge, Thunderstore, r2modman and BG3 real user profile roots.
- [ ] Recycle Bin on fixed NTFS drives, paths with Unicode, spaces, punctuation and long paths; failure must not permanently delete.
- [ ] Undo Center Windows Shell COM check/restore when unique; conflict, duplicate name, empty bin, alternative recycle state, multilingual UI.
- [ ] Never Touch prevents recycle of save folders, Workshop, Vortex and user-protected directories.
- [ ] No path follows junctions, symlinks, permissions leaks or network-drive recursion.
- [ ] User approval before recycling files and before enabling scheduled cleanup; scheduled mode only Downloads allowlist.
- [ ] ZIP backup and integrity checks, insufficient storage, changed files, long/unusual Unicode paths.
- [ ] Theme contrast, keyboard navigation, screen readers, Windows DPI 125/150/200%, small laptop screen and window resize.
- [ ] App remains responsive for >100,000 mods and huge game libraries; cancel scan correctly stops.
- [ ] Absolutely no updates or background polling unless the user opts in.
- [ ] False-positive detection and storage usage regression suite with anonymized real-world fixtures.

### v1.7 customization checks

- [ ] Sort each of Steam Games, Game Mods, Old Files and Graveyard; verify numerical sizes and unknown last-play handling.
- [ ] Mix Graveyard category/status/size/age/search filters, click column headers and test ascending/descending choices.
- [ ] Save, recall, replace, remove and reset user-named view presets; verify preferences survive a restart.
- [ ] Inspect confirmation dialog after sorting and filtering; “all visible eligible” must not include hidden or protected files.
- [ ] Test with many thousands of findings, long paths, narrow screen widths, high DPI and keyboard/screen reader navigation.

## v1.8 preset/theme QA

- Open Settings > Appearance; use Windows color dialog to select custom RGB color; confirm persist after restart.
- Enter a valid #RRGGBB HEX color manually; confirm buttons, sidebar, selection highlight, and text foreground update without crashing. Check very dark, very light, saturated colors.
- Save a named preset; adjust view layout/theme; apply the saved preset; verify presentation only.
- Export preset JSON, inspect it for personal paths/searches/cleanup settings, then import it into a clean profile. Check confirmation before apply.
- Import malformed, oversized, unknown-version, extra-field, and unknown-palette JSON: all must be rejected without changing app settings or launching scans.
- Ensure updated Graveyard age filters require an explicit new scan when broader file discovery is needed.

## v1.9 File Detective / Make Room QA

- [ ] Check File Detective on Windows drive paths with different casing, Unicode, symlinks and junctions. A custom library must be labeled unverified, never an installed game.
- [ ] Test Vortex/MO2 active profiles and disabled profiles; managers may store data outside known locations. Never claim definitive orphan/safe status.
- [ ] With several drives, choose the target drive and check actual free space vs OS Explorer. Ensure old archives on another volume are NOT suggested.
- [ ] Validate small laptop screen at 990x660 and 125%-200% DPI; Make Room and Graveyard controls must stay visible/keyboard usable.
- [ ] Ensure hardlinks, changed/archive files, protected paths, cloud directories and Recycle Bin are not counted as verified reclaimable space.
- [ ] Check the new dialogs with screen readers and a plain-language novice user.
- [ ] Perform real Windows Recycle Bin recovery QA; Linux/Xvfb is not sufficient.


## Installer QA (v2.0 addition, REQUIRED before distributing)

- On a clean Windows 10 and 11 x64 VM: build and run `GameGrave_Setup_v2.0.0.exe`; verify Setup wizard, per-user installation, Start Menu, optional desktop shortcut, Add/Remove Programs and uninstall.
- Launch installed `.exe` on Windows without Python installed. Open every main tab, especially Settings > Free / Pro and existing Recycle Bin / Undo Center. Check quarantines and SmartScreen (unsigned development builds may warn).
- Upgrade from an older installed Game Grave, check installer replacement works, no duplicate entries, settings/history/never-touch and user save backups retained. Test uninstall never touches games, mods, saves or local profile settings.
- Confirm Free runs offline with zero license prompts; fake receipts/tampered JSON never unlock Pro; no key submission possible in this preview. Test paid activation only when live service exists, then verify receipt offline and after restart.
- Later: add signature/timestamp and verify it on the release files. Test multiple user accounts and PATHs with Unicode/spaces.


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


## Version 1.0 milestone M1: mandatory Windows safety witness record (NOT YET SIGNED OFF)

Run on disposable content only, never an important modpack, a live save, or the original kit.
For each Windows version, record OS build, file system, administrator/standard user,
Game Grave commit SHA, whether packaged/installed, date and a permalink to sanitized
test evidence in [M1 issue #10](https://github.com/wrightausername/Game-Grave/issues/10).

- [ ] **Windows 10 x64** standard-user packaged-install manual pass.
- [ ] **Windows 11 x64** standard-user packaged-install manual pass.
- [ ] Scan a disposable Downloads subfolder with old game-like archives; verify stale/new
      distinction, optional manual review, Never Touch and separate confirmation.
- [ ] Create a disposable nested directory junction/symlink that points to a protected
      folder; ensure the recycler refuses the *linked ancestor*, not just linked leaf.
- [ ] Create an NTFS hardlink to a disposable file; verify generic recycling is refused.
- [ ] Recycle one temporary ordinary file on a local fixed NTFS drive. Confirm the file
      appears in the Windows Recycle Bin and disk space is NOT claimed as freed.
- [ ] Check Undo Center and restore that uniquely matchable file; check original content.
      Then simulate an original-path collision and verify nothing is overwritten.
- [ ] Test missing/emptied Recycle Bin records, duplicate path records, locked files,
      and multilingual shell properties. Refusal is acceptable; unsafe restoration is not.
- [ ] Verify no successful restore is claimed if Windows Shell did not confirm the
      path exists afterwards; test UI messages and logging.
- [ ] Make two Resurrection Kits; test safe backup, checksum verification, restore
      into an empty target, missing space, renamed ZIP, modified CRC, Unicode filename
      and an existing target collision.
- [ ] Test interrupted/power-loss recovery in a disposable environment; make sure
      incomplete output is labeled, the source remains intact, and no preexisting
      file or folder is deleted.
- [ ] Verify protected save/mod/manager folders and a running game are never recycled.
- [ ] Record failures and passing evidence in issue #10; do not mark M1 passed just
      because a GitHub Actions test run is green.

A manual workflow exists for a disposable **Windows runner Recycle Bin integration
smoke test**. It is not a replacement for human UI, installer or OS-build coverage.


## M1 repeatable interactive Windows desktop test runner

A native disposable-only helper is available at `tools/windows_m1_desktop_qa.py`.
**This does NOT inspect or touch your real games, mods, saves or Downloads.**
Its input must be an ordinary local fixed-drive scratch subdirectory; it creates
and owns a separate one-time temporary subfolder underneath. It checks:

- Built-in save protection and refusal to recycle a protected file.
- Rejection of hardlinked files and redirected parent folders.
- Portable Resurrection Kit ZIP checksum/Unicode restore and refusal to overwrite.
- A missing Recycle Bin record's honest status.
- A harmless text file's Recycle Bin/Undo round trip, collision refusal and byte-identical restore.

To run with Python from a **local Windows desktop session** on Windows 10 and 11:

```powershell
New-Item -ItemType Directory -Force .\GameGrave-M1-Scratch | Out-Null
$env:GG_QA_DISPOSABLE = 'YES'
python tools/windows_m1_desktop_qa.py --scratch .\GameGrave-M1-Scratch --execute --report .\GameGrave-M1-report.json
Remove-Item Env:GG_QA_DISPOSABLE
```

Choose a fresh report filename each time: the helper intentionally does not
overwrite prior reports. The JSON contains OS product/build and per-test
results only, not personal usernames, original paths or filenames. Attach
sanitized reports to [M1 issue #10](https://github.com/wrightausername/Game-Grave/issues/10).
`SKIP` and `FAIL` are not valid evidence for that acceptance criterion.
Repeat the tests in the **installed application UI** on both Windows 10 and
Windows 11, with non-admin and representative locale/accessibility coverage.
GitHub's automated Windows runner is not a substitute for those sessions.


## M2 real gaming PC inventory QA (read-only, not acceptance by itself)

On a Windows 10/11 PC with Steam/Epic/GOG and optionally MO2/Vortex,
run from the repository source in an ordinary PowerShell session:

```powershell
python tools/m2_real_pc_qa.py --execute --report GameGrave-M2-local-qa.json
```

The M2 helper reads **existing launcher inventory metadata, known mod-storage
roots and manager profile snapshots** on demand. It does not scan every disk,
alter any files, start games, uninstall anything, or upload telemetry. It
generates only aggregate counts grouped by a whitelist of software categories,
plus counts of ambiguous, truncated or stale results. No game titles,
installation directories, usernames, mod file paths or manager-profile names
are included in the JSON report. Use a new filename each time; it refuses
to overwrite a previous report. Press Ctrl+C to cancel.

A human must separately verify detected installs against the launcher UIs,
whether Steam libraries were moved, whether MO2 mods/profiles are actually
active, whether Vortex's available JSON backups are stale, and whether addon
folders are in use. Mark the validation matrix in
[M2 tracker #11](https://github.com/wrightausername/Game-Grave/issues/11).
Do not upload screenshots or logs containing usernames or private paths.
The emitted report deliberately sets `m2_release_accepted: false`, because counts alone cannot prove detection accuracy.

### Easier M2 report export directly inside the desktop app

After clicking **Scan PC** and optionally **Inspect manager profiles**, open **Game DNA → Export QA**. Confirm the privacy notice and choose a new JSON destination. The report contains only whitelisted counts, never raw paths, game names or mod/profile names. A checkmark in the report is **not** an M2 sign-off; compare the actual findings against the launchers/managers on both Windows 10 and Windows 11 and record any false positives or missed storage in [M2 issue #11](https://github.com/wrightausername/Game-Grave/issues/11). The separate command-line helper remains available to developers.
