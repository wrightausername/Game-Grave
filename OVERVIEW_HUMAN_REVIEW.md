Overview click-through review, preview 0.2.11

The owner authorized reviewing how someone would use Overview and implementing
the resulting fixes. The dashboard foundation is preview 0.2.10, source
8733e55505e1500c74646e540fcd2f7ba565ec0f. Ready Room and all other tabs remain
locked. This is an agent cognitive walkthrough with actual mouse/keyboard
events, not a study with recruited human participants.

| User goal and expected behavior | Observed in 0.2.10 | Implemented in Overview |
| --- | --- | --- |
| Click Mods on the chart to inspect mod storage | Every slice opened All categories | Category is resolved from the actual clicked arc; center/keyboard opens the full breakdown |
| Read the storage, search, locations and activity dialogs | Default light dialog backgrounds made the light text nearly unreadable | Overview-owned dark dialog background; shared styles remain unchanged |
| Select a storage row and press Enter | No inspection occurred | Native item activation opens the selected location once; double-click works too |
| Filter storage, then press Enter | No deliberate keyboard path to matching rows | Enter selects the first match and focuses the table; refresh is never an implicit default action |
| Type a mod name into the global search | Game shelf became blank with no explanation | Search feedback explains the matching-game count and Enter-to-search-all action; clearing search restores the shelf |
| Choose between two installations with the same name | Result captions did not show which installation was selected | The selected folder is displayed before opening the exact game record |
| Stop storage measurement after the inventory scan | The dashboard Cancel button disappeared while measurement was still running | The existing Cancel control remains visible, distinguishes the two phases and retains previous totals on cancellation |
| Close a dialog or abandon a search | Requires predictable keyboard behavior | Escape/Close dismiss; disabled selection actions and explicit empty-results feedback are checked |

The default dashboard's layout, artwork and typography are unchanged. A new
six-image comparison protects its empty/populated states at three sizes against
0.2.10, alongside the existing 72 comparisons protecting the twelve other tabs
against the approved Ready Room baseline. Dialogs fit the available screen;
their action row can wrap. No storage-accounting, game/mod data, cleanup,
protection or recovery engine is changed.

`tools/overview_human_walkthrough.py` verifies ten goal-based journeys using
real Qt mouse clicks, double-clicks, typing, Return and Escape. It records
expected user behavior and results in `overview-human-journeys.json`, and
captures the dialogs and default dashboard. The Windows workflow repeats these
checks in native Qt and packages the EXE/installer as 0.2.11.

Local desktop diagnostics: the selected managed environment is
`ccarenv_b64_Y2NhcmVudl80OWM5NjRiYzM2YjQ4MTkxYmUxNTVlYmI4MDIwZmQyNA`.
Its status reported remote desktop enabled with state `unknown`; neither
`cua_repl.js` nor `open_in_codex` was exposed, and DISPLAY was unset. Linux
verification therefore uses actual Qt widgets on the offscreen platform;
the native Windows workflow supplies the platform-specific validation.

Overview remains pending owner signoff. This review does not authorize moving
to another tab or reopening a locked one.
