GAME GRAVE - OVERVIEW CLICK-THROUGH FIXES WINDOWS PREVIEW 0.2.11

This version fixes problems found while using Overview as a person would:
Overview dialogs now have readable dark backgrounds; chart slices open their
own category; Enter and double-click inspect a selected storage row once;
typing a mod/file search explains how to reach all results; search selection
shows the folder so equal game names can be distinguished. The dashboard's
existing Cancel control remains available during storage measurement.

The default Overview dashboard layout, artwork and typography are preserved
against 0.2.10 with six pixel comparisons. All twelve other tabs, including
the locked Ready Room, retain their 72 pixel comparisons. The click-through
uses real Qt mouse/keyboard events and disposable files, and is repeated in
native Windows. This is an agent review, not a participant usability study.

This update changes Overview only. Ready Room stays locked at the owner's
approved native-scale version. The shared shell, artwork, styles and every
other tab retain their approved source and appearance.

Extract the entire ZIP, then run GameGrave-Crimson-Preview.exe. On Overview,
choose Scan PC. Add missing libraries with Scan Locations. F5 scans the
existing configured locations; Cancel Scan retains the last accepted results.

Overview now measures actual file sizes in detected game and mod locations
across their drives. Launcher estimates no longer determine the pie or the
Overview game cards. Games, Mods, Other Storage, Captures and Old Files share
one measured total. Nested folders and hardlinked files count once. Deployed
mod hardlinks are attributed to Mods rather than also charged to Games.

The chart shows logical file bytes, not compressed physical allocation or
guaranteed reclaimable space. Click the chart or a legend category to inspect
folders, exact counted bytes, coverage, timestamps and separate drive readings.
Refresh measurement updates file sizes without another inventory scan; Cancel
measurement retains the prior reading. Missing or inaccessible folders show
Unknown/Partial instead of a false zero. Asterisks mark partial size coverage.

The Mods metric counts present individual packages from local manager metadata.
A plus sign indicates incomplete catalog coverage. When individual packages
cannot be identified, the metric explicitly counts Mod locations instead.
Captures and Old Files use the accepted scan's folder and age scope. They are
not a claim that all files on the PC were discovered. Game card sizes include
files inside that installation, including mods; the pie separates shared mod
bytes and counts them once. Detailed folder rows explain any overlap.

Overview search filters the library and activity. Enter opens matching games,
mods and file findings. Favorites persist through the existing settings store.
The library reaches every installation, including equal titles in different
locations. Activity entries open their details; history, metrics and quick
actions open the existing destinations without changing those tabs.

Included PNGs are actual native Windows captures using explicitly labeled
disposable QA files. Normal mode measures the user's detected libraries.
Build-Info.txt ties both EXEs to the source and Windows build. SHA256SUMS.txt
contains both executable checksums. The setup EXE installs this unsigned preview.

Overview is awaiting owner review. Passing tests does not lock or approve it.
