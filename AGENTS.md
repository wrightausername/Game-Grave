# Approved UI foundation

The owner's locked photos are the visual specification, not the current code or
prior preview screenshots. The unmodified originals are in
`gg_desktop/assets/references/`; the Ready Room original is also in the owner's
conversation. Do not replace their shell, artwork, proportions, cover grid,
filter columns, metrics, tabs or right-side inspectors with generic tables.
Prior code-baseline pixel checks do not establish fidelity to the photos.

Before editing UI,
acknowledge the exact requested sections in chat. Confine changes to those
sections and preserve all other screens, the shell, navigation, styling and
behavior. An overall redesign requires an explicit request from the owner.

## One tab at a time; completed tabs stay locked

- Work only on the single tab the owner currently names. Acknowledge that tab
  and the requested sections in chat before editing. Do not expand the scope
  to other tabs or start the next tab on your own.
- The owner decides when the tab is complete and when to move on. Passing
  checks or declaring the work finished does not replace the owner's signoff.
- Once the owner accepts a tab and says to move on, that tab stays locked
  across later tasks, turns and branches. Do not change its layout, artwork,
  controls or behavior unless the owner explicitly instructs you to change
  that tab again. Record explicit tab signoffs here as they occur.
- This restriction includes indirect changes through shared styles, widgets,
  navigation, controllers or backend code. Work on the active tab must preserve
  every locked tab. Read-only inspection and regression checks are allowed.
- If the requested work requires changing a locked tab, identify the exact
  dependency and wait for the owner's explicit instruction before that change.
  Continue only independent work within the active tab. Refactoring, cleanup,
  consistency work or an incidental fix does not authorize reopening a tab.

## Locked tabs

Ready Room: OWNER APPROVED AND LOCKED. The owner explicitly accepted the result
and instructed that it must not be touched unless they specifically say otherwise.
The approved runtime baseline is commit
471eb2bb088915573d99e7010f8472a28a274b9a, Windows preview 0.2.9:
https://github.com/wrightausername/Game-Grave/actions/runs/42320457095

Preserve Ready Room's layout, typography, artwork, scaling, controls and behavior.
This includes its native app scale and shared sidebar/header, search, icons,
actions, data/services and assets. Changes to shared styles, components or
backend code must not alter the approved Ready Room. It must not replace,
resize or magnify the shared app shell when navigating into the tab.
Keep sample data confined to the explicitly labeled reference preview.

Read-only inspection and regression checks are allowed. A discovered issue,
refactor or work on another tab does not authorize reopening Ready Room.
Only the owner's explicit instruction to change Ready Room can unlock it.

The owner explicitly approved and locked the native-scale correction, then
instructed work to move back to Overview. Ready Room is no longer open for edits.

