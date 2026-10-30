# M4 usability and accessibility acceptance tests

**Status: engineering in progress, not signed off.** Repeat on a clean, disposable Game Grave installation under standard user privileges. Do not manipulate valuable saves or live mod-manager folders to test interface controls.

| ID | Scenario | Pass condition |
|---|---|---|
| M4-01 | Launch at 1920×1080, 1366×768 and 1280×720, each at 100/125/150/200% display scaling | Window opens inside visible desktop area, the main controls are not obscured by the taskbar |
| M4-02 | Tab and Shift+Tab through sidebar and page controls | Visible focus indicator, logical order and activation using Space/Enter |
| M4-03 | Ctrl+1..7 | Navigate Overview, Game DNA, Game Mods, Graveyard, Save Vault, Resurrection Lab and Undo Center; no cleanup occurs |
| M4-04 | F1 and Settings → Keyboard guide (F1) | Guide is readable and closable by keyboard; all shortcuts match actual behavior |
| M4-05 | F5 while idle and while a scan is running | One read-only scan starts; duplicate scan is not started |
| M4-06 | Escape during each scan stage, including just after completion is queued | Requests cancellation; no additional inventory stages run after the next checkpoint; any late completion result is discarded and previous accepted inventory is preserved |
| M4-07 | Escape with no active scan; Escape with a popup open | No unexpected destructive actions; appropriate popup closes |
| M4-08 | Game DNA visual map, Mod Radar guide and Resurrection Lab flow on narrow screen | Visuals adapt and the textual explanation remains readable |
| M4-09 | Keyboard-only operation at large Windows display/text size and light/dark themes | No focus trap or unreadable modal; color not sole way to know safe vs uncertain |
| M4-10 | Windows Narrator or NVDA (where available) | Navigation/button names can be discovered; failures recorded rather than silently considered supported |
| M4-11 | Scan a large disposable mod/launcher fixture and cancel | UI remains responsive, memory bounded, cancel honored |
| M4-12 | Repeat the same tasks on Windows 10 and Windows 11 | No missing controls or unsupported key events |

**Important limitations:** Automatically fitting the initial window inside the desktop does NOT prove every page is scrollable on small screens. Keyboard bindings and manual focus styling do not establish full screen-reader compatibility. Record any clipped controls, bad focus order, unreadable labels or slow scans as blockers for M4.

Report Windows build, Game Grave commit, display resolution/scale, task ID, observed versus expected, and a sanitized screenshot if useful. Attach results to [M4 issue #13](https://github.com/wrightausername/Game-Grave/issues/13). Before starting the **M6 closed beta**, M4 and the other pre-beta gates M1–M5 must be accepted. Use the identical participant questionnaire in [BETA_TEST_PROTOCOL.md](BETA_TEST_PROTOCOL.md).

### Cancellation regression evidence

Re-run cancellation tests after every scanner change. Cancellation is cooperative, not a guarantee of immediate interruption within a single slow third-party metadata call, so manual QA should record **cancel response latency** for each scanner and a large sample library. No canceled scan may overwrite the last accepted inventory, announce completion, start cleanup, or write successful scan history.

Automated tests exercise cancellation between every scan stage, late `scan_complete` events, and the difference between explicit cancel and an actual failed scan. These tests do not prove real Windows UI responsiveness at 100,000 mod entries.

## Scroll and compact-control verification

On 1280×720, 1366×768 and 1920×1080 at 100%, 125%, 150% and 200% scaling, verify the page scrollbar reaches the last action on every page, including Settings tabs, Game DNA, The Graveyard, Save Vault and Resurrection Lab. The mouse wheel over a page panel must scroll the outer page; over a Treeview it must scroll the **table**, without losing selection. Check page navigation resets outer scroll to top, keyboard focus remains visible and the Game DNA action buttons no longer clip on laptop-sized windows. The new scroll container is not proof of universal screen reader support. A UI automation test cannot substitute for interactive Win10/Win11 scaling verification.

## Large inventory rendering and pager accessibility

Use a wholly **synthetic** test library with at least 10,000 game-like records, 30,000 mod-root entries and 50,000 disposable old-file records. Confirm Steam Games, Other Launchers, Game Mods and Old Files each render **no more than 160 table rows per page** while preserving the full scan inventory. The **Previous / Next** buttons and total count must remain keyboard reachable, move forward/back without skipping data, and disable appropriately on the first/last page.

Search or source filtering must reset to a valid page; changing sort order must not silently remove data. Each page must preserve the correct object-to-row lookup. For **Old Files**, protection checks, confirmation and Recycle Bin preflight still apply to every selected item; **Select all shown** means the current page only. No background cleanup or deletion authorization is enabled by paging.

Measure first-page rendering, filtering and page-change latency on Windows 10 and 11 with DPI 100–200%, and test F1 keyboard navigation and Narrator/NVDA announcements for the pager label. A synthetic unit test proves bounded insertion, **not** an interactive latency benchmark. Large library scans still need representative hardware timing and cancellation checks.

## Short-screen sidebar navigation

At 1280×720 and 1366×768, with normal and large text, verify **all** navigation destinations remain accessible via the new sidebar scrollbar: Overview through Settings in Simple mode, plus Storage History and Automation in Advanced mode. Mouse wheel over the sidebar should scroll the nav list, not the Game DNA/Graveyard content. Ctrl+1..7 should visibly reveal the focused destination in the sidebar even when it is below the fold. Test navigation solely by Tab/Shift+Tab, arrow keys in the scrollbar, mouse wheel and using the direct Ctrl shortcuts. The bottom edition/safety reminder stays visible. Record missing or clipped buttons and focus indicators as M4 defects; automated unit tests simulate the scroll routing but cannot certify Narrator/NVDA.
