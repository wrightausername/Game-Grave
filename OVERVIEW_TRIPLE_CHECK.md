Overview full-control verification, preview 0.2.12

The owner requested a triple check of the actions a person would click.
Overview is the only active tab; its normal 0.2.10 dashboard foundation and
the locked Ready Room/all other tabs remain protected.

The expanded matrix uses actual Qt mouse/keyboard events and verifies resulting
navigation, selection, state and saved preferences. It runs 66 journeys in
three fresh processes, producing a case-level JSON report. Native Windows
repeats the same runs. This is an agent-run interaction check, not a recruited
participant study or a test on the owner's PC.

Coverage includes all five metrics, seven navigation/review links, game artwork,
the storage Inspect button, all fifteen legend targets (dot, label, value),
Help/status, activity/history, Ctrl+K and the actual search-clear button, Tab and
Enter through each category, keyboard metric activation, hero/quick/F5 scans,
duplicate-scan protection, cancellation, the busy-window Close guard, storage
folder dispatch/refresh/selection/paging beyond 200 findings, library paging,
favorite persistence in real preference files and a fresh window, failed saves,
scan-location Save/Cancel/add/remove/rejection, maximize/restore/minimize,
closing during measurement, and message-style isolation after leaving Overview.

The expanded check found and fixed these missed cases:

| Finding | Overview fix |
| --- | --- |
| Legend dots were inactive | Dot, label, value and row whitespace share the category action; each category has one keyboard stop |
| Help/status/error messages had a pale background behind pale text | Only messages owned by the current Overview window receive the local readable style |
| Closing the app left the measurement worker running | An accepted Overview close cancels its worker and prevents late UI updates; the existing busy-scan Close guard is retained |
| Remove Selected was active without a selection | Enable it only for a selected folder while edits are allowed |
| Favorites were saved but lost after restart because the shared loader filters extra keys | Overview restores its saved favorite preference through a bounded read-only adapter, preserves it on scan-location saves and passes the restored state to game details |

The shared loader, data/cleanup/recovery engines, styles, navigation and locked
tab source are unchanged. The preference adapter checks ordinary paths,
size limits, duplicate keys and types. Five pure regression tests cover real
save/restore, session precedence, invalid data, oversized and redirected files.

The full suite contains 519 tests (one platform skip locally). Existing
Overview/human functionality checks and all 78 image comparisons remain in the
Windows workflow, alongside packaging, launch and isolated install/uninstall.
OS folder-opening calls are checked at their dispatch boundary; game launches,
cleanup and automatic network calls are prevented during the interaction checks.

Overview remains pending owner signoff. No other tab is reopened by this work.