Mods: OWNER SIGNED OFF AND LOCKED ("Good lock it in"). The approved baseline is commit
d83f972716d258aa10d8e1005539f460160fe2d1 on branch `claude/mods-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42458764179. Do not change its
layout, tabs, controls, statuses or behavior, or anything that reaches it through shared
styles, widgets, navigation, controllers or backend code, unless the owner explicitly
reopens it. The next tab's lock must freeze Mods against this commit.

Old Files: built with full functionality on branch `claude/old-files-full-functionality`
(latest verified Windows run for its content:
https://github.com/wrightausername/Game-Grave/actions/runs/42465551781). The owner moved on to
Other Storage after the banner fix, so Old Files stays locked unless the owner reopens it. There was
no separate "lock it in" message, so treat that as not formally signed off. Nothing in Old Files
permanently deletes; removal is Recycle Bin only after the existing re-checks.

Other Storage: OWNER SIGNED OFF AND LOCKED ("good lock it in"). The approved baseline is commit
0689695ee5ada524f0c96eaa674488b8c2e180be on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42469660937. Do not change its layout,
tabs, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: no invented "safe to clear"; driver and Steam
library caches are review only; settings and saves are never removable; launcher cache and log folders
of 200 files or fewer go to the Recycle Bin only after confirmation and per-file re-checks. Widening
deletion (core is byte-guarded) needs the owner's explicit approval, which has not been given. The
next tab's lock must freeze Other Storage against this commit.

Captures: OWNER SIGNED OFF AND LOCKED ("good lock it in"). The approved baseline is commit
8402ac06a190b3e7164a21c48322c17043f190bf on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42475554496. Do not change its layout,
tabs, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: ownership only from proof, never a "safe to
delete" claim, Recycle Bin only after confirmation and per-file re-checks. The next tab's lock must
freeze Captures against this commit.

Graveyard: OWNER SIGNED OFF AND LOCKED ("Yes lock it in"). The approved baseline is commit
1202b47cad0103c3a8aed61d2c13b67cdbf2de15 on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42478374434. Do not change its layout,
tabs, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: the Evidence column (Direct, Location, Name hint,
Age only, Yours) replaces any confidence claim, "Reviewable" never means safe to remove, leftover
scanning only runs when the owner presses Scan Leftovers, and removal is only single archives or
recordings to the Recycle Bin through the existing verified path (screenshots one at a time after
preview; games via Steam; mods via Mods; folders via Other Storage). The next tab's lock must freeze
Graveyard against this commit.

Game DNA: OWNER SIGNED OFF AND LOCKED ("yup lock it in"). The approved baseline is commit
7936f7e73fe9d28295715a48b65ca8a0998659c9 on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42498533084. Do not change its layout,
tabs, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: only proven locations are counted (install folder,
mods in it or tied by Steam Workshop ID, Steam shader cache by app ID, Steam per-game screenshots, folders
the owner links), saves and configs are never matched by name, Cleanup Suggestions hand off to the
owning tab and never delete, and nothing is called safe to remove. The next tab's lock must freeze Game
DNA against this commit.

Undo Center: OWNER SIGNED OFF AND LOCKED ("lock it in"). The approved baseline is commit
e96fd44bf86d79a882e42f34b210a4783fe7ce63 on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42505113783. Do not change its layout,
filters, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: recycled bytes are "Recycled Size", never freed
space; no reversibility percentage; restore only through the protected recovery engine after a fresh
check and confirmation (one matching Recycle Bin item, free original path, never overwrite, batch of
20 at most); "Hide from History" only hides a row through settings and never edits recovery records or
the activity log. "Restore to Custom Location" is not built because the engine restores to the original
path only; adding it needs the owner's explicit approval to change `recovery.py`. The next tab's lock
must freeze Undo Center against this commit.

AI Assistant: OWNER SIGNED OFF AND LOCKED ("Lock in ai assistant for now and move on"). The approved
baseline is commit 040951c7c85c367d23841c091573e1610fe11e67 on branch `claude/old-files-full-functionality`,
Windows run https://github.com/wrightausername/Game-Grave/actions/runs/42512547513. Do not change its
layout, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: a local, rule-based, read-only assistant over
scanned data the owner switches on; it answers only from enabled sources and names sources that are off
or empty; sizes are "reported", never freed; it never says anything is safe to remove; it hands off to
the owning tab. The next tab's lock must freeze AI Assistant against this commit.

Settings: OWNER SIGNED OFF AND LOCKED ("Yes", to locking it and moving on). The approved baseline is
commit d4ec9782e66dad9e8f9b8f0f3c2bd2cf6b605e7c on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42517152855. Do not change its layout, tabs,
controls or behavior, or anything that reaches it through shared code, unless the owner explicitly reopens
it. Its honest-claims rules stay: preferences are staged and saved only on Apply; Protection switches are
always on and cannot be turned off; Never Touch rules are only added or removed one at a time with a
confirmation, and Import and Reset never remove one; excluded folders only leave results out of scans and
never touch a file; update checks, notifications, accent and scale are shown as unavailable or fixed, not
faked. Shared code changed with the owner's approval: `settings_store.load_settings` (saved keys survive a
restart) used by `app.py`, start minimized in `app.py` main(), the excluded-folder filter in `backend.py`,
and the Mods stale-row guard in `mods_page.py`. The next tab's lock must freeze Settings against this commit.

Polish pass (owner instruction, 2026-11-08): the owner explicitly reopened the shared shell (sidebar logo,
bottom-left backdrop, nav order, scan bar), Ready Room (banner, live Steam news), Games (HD launcher marks and art),
Mods (banner, sorting), Old Files (banner), AI Assistant (optional, off by default), Settings (the AI switch) and More
Tools (implement the seven dimmed tools). Tab pixel locks do not run during this pass; each change is covered by a
native smoke instead. Owner decisions: the logo and backdrop are rebuilt as HD PNGs (`gg_desktop/assets/brand/`,
`tools/make_forest_art.py`); Ready Room auto-refreshes official Steam news only; the owner approved fully
implementing the seven More Tools tiles, which is the one approved exception to "Game Grave never changes Windows or
runs commands": every such action must name exactly what it will change, ask first, and be recorded in the activity
log. Protected engines still need explicit approval before any edit, except where the owner's polish message names
the feature: `ready_room_actions.py`, `ready_room_data.py` and `ready_room_services.py` were released from the byte
guard for live Steam news (auto-refresh on open and every 30 minutes while open, Last checked, manual Refresh).

Polish pass, second message (owner instruction, 2026-11-08): the owner also reopened the Overview banner, the bottom-left
sidebar art, the art of every tab's header, the scan bar and the wording of the Mods tab. Decisions: one restrained abstract panoramic HD
picture per tab, symmetric top to bottom so it stays centred (`tools/make_banner_art.py`, `gg_desktop/assets/brand/banner_*.jpg`; no illustrations), fills the full header width at any
window size and replaces the photo crops in headers; the sidebar backdrop is a subtle abstract gaming picture
(`tools/make_nav_art.py`) drawn only in free space under the menu; the scan bar is a clear strip with step, percent,
elapsed time, an "about N left" estimate (only after a step has finished, or from the last scan) and Cancel; the Mods tab
uses plain words (`gg_desktop/mods_words.py`) without changing any fact it shows or claiming anything is safe.
Every page heading shows the tab's own sidebar symbol (`ROUTE_SYMBOLS` in `reference_widgets.py`) instead of the slash.

Active tab: More Tools. The owner's photo is `gg_desktop/assets/references/more_tools.jpg`. Work is confined
to new `tools_*.py` modules, a `tools_page` delegation in `photo_integration.py` and the More Tools tests and
tools. Every locked tab above stays frozen.

Earlier history (kept for context; none of these tabs is open):

Games: the owner reopened it to finish launcher management, ownership/update/playtime
integration and artwork coverage, then fixed its banner artwork. Not signed off; frozen at
the commit above. Account connections, private storage and provider adapters stay Games-only.
Show accurate capabilities and data sources; never substitute fake ownership, playtime or
completion messages.

Overview: preserve exactly as in Windows preview 0.2.12, commit
df6bd6628adf6dd9713fe41235acb618da594574. No further Overview edits and no new signoff.

Polish pass, third message (owner instruction, 2026-11-08): the owner approved the Mods mockup ("better, implement it")
and asked for more graphics, kept restrained. Implemented in `gg_desktop/mods_graphics.py` (painted display only, with
pure helpers in `mods_visuals.py`): status pills with Update and Conflict badges, size bars, glowing stat tiles with a
Turned On meter and a Space Used share bar, a ring beside the plain-words summary, a per-mod hero picture, a
load-order stack, and conflict and update cards. Every picture is drawn from a number the tab already shows in words;
no new claim, no "safe" language. `MetricStrip` only gained `glyphs` and `word_columns` lists, with no visual change.


New features, first build (owner instruction, 2026-11-09): the owner asked for the five features discussed earlier
("wtf build them"). Built one at a time, each with CI and real screenshots before the next: Soulbind, then Black Box,
Autopsy, Exhume, Squad Sync. Soulbind is a Ready Room panel plus a small badge on Games cards. It is honest by design:
a preference counts for a game only when its exact key is found in that game's real settings file. Apply changes only
that value, saves a dated backup first and logs to the activity log; Undo restores the backup only if the file has not
changed since. Share codes hold only the ticked preferences. The locked photo-reference preview never shows the panel.
Referral program, owner command center, paywall and Afterlife wait on a server and payment-provider decision.

Banner art, redone (owner instruction, 2026-11-09): the owner asked for new abstract, gamer-related header art on all
tabs, in the spirit of the sidebar art but not similar to it. `tools/make_banner_art.py` now draws one distinct
abstract gaming motif per tab (pixel equalizer, perspective tunnel, HUD reticle, modular diamonds, glitch bands, HUD
health bars, viewfinder, pixel sparks, pixel helix, rewind chevrons, mixer sliders, constellation, block puzzle),
kept clear of the sidebar's hex grid, circuit traces and gamepad outline. Same rules as before: 6000x500, symmetric top
to bottom, calm on the left behind the title, full header width. Only the picture files changed; no layout, control or
behavior changed.

Graphics pass (owner instruction, 2026-11-09): the owner said the Hardware tab should look fancier and that the Mods tab
"is just a jumble of numbers", which reopens Mods for graphics only. Mods sub-tabs (Mod Radar, Load Order, Profiles,
Conflicts, Cleanup) now draw count chips, an on/off bar under each profile, a load-order rail, a profile ring, a source
type bar, coverage cards, a conflict banner and a picture for empty tables (`gg_desktop/mods_tab_graphics.py`, pure
helpers in `mods_visuals.py`). Hardware gets ring gauges, smooth live charts, a core grid, memory slots, speed bars and
drive bars (`gg_desktop/hardware_graphics.py`). Painted display only: every shape comes from a number or word the tab
already shows, cell text is unchanged, no new claim, nothing called safe, and no behavior, control or engine changed.

Hardware: OWNER SIGNED OFF AND LOCKED ("I like it lock it in", 2026-11-09). The approved baseline is commit
f3067827ced6a12d4dcf50682e1bf436bd9222b1 on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42747155944. Do not change its layout, tabs, controls or
behavior, or anything that reaches it through shared code, unless the owner explicitly reopens it. Two tabs inside:
Your PC (rig map, live gauges and charts, drives donut, parts as cards, Copy Specs, Save as .txt, Re-read Hardware) and
Upgrade Advisor (notes, Record Play Session, Session Peaks, Recorded Sessions). Its honest-claims rules stay: parts only
from Windows, CPU temperature never shown, graphics load, video memory and temperature only through nvidia-smi, upgrade
notes only from at least 3 sessions of at least 2 minutes the owner recorded, each note says what was measured and what it
cannot tell, and there are no frame rate, price or "safe to buy" claims. Everything painted comes from a number the tab
already shows. The next tab's lock must freeze Hardware against this commit. Mods stays open only for the graphics pass
recorded above; it has not been separately signed off.

Settings, update check (owner instruction, 2026-11-10, answered "yes" to an in-app Check for Updates button): Settings is reopened
for this one control only. The version box now has a "Check for Updates" button (`update_check.py`). It runs only when pressed,
asks the GitHub releases list for the newest preview installer, and reports in words whether this PC has it, using the build the
Updater last installed; if there is no record it says so instead of guessing. It downloads and installs nothing. "Open Updater"
launches GameGrave-Updater.exe or opens the releases page. The "Check for updates on launch" switch stays off and unavailable;
nothing is contacted automatically. The rest of Settings stays locked.

Mod Bisect, engine only (owner instruction, 2026-11-10, "I like 1", plus a request for a sophisticated recently-added ordering):
`gg_desktop/bisect_core.py` is a pure decision engine with no screen, no file access and no game launch. It proposes one
test at a time (exactly these mods on), the owner answers crashed / fine / not sure, and it narrows with delta debugging, so
it works for any number of mods that conflict (one mod, a pair, a group, or several separate causes found one after another).
Every named group is proven by the owner's own launches: it crashes on its own (asked twice), taking away any one member
stops it, and with every found cause off the game runs. Timing clues only ORDER the search and never decide it: "started
after I added these" (`hint_keys`), "started in this time" (`window`), "last time it worked" (`last_good`), code mods, crash-log
hits. A wrong clue costs launches, never correctness. `batches` groups mods installed together so a downloaded pack can be
picked from a list; `recent_order` gives the newest-first ordering with plain reasons. It checks the crash reproduces with
everything on and stops with everything off (else "not a mod"), keeps dependencies together, handles crashes that do not
always happen with a detection rate and repeat runs (confidence is stated, never 100% when it is not), reports which single
member is enough to switch off, and stops honestly ("undetermined", with what it narrowed to) after MAX_TESTS launches.
It never calls anything safe. Measured with 400 random cases (10 to 400 mods, 1 to 8 mods per cause, up to 3 causes,
dependencies, always-on mods, flaky crashes, right and wrong clues): 0 wrong answers; 97% finished, the rest (all 400-mod cases with several large causes) stopped honestly.
Crash reports (owner instruction, 2026-11-10, "reference crash reports too if it can find them"): `gg_desktop/bisect_clues.py`
is pure too: it is handed report text and Black Box crash records (it opens no file) and returns which mods have files named in
reports, which mod owns the file Windows recorded as the crash location, and when the crashes began. File names shared by
several mods are ignored, never blamed. These only ORDER the search (`fault_keys`, `crash_hits`, `started_after`); a report
naming a mod is not proof. After a verdict, `cross_reference` compares the reports with what the launches proved: it says
when they agree, says "named, not the cause" for a mod that stayed on during the clean run (never for a mod that was off with
the cause), and for a crash with every mod off it points at the non-mod file the reports name (graphics driver, DirectX, Windows)
and what the recorded exception code means. `what_reports_say` summarizes the reports before any testing. The launches always
win; the cross-check never changes a verdict. Finding the reports on disk is Black Box's job and belongs to the future screen layer.
Bisect tab (owner approval 2026-11-10, "Yes to all"): a Bisect tab inside Mods, copy-based writes, and a date the owner enters for
"last time it worked" with Black Box crash times as a hint only. Logic lives in pure, tested modules (`bisect_flow`, `bisect_model`,
`bisect_units`, `bisect_store`, `bisect_apply`); `bisect_tab.py` is the thin Qt layer and `tools/bisect_tab_smoke.py` drives it on
Windows CI. Write model: Mod Organizer 2 only. It makes `<profiles>/GG Bisect - <profile>` (with a `gg-bisect.json` marker and
`GG-original-modlist.txt` / `GG-original-plugins.txt` backups) and rewrites only that copy's `modlist.txt`. It never touches the
original profile, never deletes (the owner removes the copy in MO2), and refuses a folder without the marker, links, a profile that
keeps its own saves, writing while MO2 runs, and mods not in the list. Other managers get a list to apply by hand. Modlist names are
folder names, never manifest names. The install date is the mod folder's creation time. Do not widen these writes without approval.
Mods otherwise stays open only for graphics.


Ready Room, Mods names, Hardware and Undo Center reopened for one pass (owner instruction, 2026-11-10, "soulbind needs more
settings ... less intrusive ... autopsy should be automatic ... undo center easier on the eyes ..."). Only these parts were
reopened; the rest of each tab stays as locked.
- Background rule (owner: "cant be super intrusive as to hinder performance on users PC when gaming"): every automatic job is
  bounded, spaced out, and skipped while a game runs (`window._games_tracker.ledger.active`). Never add unbounded or polling work.
- Ready Room panels (Soulbind, Autopsy, Exhume, Squad Sync) are slim `feature_strip.collapsible` strips: one header line plus a
  status line, body hidden until opened. Patch Watch and Your Games at a Glance show game artwork through `ArtThumb`.
- Soulbind: a preference counts only if its exact key is found in the game's real config file; unsupported otherwise.
- Autopsy is automatic (`autopsy_library.py`, pure). Game Grave keeps only its own summaries of the newest 10 captures; the 11th
  drops the oldest from Game Grave's file, never the owner's CSV. Passes are bounded and skipped while a game runs.
- Squad Sync / Nexus (`nexus_core.py`): the owner's personal Nexus API key, stored with Windows DPAPI (owner-only file elsewhere),
  sent only to api.nexusmods.com. Downloads are Premium-only direct links, host allowlist (nexusmods.com, nexus-cdn.com), new files
  only, batch of 10, nothing is installed. Steam Workshop pages open through `steam://`; Steam decides about subscribing. A true
  Wabbajack-style login needs Nexus to register Game Grave; do not fake one.
