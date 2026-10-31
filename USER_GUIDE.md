# Game Grave | Getting started and recovery guide

**Engineering preview. Not a certified 1.0 release.** Keep independent backups of important saves and mod setups. Game Grave works locally. Scans do not delete anything.

## First use: scan, understand, decide

Open Game Grave and choose **Scan PC**. The Overview lists detected games, mod storage, older downloads and possible game clips. These are findings, not declarations that anything is unwanted. Last-play and file-age information can be unknown or incomplete. When an item is uncertain, preserve it.

The default sidebar stays short. **Settings → More tools** contains extra pages such as Old Files, Make Room, Storage History and Automation. You can enable advanced navigation in Settings → Appearance.

## The Graveyard

Open **The Graveyard**, select a row, and read the selected-item explanation. Choose **Why is this here?** to inspect the evidence behind the suggestion. The list may include:

- Old, individual mod/game archives from your chosen Old Files folder.
- Possible old game recordings under conventional local capture folders or folders you explicitly add.
- Installed games, mod manager directories and unknown storage shown **for review only**, not direct deletion.

**Protect selected** creates a personal Never Touch rule for an ordinary file. The status refreshes immediately and Delete is disabled. **Unprotect selected** removes only that rule. It does not disable built-in protection or delete anything. Managed games, profile data, active mods and saves remain protected and cannot be overridden here.

**Delete selected** means *move to Windows Recycle Bin*, not permanently erase. Game Grave shows an approval dialog, rechecks the file and its protection status, then asks Windows to verify reversible recovery before moving it. The window should remain responsive during this operation, though Windows checks may take time. **Delete checked** handles a limited reviewed batch. A protected or changed file is skipped, never forced.

**Important:** A Recycle Bin move does not immediately reclaim free space. Emptying Windows Recycle Bin can make recovery impossible.

## If Delete appears to do nothing

Select one individual file in the list, not a folder or installed game. Read whether the selected item is **Ready to delete**, **Protected by you**, or **Review only / protected**. For personal protections, Unprotect first, then reselect the file. If Delete prompts for approval, choose Yes and read the progress status at the top of the app. If Windows cannot verify Recycle Bin recovery, the operation is blocked rather than silently deleting the file.

Under **Settings → More tools**, select **Test Windows recovery (disposable file)**. Choose an ordinary local folder outside your game installs, saves and Never Touch locations. With your approval, Game Grave creates one tiny test file and tries to move and restore those exact bytes. It does not select or delete your personal data. If the self-check fails, inspect Windows Recycle Bin and permissions rather than forcing deletion.

The self-check is a diagnostic, not approval to rely on this engineering build for valuable data.

## Recover something through Undo Center

Open **Undo Center**, locate the relevant recorded move, and request a recovery check. When Windows reports a uniquely matched Recycle Bin item, you can approve restoring it to its original path. Restoring will be refused if a conflicting file already exists at that path. The safest fallback is to inspect Windows Recycle Bin through File Explorer and restore manually to a nonconflicting destination.

An emptied Recycle Bin, permission changes, external cleaners and ambiguous items may prevent recovery. **Do not count Undo Center as your only backup.**

## Game DNA, explained

Game DNA is organized into three plain-language steps:

1. Scan your PC so it knows which games and mod folders exist.
2. Pick a game to see linked mod-storage locations. A link indicates evidence, not proof a mod is needed or unused.
3. Check what changed. The on-demand snapshot compares folder metadata, not in-game compatibility.

Select **Advanced tools and mod-manager profiles** only if you need the visual map, Mod Radar ownership audit, MO2/Vortex profile reports or preparation for a Resurrection Kit. Unknown associations stay protected.

## Old game recordings and duplicate archives

A scan finds possible older clips under familiar Videos/Captures directories. Under Settings → More tools you may **Add capture folder** if recordings are stored elsewhere. Files that match a location or filename hint could still be personal videos, so inspect them in their folder before choosing Delete.

Under Graveyard → More filters, **Find exact duplicate archives** performs an *optional* bounded SHA-256 comparison of older standalone game/mod archives. It may read gigabytes while hashing but never automatically removes matching files. Identical bytes do not prove two copies are unneeded or physically reclaimable.

## Resurrection Kits and recovery

A Resurrection Kit preserves the specific Saves, Mods, Profiles and/or Configs directories you review and approve. Keep **both** the ZIP file and its `*.ggkit.json` manifest. The manifest and archive are checked before restoration. Rehearsal restores an isolated disposable copy and compares contents; actual restore creates a **new separate folder**, never overwrites installed game files.

**Living Kits** create independently verifiable versions. **Time Machine** compares versions and helps choose a separate staged recovery. **PC-to-PC Resurrection** produces a portable package with a setup guide, not a licensed game installer. A ZIP does not prove the modded game or a mod manager will start correctly.

A reviewed MO2 reconnection workflow exists only for supported verified setups and always requires explicit approval. Vortex live-state automatic restoration is **not** supported.

## Other guarantees and current limits

Free works without an account, a key or telemetry. The intended business model is Free plus optional one-time lifetime Pro, but the preview cannot issue paid keys. New game/mod discovery is local and on-demand unless you explicitly enable the legacy Downloads schedule.

**Do not use this engineering preview as the sole protection for important saves or mod setups.** Real Windows 10/11 installed-app, screen-reader, game-manager, signing, entitlement, and closed-beta acceptance remain outstanding. See [the release plan](RELEASE_1_0_PLAN.md) and [release safety checks](WINDOWS_QA.md).


## Review old in-game screenshots

1. Choose **Scan PC**. Game Grave checks Steam's per-game screenshot
   locations (including the Steam account's `userdata/760/remote` folders),
   local Windows/Game Bar `Videos/Captures`, and narrowly named local
   Game Screenshots folders. It **does not search your general Pictures or
   family photo collection** by default.
2. If you save screenshots somewhere unusual, open **Settings → More
   tools → In-game screenshots → Add screenshot folder**. Only folders
   you explicitly add extend the screenshot search.
3. Open **The Graveyard**, choose **More filters → Type → Old game screenshot**
   to see older images. Screenshot entries say **Preview individually**, not
   **Ready to delete**, even if they are very old. Bulk **Check eligible**
   cannot select them for removal.
4. Select one image and choose **Preview screenshot** or double-click
   the screenshot row. Game Grave displays a bounded local thumbnail. The
   image never leaves your computer. Large/corrupt/linked images refuse
   preview; they cannot be recycled through this feature.
5. Choose **Keep screenshot** to leave it untouched, or **Review moving THIS
   image to Recycle Bin**, followed by the ordinary explicit confirmation.
   Windows Recycle Bin recovery must pass its disposable test before
   Game Grave moves this one file. **Never Touch** rules still win.
6. If you change your mind, open **Undo Center**. An item moved into the
   Recycle Bin is not automatically free disk space. Emptying the Recycle
   Bin later is separate and may make restoration impossible.

Supported still images: PNG, JPEG/JPG, WebP and BMP. Scan reads only
filenames, dates and sizes; actual image decoding happens **only after
you click preview**. In-game screenshot origin is a *guess based on the
folder*, not image recognition, so you must check each picture yourself.
For source-code runs, install Pillow for in-app image preview; the
Windows preview/installer bundles it. This tool never performs scheduled
screenshot deletion or mass screenshot cleanup.
