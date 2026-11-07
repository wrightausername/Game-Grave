GAME GRAVE - READY ROOM NATIVE SCALE WINDOWS PREVIEW 0.2.9

This update changes Ready Room only. It fixes the zoomed appearance when
switching into this tab. Ready Room now uses the same native app sidebar,
header, text scale and window dimensions as the other tabs. It no longer
replaces the whole app frame with a separately scaled graphics canvas.

The approved artwork, card arrangement, news, follows, game selection, mod
scan, backup history, verified ZIP backups and local checks are retained.
Content adapts to the available space. Narrow windows scroll vertically to
keep controls readable and reachable instead of shrinking the whole app.

Extract the entire ZIP and run GameGrave-Crimson-Preview.exe. Choose Ready Room.
Start_Ready_Room_Reference.bat opens the same app scale with clearly labeled
sample data for visual review. Normal mode uses your actual local records.

Ctrl+K searches Ready Room. F5 starts the existing read-only scan. Escape
cancels the active scan or clears search. Patch Watch and game rows open their
existing details. View Mods, Run Mod Scan, Manage Saves, Backup Now and the
health gauge keep their existing actions. The shared window controls and
navigation remain in place while entering, leaving or refreshing Ready Room.

Tests cover repeated tab/panel clicks, wheel/Ctrl+wheel events, live refresh
and five window sizes. Window geometry, native sidebar/header and text sizes
must stay stable. All twelve other tabs must pass 72 pixel comparisons against
the previously locked build, with their runtime source and artwork unchanged.

The included PNGs are actual native Windows captures. Reference captures use
explicit sample data; the live capture uses disposable QA files and a verified
backup. Build-Info.txt ties the EXEs to their source and Windows workflow.
SHA256SUMS.txt contains checksums for both EXEs.

GameGrave-Crimson-Preview-Setup.exe installs this unsigned engineering preview.
Ready Room's scaling correction awaits owner signoff. Other tabs are untouched.