- Mods names: `readable_name` turns folder names into readable names and keeps the folder name in the tooltip and detail panel.
- Hardware: the Live Monitor is full width above Your Parts and Drives, with larger gauges. Same readings, same honesty rules.
- Undo Center: larger type, brighter text and roomier rows, scoped to this page (`TABLE_STYLE`, `ReadableName`). Behavior and
  `recovery.py` are untouched.
- Prompts: `theme.STYLE` makes every dialog and message box dark with light text (covered by `tests/test_theme_prompts.py`).

Mods Library redesign (owner instruction, 2026-11-10, "good fully implement that", after viewing the gallery mockup): Mods is
reopened for the Library tab only. The Library now opens as a gallery (`gg_desktop/mods_gallery.py`, Qt; pure facts and wording in
`gg_desktop/mods_gallery_data.py`): a poster wall of your games (each game's own artwork when Game Grave already has it, else a drawn
colour field), a banner for the picked game with its counts and a health bar, "Needs attention" (conflicts first, then updates your
mod manager recorded), "Recently changed" (folder change time, newest first) and "No change date" card rows, and a search box and
Gallery / List switch above them. List is the previous table, kept as it was with its filter column. The other six sub-tabs, the
engines (`mod_conflicts`, `bisect_*`, writes) and every other locked tab are untouched.
- Honest-claims rules stay: every card is drawn from a fact the tab already has (saved profile status, MO2's recorded update, the
  file-sharing check, the folder's change time). A check that has not run shows "not checked", never zero. Nothing is called safe.
  Game Grave does not install or change mods, so a flagged card offers Review (opens Conflicts) or Details, never Update or Turn Off.
  A conflict is "shares files with", not a verdict on which mod to keep. Mod pictures are the game's artwork plus a colour from the
  mod's name; there is no per-mod picture and none is invented.
- The inspector gets the game's artwork behind the status and version chips, and "Open in Conflicts" as the main button when the
  mod shares files with another; Open Folder, Details, Mod Page and Manager stay.
- `tools/mods_gallery_smoke.py` drives it on Windows CI; `tools/mods_page_smoke.py` switches to List first and still covers the table.

Ready Room Black Box, Overview storage graphic, AI Assistant answers and hover text (owner instruction, 2026-11-10, "black box
needs to be minimizable ... storage overview graphic ... AI assistant doesnt really do much ... better description when hovering").
Four scoped reopenings; everything else in these tabs stays as locked.
- Ready Room: only the Black Box panel changed. It is now a `feature_strip.collapsible` strip like Soulbind, Autopsy, Exhume and
  Squad Sync (one line, Open / Hide), body unchanged.
- Overview: only the storage dial's centre mark. `OverviewRing.brand_mark` draws the real GG mark cut out of the full-resolution
  transparent `game_grave_logo.png` (`insight_widgets.gg_mark`, resampled to device pixels) instead of a screened crop of the photo.
  The same dial class on Other Storage and Game DNA is unchanged.
- AI Assistant: feature and "how does it work" questions (Resurrection Kit, Save Vault, Black Box, Exhume, Autopsy, Soulbind, Squad
  Sync, Undo Center, Graveyard, Old Files, Game DNA, Mods Library, Hash Checker, Data Used) are answered from
  `gg_desktop/assistant_features.py`, which only states what the code does and never says anything is safe to remove. Scan-data
  intents, sources, safety and hand-offs are unchanged and checked first-class by `tests/test_assistant.py`.
- More Tools hover text: Resurrection Kit, its seven menu actions and the Go tiles now say what they read, write and never do.

Resurrection Kit, whole installation (owner instruction, 2026-11-10: "must be easy to set up ... not just archiving the mod zips but
the whole installation so that it works on the game immediately"; answers: engine change approved, "Installs + saves + load order.
Don't cap at 80 gigs. No cap at the user's preference and discretion"). The protected kit engine `resurrection_v2.py` was changed
with that approval; every older kit still restores (`tests/test_resurrection_v2.py`, `test_resurrection_lab.py`, `test_m1_safety.py`
pass unchanged).
- Engine: new parts "Game" (the whole install folder), "LoadOrder" and "Launcher" (explicit files: plugins.txt, the Steam
  appmanifest). The 80 GB cap is gone and the file cap is only a structural 5,000,000; free space is checked before anything is
  written and the owner confirms the size. Already-compressed game data is stored, the rest deflated at level 1. `create_complete_kit`
  takes `origins` (templated places such as `%LOCALAPPDATA%\...`, never a user name or a drive path), `progress` and `cancel`
  (a cancel removes everything it wrote). Links and junctions are still refused, now naming the item.
- Restore: `plan_installation` (read-only preview) and `restore_installation`: the install goes into a NEW folder in a library the
  owner picks; the Steam manifest only into a `steamapps` folder; saves, settings and load order back to their original place only
  where it is free (an existing file or non-empty folder is never touched, the kit's copy goes to a review folder); mod-manager
  parts always go to the review folder. The whole kit is verified (SHA-256 and CRC) first, and any error or cancel removes exactly
  what the restore created. `restore_kit` (review folder) is unchanged.
- `kit_easy.py` (pure) offers parts for one game only from proof: install and Steam record from the launcher record, saves only when
  the save scanner labeled the folder with that exact game or the owner linked it in Game DNA, settings and extra mods only from Game DNA
  links, Profiles and Mods from verified Mod Organizer 2 discovery, and the load-order file from a small table of games whose
  plugins.txt or modsettings.lsx location is known. `gg_desktop/kit_easy_ui.py` is the Qt layer (Set up a kit for a game, Restore a game
  from a kit; progress bar, Cancel, confirmation first), reached from the Resurrection Kit menu in More Tools.
- Honest limits shown on screen: launcher accounts and licences are not part of a kit, so a launcher may sign in or re-verify the first
  time; a restored game is not promised to run, only restored. Nothing is called safe.
- Covered by `tests/test_kit_install.py`, `tests/test_kit_easy.py` and `tools/kit_easy_smoke.py` on Windows CI.

Bug pass (owner instruction, 2026-11-10, "do some passes ... fix any bugs you can find"). Fixes only; no layout or feature change.
- Ready Room strips remember whether they were open for this run of the app (`feature_strip._REMEMBERED`), so the page rebuilding
  itself for live news no longer snaps an open panel shut. Every panel still starts closed when Game Grave starts.
- `app.Job` no longer raises when its window was closed while the job was still running.
- AI Assistant: a game whose title contains a feature word (Graveyard Keeper) is answered as a game, not as the feature.
- Kits: Documents is asked from Windows (OneDrive can move it) instead of assumed; the kit check and fingerprint steps show progress
  and can be cancelled; restore refuses a blocked destination before the long check; restored files get their recorded time back
  (older games order plugins by file time); kits without role details restore to the review folder; parts that overlap or are empty
  are flagged on the setup screen instead of failing at the end; the restore note no longer says the install was restored when the kit
  had none.

Checklist pass (owner instruction, 2026-11-11, after viewing the finish checklist: "Skip number 2 for now and complete and polish the
rest. Go"; number 2 was real-PC testing). Each item below names the tab it reopens; everything else in those tabs stays as locked.
- More Tools / kits: kits record empty folders (names in the manifest, the ZIP still holds files only) and a restore recreates them;
  GOG, Epic and Microsoft Store copies of Bethesda games use their own load-order folder; the kit menu shows the two everyday
  actions with the rest behind "More kit tools"; a restore stops before writing when a path would be too long for this PC; the
  restore screen offers "Put mods back into Mod Organizer 2" for kits that hold a verified MO2 profile and mods (`mo2_reconnect.py`,
  unchanged: new mod folders and one new profile only, never an overwrite, MO2 must be closed).
- Ready Room / Squad Sync (owner's original ask, "one-push download all and install"): with Nexus Premium, Get what's missing
  downloads the missing Nexus files and `gg_desktop/squad_install.py` installs the plain zip ones into Mod Organizer 2 as NEW,
  switched-off mod folders under the host's mod names, with a meta.ini. It never overwrites a mod and never edits a profile or load
  order. FOMOD installers, 7z and rar archives and unknown layouts wait in MO2's Downloads tab with the reason. No outside program is
  run. Switching the mods on and matching the host's order is still done in MO2; a profile copy for that needs the owner's approval.
- Hardware: for cards without nvidia-smi (AMD, Intel), graphics load and video memory in use come from Windows' own performance
  counters through PDH (`hardware_core.WindowsGpuCounters`), the figures Task Manager shows. Temperature and total video memory stay
  NVIDIA-only and are shown as such. This replaces the earlier rule "graphics load and video memory only through nvidia-smi".
- Games: at narrow widths the launcher strip and tab row swap a long caption for a whole short word (`gg_desktop/games_fit.py`) instead
  of being cut; inspector labels are wider; the quick actions read Verify, DLC and Uninstall with specific tooltips.
- Mods: the Gallery / List choice is remembered (`mods_library_view`).
- Overview / Other Storage / Game DNA: every storage dial shows the cut-out GG mark.
- Undo Center: Soulbind, kit, Exhume and Squad Sync events read in plain words with where to undo them (`undo_data.FEATURE_EVENTS`).
  Undo Center itself still restores only Recycle Bin records.
- Settings: "Check for updates on launch" is a real switch, off by default (one request at start, nothing downloaded, no pop-up);
  "Soulbind new games" (off by default) applies the saved Soulbind profile after a scan to games that were not installed before, once
  their settings file exists, with the usual backup and log (`gg_desktop/soulbind_auto.py`); the Appearance button opens More Tools.
- AI Assistant: feature answers for Mod Bisect, Hardware, Check for Updates; Squad Sync and Soulbind answers updated.
- Shell: screen-reader names are filled in for unnamed controls on every page (`gg_desktop/a11y.py`); the running-game check slows
  down while a game runs or nothing has run for a while (`games_tracking.next_interval`), always under the 20-second playtime gap.
- Not done, by design: code signing (needs a certificate), licensing, referrals and the command center (need a server), widening
  Other Storage deletion and Undo Center custom restore (protected engines), Bisect writes for Vortex (its state is a database Game
  Grave will not edit), accent colour and interface scale.

Squad Sync, made obvious (owner instruction, 2026-11-11: "continue the checklist... also refine the squad sync... ya it gives you a
code but wtf are you supposed to do with that"). Ready Room is reopened for the Squad Sync panel only.
- The panel is two plain flows with numbered steps: "Hosting? Share your setup" (Copy squad code, Save code as file) and "Joining? Match
  a friend" (Paste a friend's code, Open a code file). After a copy the panel says what to do with the code, and warns when it is too
  long for one Discord message. A bold "Next:" line always says the next step (`squad_core.next_step`).
- Paste a friend's code reads the clipboard first; `squad_core.find_code` finds the code inside a whole chat message or broken over
  lines. Your own code on the clipboard is not treated as a friend's. A code for another installed game switches the game for you.
- Make squad profile (`gg_desktop/squad_profile.py`, pure): the same copy model the owner approved for Mod Bisect. It adds ONE new
  Mod Organizer 2 profile, "GG Squad - <your profile>" (numbered if taken), with a `gg-squad.json` marker, copies of your profile's own
  files, and a modlist with the host's switched-on mods that are installed here switched on in the host's order and everything else
  off. It asks first, only reads your own profile, never overwrites, never deletes (you remove it in MO2), and says that plugin order
  is not part of a code. A profile that keeps its own saves is allowed and the result says the copy starts without them.
- Still not built: 7z and rar installs (need an unpacking library in the build).
- Squad Sync shows a missing Mod Organizer 2 mod whose folder is already installed as "Installed, switched off", leaves it out of
  Get what's missing, and the Next line moves on to Make squad profile and then "pick the profile in Mod Organizer 2".
- Settings / Appearance: "Interface scale" is a real choice (100% native, 110%, 125%, 150%). It sets Qt's scale factor before the
  window is created, so the whole window grows evenly and no tab's layout changes; it is used at the next start and never overrides
  a QT_SCALE_FACTOR the user set themselves. Accent colour stays fixed.

Drivers & Startup (owner instruction, 2026-11-11: "somewhere where ever makes the most sense add a section that detects outdated
drivers and a way to update them all along with what starts up automatically when windows does so i can turn off unwanted apps
easily"). Placed as a third inner tab of Hardware, "Drivers & Startup" (`gg_desktop/upkeep_core.py` pure plus Windows calls,
`gg_desktop/upkeep_ui.py` Qt). Hardware is reopened for this tab only; Your PC and Upgrade Advisor are unchanged.
- Drivers: "update available" comes only from Windows Update's own driver search (Windows Update Agent, IsInstalled=0 and
  Type='Driver'), asked only when the owner presses Check. Update all / Update N selected installs exactly those update IDs through
  Windows Update in a separate PowerShell that Windows asks to allow (UAC, `run_elevated`); declining changes nothing. The result is
  read back per update (installed / failed / restart needed) and logged. "Oldest drivers" lists game-related classes older than 3 years
  as a hint, never as "outdated"; Windows' inbox 2006-06-21 drivers are left out. The graphics maker's official app page is linked
  (NVIDIA App, AMD Adrenalin, Intel DSA); nothing is downloaded from anywhere else.
- Startup: the same sources Task Manager lists (HKCU/HKLM Run, HKLM WOW6432Node Run, the user and common Startup folders), with
  publisher and description from the program file. The switch writes only Task Manager's StartupApproved value (02 on, 03 + time
  off), so entries and apps are never deleted and Task Manager shows the same state. Apps for you change directly; apps for all users
  ask first and go through the Windows prompt. Scheduled tasks, services and Store apps are not listed, and the tab says so.
- Nothing runs automatically: the startup list and installed drivers are read when the tab is first opened, Windows Update only on a
  press. Covered by `tests/test_upkeep.py` and the Drivers & Startup part of `tools/hardware_smoke.py`.
