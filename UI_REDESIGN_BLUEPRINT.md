# Game Grave UI rebuild: Crimson Command (approved visual direction)

**Status:** Approved implementation blueprint, **not implemented yet**. Written 2026-10-31. This is the binding visual and interaction specification for the red-and-cyan cinematic **Overview** mockup chosen by the owner on 2026-10-31. Reuse the current Game Grave backend; do **not** ship a static image pretending to be a working UI. Do not change `release_gate_status.json` or declare 1.0 stable based on this blueprint.

**Product goals:** Stunning, gaming-aware Windows desktop experience that is also clear to nontechnical users; one unified **Games** list across launchers; full, understandable control over **personal** Graveyard protection without weakening built-in protection; authentic numbers; local-first operation; no subscriptions or hidden file deletion.

## 1. Decisions locked

1. **Look:** near-black/charcoal gaming HUD with a cinematic crimson hero, subtle electric-cyan storage graphics, restrained red emphasis, bright readable text, thin panel borders, purposeful icons and tasteful depth. The selected Overview mockup is the direction; its sample statistics, invented artwork, screen contents, game artwork and wording are *illustrative*, not measured facts or production assets.
2. **Navigation:** Overview, **Games**, Mods, Old Files, Graveyard, Game DNA, Undo Center, Settings. Keep Save Vault, Resurrection Lab, Automation, Make Room, history and support functionality accessible via a clearly labeled Tools/More panel or contextual destinations, not deleted. Keep screen names plain English and route any legacy Steam Games/Other Launchers deep links to **Games** with an appropriate filter.
3. **Games = detected installed games across supported launchers** (Steam, Epic, GOG, EA, Battle.net/Blizzard, Ubisoft, Xbox/Microsoft Store where reliable, Riot, Rockstar and verified custom libraries). All supported sources appear in the **same searchable/sortable list**. No promise of full detection for vendors without confirmed local evidence. Display `Unknown` rather than inventing installation, last-play dates or size.
4. **Graveyard inline protection action:** exact user-added Never Touch file rules can be removed from the **selected row/detail panel** after confirmation. Inherited user folder rules link straight to the relevant Settings rule; no hidden mass unprotect. Built-in system, installed game, live mod, save, symlink/junction and manager protection is **not overrideable** by the Graveyard; explain why and offer the appropriate source/manager action.
5. **Recycle Bin only**, each file remains subject to a separate explicit deletion confirmation and existing file identity, ownership, recovery canary and Undo checks. **No permanent-delete button.** Screenshot images are only eligible after user-triggered, individual content preview plus consent; never mass-select screenshots.
6. **Metrics cannot lie:** `moved to Recycle Bin` ≠ `disk space reclaimed`. Show confirmed reclaimed bytes only if a trustworthy measurement supports them; otherwise show `Moved to Recycle Bin` or `Potentially reviewable size`, with a nonmisleading tooltip. Never count an entire installed game as `safe to remove`.
7. **No cloud asset loading / background telemetry.** Artwork, icons, fonts and textures are local; use original rights-cleared hero art. Screenshot previews remain opt-in, local and bounded. Preserve Free, Undo Center and readable history. All original M1–M7 1.0 acceptance gates remain separate.

## 2. Technical approach and migration boundaries

### Choice: PySide6 Qt Widgets for the new premium presentation, with the existing Tkinter app intact as the fallback

The existing `ui.py` is approximately 4.3k lines and owns navigation, layouts, callbacks and asynchronous scan result handling. However, business logic already lives in reusable modules: `core.py` (Steam, settings, safety, Recycle Bin), `launchers.py` (other launcher evidence), `graveyard.py`, `graveyard_protection.py`, `cleanup_actions.py`, `game_intelligence.py`, `view_options.py`, `recovery.py`, `screenshots.py`, `screenshot_preview.py`, Resurrection Kit modules and licensing. **None of those modules should be rewritten to produce the cosmetic redesign.**

Use **Qt Widgets + Qt Style Sheets (QSS) + QtGui/QPainter** for custom progress rings and other charts, and local SVG/PNG artwork. Use QObject/Signal and QRunnable/QThreadPool for nonblocking worker updates; only the Qt main thread may touch widgets. Start with a separate `gg_desktop` package and an explicit developer preview entry point so the existing Tk UI and its tests continue passing. Do not import Qt into scanner modules. Prefer Qt built-in widgets/QtGui for charts over pulling in GPL-only or large add-on modules.

**Legal/build gate:** PySide6/Qt is dual-licensed and commercial distribution under LGPLv3 has compliance obligations (and some modules are GPL-only). Before choosing the production packaging model, review the exact pinned dependency versions, Qt license obligations, redistribution of Qt DLLs, replacement/relinking requirements, third-party assets and the intended proprietary lifetime-Pro business. A Qt commercial license is an alternative; no conclusion of legal clearance is implied here. Official references: https://doc.qt.io/QT-6/licensing.html and https://www.qt.io/development/open-source-lgpl-obligations. Do not use optional GPL-only modules without a reviewed licensing path.

**Fail-safe startup strategy:** `launcher.py` continues booting legacy Tk by default until the feature parity and Windows QA gates below are accepted. A clearly distinct opt-in `python -m gg_desktop --ui-preview` launches the Qt shell against *read-only test fixtures* first, then actual read-only inventories, then approved backend actions behind reviewed feature flags. Old preferences must survive switching UI versions. Never publish a Windows installer pointing at a half-finished shell.

### Intended source structure

```text
gg_desktop/
  __init__.py
  __main__.py                    # preview entry point; no scan at import
  app.py                         # QApplication, high-DPI, error boundary, shell
  theme/
    tokens.py                    # semantic colors, typography, radii, spacing
    styles.qss                   # focus, button, table, chips, hover/disabled
    assets/                      # LOCAL original hero art, icons, app emblem
  components/
    nav_rail.py                  # responsive navigation; readable focus
    hero_banner.py               # cinematic art, contrast overlays
    cards.py                     # metric, action, media, info, alert cards
    buttons.py                   # primary, neutral, caution, destructive
    chips.py                     # launcher, state, filter chips
    storage_ring.py              # QPainter; quantities from evidence only
    launcher_bar.py              # categorized storage with unknown handling
    item_row.py                  # virtualized rows; keyboard selection
    image_preview.py             # user-requested thumbnail; bounded decoder
    modals.py                    # confirmations and irreversible warnings
    states.py                    # loading, empty, partial, error, canceled
  models/
    game_record.py               # normalized Steam + launcher read model
    graveyard_row.py             # safe display/action availability
    overview_metrics.py          # computed provenance-safe metrics
  adapters/
    library.py                   # existing find_games / find_launcher_games
    cleanup.py                   # existing rules; NO new delete implementation
    inventory.py                 # maps Graveyard, DNA, captures, activities
    operations.py                # asynchronous task adapter and cancel
  pages/
    overview.py
    games.py
    graveyard.py
    game_dna.py
    mods.py
    old_files.py
    undo_center.py
    settings.py
    tools.py                     # existing advanced features remain reachable
tests/
  test_gg_ui_tokens.py
  test_gg_games_unified_model.py
  test_gg_protection_flow.py
  test_gg_overview_metrics.py
  test_gg_ui_read_only.py
tools/
  windows_gg_ui_smoke.py         # ephemeral Windows GUI screenshot/navigation
```

New files are **proposed paths**, not a claim they already exist. Every view model must be serializable/simple and testable without Qt. Use an adapter boundary rather than calling `os.startfile`, Recycle Bin or scanning APIs directly from widgets. Existing backend contracts stay authoritative.

## 3. Visual design system, specified in device-independent pixels

| Token | Initial value | Use |
|---|---|---|
| `surface.canvas` | `#080B11` | Window background |
| `surface.sidebar` | `#0B1018` | Navigation rail |
| `surface.panel` | `#101720` | Main cards |
| `surface.raised` | `#17212C` | Interactive hover/row |
| `border.subtle` | `#263440` | 1px card separators |
| `text.primary` | `#F5F7FB` | Headers / values |
| `text.secondary` | `#A3B0BF` | Help text |
| `accent.crimson` | `#FF4055` | Brand / urgent actions |
| `accent.cyan` | `#40CFF4` | Graphs / data focus |
| `state.good` | `#65D7A3` | Confirmed completion |
| `state.caution` | `#FFCB80` | Protected / unknown |
| `state.danger` | `#FF5469` | Deletion, always confirmation |

These are design starting tokens, not final accessibility certification. Font: **Segoe UI Variable** where installed, fallback Segoe UI and system sans; no bundled proprietary font files. 14–15px body, 12–13px metadata, 20–24px card headings, 30–34px page headline, 36px key stat maximum. Spacing scale 4/8/12/16/24/32; default card padding 16–20; corner radii 8/12/16; sidebar width ~220–244; button minimum hit target 40x40; focus outline clearly visible in keyboard navigation.

**Rules:** Crimson for identity and explicit risky action; cyan for analytics and link highlights. No glowing border on every card. Hero imagery must not sit directly behind unshadowed text; use dark overlays and text contrast checks. No neon red paragraph text. Icons use one coherent local SVG set. Stock game cover art is not bundled absent redistribution rights; fall back to title + launcher monogram or local metadata.

**Responsive:** reference canvas about 1440x900; usable 1366x768 and 1280x720 without clipping. At smaller viewport collapse three-column overview to two columns then one column with page scroll; never compress controls below legible size. Test Windows DPI 100/125/150/200%; typography and controls scale using Qt's DPI handling. Support system text scaling, high-contrast override and reduced animation.

**Motion:** 120–180ms unobtrusive hover/focus/section transitions; no motion on every progress tick; disabled under reduced-motion setting or remote/low-resource mode. Prefer no animation to jitter.

## 4. Component contracts

| Component | Properties / data | Required interaction / states |
|---|---|---|
| `GameGraveShell` | active route, global scan state | Sidebar keyboard shortcuts, Ctrl+F search, F5 scan, Esc cancel; keep tools accessible |
| `HeroBanner` | local original image, heading, scan status | Contrast overlay, fallback gradient when art absent, never cover the scan cancel control |
| `ActionCard` | icon, title, description, route, enabled | Scan, Review Graveyard, Undo Center, Settings; focus, hover, disabled, loading |
| `MetricCard` | value, unit, evidence source, confidence | `Not scanned`, `Unknown`, exact, approximate, error; tooltip explains counting |
| `StorageRing` | drive capacity, used/free verified bytes | No fabricated split; no double-count, units and keyboard-readable text alternative |
| `LauncherRow` | provider, verified known bytes, game count | Opens Games with launcher filter; unsupported/unknown sizes not shown as zero |
| `FindingRow` | category, path label, age, evidence, protection | Open detail, optional preview, no destructive quick gesture |
| `GraveyardRow` | category, is_selected, protection kind, allowed actions | Inline `Unprotect` only for exact personal rule; otherwise explain/route to Settings or manager |
| `ReviewQueue` | explicitly reviewable findings, bounded page | Check eligible never selects screenshot, protected mod, active install or saves |
| `ScreenshotCard` | local metadata and optional user-selected image | Read bytes only after user clicks Preview; no uploads or automatic cached thumbnails |
| `StatusChip` | semantic code not user-supplied arbitrary color | `Protected`, `Needs review`, `Ready for individual review`, `Moved to Recycle Bin` |
| `ConfirmationDialog` | exact files, total *apparent* bytes, action, risk | Explicit confirm; no prechecked destructive action, cancel is default |
| `EmptyState` | reason, next safe action | Not scanned, no supported games, no old screenshots, no permissions, search yields none |
| `ActivityToast` | status and next action | Completion is only reported after backend confirms; Undo link when supported |

**Every control must have a real handler and accessible label.** No dummy buttons or aspirational charts. Placeholder metrics are allowed only in an isolated fixture/design preview visibly labeled **DEMO**, never in a production install.

## 5. Overview: exact screen layout and data rules

**Hero band (~one fifth of top viewport):** local cinematic red-moon/hooded ruin art, `YOUR GAMES. A CLEANER TOMORROW.`; small honest subtitle; compact *last scan status* and global `Scan PC` / `Cancel scan` control. Avoid pretending red hero artwork represents a current game.

**Action strip:** four equal action tiles, `Scan PC`, `Review Graveyard`, `Undo Center`, `Quick Settings`. All clickable via mouse and keyboard. When scanning, display truthful stage/progress and explicit Cancel, not fake ETA.

**Primary dashboard grid:**
- **Storage Overview:** drive selector; QPainter donut for OS-reported used/free; known game bytes when reliably measured; remaining bytes `Other/Unclassified` with explicit disclaimer; no sum > drive capacity; no double-counted Steam copies, mods within game installation or multiple launchers. Show `Reclaimed` only if separately verified; otherwise `Sent to Recycle Bin: X bytes` and explain not freed yet.
- **Launchers:** Steam, Epic Games, EA, Battle.net, GOG, Ubisoft, Xbox, Riot and supported sources; bars for measured or explicitly labeled reported sizes, unknowns marked rather than made-up zero; tapping filters Games.
- **Recent Findings:** most recent verified scan findings from local inventory, sorted by detection time if actually recorded or otherwise clearly labeled `Found in last scan`. Never imply an actual play date from file modification.
- **Latest Screenshot:** filename/date placeholder or optional local preview button for detected capture; do not decode without user action; `View all` opens filtered Graveyard.
- **Graveyard Review Queue:** up to four actual findings selected by criteria; protective wording; `Review` opens Graveyard, not implicit bulk deletion.
- **Needs Review:** one evidence-backed uncertain item with reason e.g. `Mod manager ownership unknown`; no `safe to remove` message absent verified individual evidence.

**States:** unscanned tutorial; scanning progress + cancel; completed with findings; empty clean PC; partial failure/permissions; canceled scan retains last accepted inventory; offline has no effect on local scanning.

## 6. Games: one unified library across launchers

Current `ui.py` `_games_page` only renders `self.games: list[SteamGame]`, and `_other_launchers_page` separately renders `self.other_games: list[LauncherGame]`. **Replace that separation in the new UI.**

**Presentation-only normalized record:**

```python
@dataclass(frozen=True)
class GameRecord:
    key: str                  # launcher + verified app_id + canonical install path
    name: str
    launcher: str             # Steam / Epic Games / EA / Battle.net / GOG...
    app_id: str | None
    install_path: str
    install_evidence: str     # manifest / registry / user-selected verified library
    size_bytes: int | None   # None = unknown; not 0
    size_source: str         # measured / launcher-reported / unknown
    last_played_at: float | None
    last_played_source: str  # Steam account record or Unknown
    status: str              # verified installed / partial / uncertain
    capabilities: tuple[str, ...]   # open_folder, supported_uninstall_uri, inspect
```

The adapter maps `SteamGame` and `LauncherGame` into this model. Deduplicate only when install identity + provider evidence really match; distinct installations in separate folders remain separate. Two providers claiming one path become a single display candidate with **ambiguous ownership** and both sources visible, not two full disk-size charges. Never collapse by title alone; multiple editions and shared games exist.

**Layout:** `All Games` header; search; launcher filter chips `All / Steam / Epic / EA / Battle.net / GOG / Ubisoft / Xbox / Other`, each showing **observed** counts; list/grid toggle; sort by size, last played (Unknown last), name, launcher; game rows with local placeholder cover, game title, provider, size, verified/unknown last play, and explicit safe action menu. A right summary card shows total *known* bytes plus unknown-size count and top large games.

**Actions:**
- `Open folder`: only validated present ordinary install directory.
- `Uninstall`: only launch the **verified corresponding launcher mechanism** after user approval; retain Steam's existing `steam://uninstall/<app_id>`; do not invent `EA`/`Battle.net` uninstall URIs.
- `Find related files`: Game DNA / Graveyard review, no auto-delete.
- `Clear shader cache`: Steam-only when exact existing per-app safeguards pass; hide/disable on other launchers with reason.
- `Refresh`: read-only scan; cancelable and nonblocking.

Use `Unknown` for unsupported EA/Blizzard play history and uncertain launcher-reported sizes. An incomplete vendor registry is not proof of zero games. **The contract is all games Game Grave can reliably detect, not an invented guarantee of every game from every launcher.**

## 7. Graveyard: the essential protection fix

**Three protection tiers**, never conflated:

| Tier | Example | In-row action | Safety |
|---|---|---|---|
| **Exact personal Never Touch rule** | User individually protected `some-old-archive.zip` | `Unprotect` directly on selected row and details panel, confirmation explains this one file only | Remove only exact user rule with existing `set_item_protection`. Rebuild inventory, revalidate before later deletion |
| **Inherited user folder rule** | Parent `D:/MyBackups` protected, child selected | `Manage parent rule` opens Settings at this exact Never Touch entry | Never silently unprotect all siblings; user changes folder-wide rule separately |
| **Built-in / managed / system / active game / save** | Installed game tree, MO2 active profile, Steam library, Windows | `Why protected?` / `Open manager` (when verified) | Cannot override directly from Graveyard, cannot recycle whole protected game/mod folder |

**Direct user flow:** click Protected row → right-side `Why protected` detail → `Unprotect this item` if and only if exact personal rule → confirmation naming file and spelling out *no deletion happens yet* → remove exact rule → row becomes `Reviewable` if still otherwise eligible → **separate** `Move to Recycle Bin...` approval → existing `recycle_reviewed_entries` worker checks eligibility again, canary, identity and registration. Never combine Unprotect + Delete into one click.

For plain old archives/recordings, allow safe batch selection but cap batch size and show every selected filename/total. `Select eligible` skips protected items, screenshots, active mods, saves and incomplete ownership. For screenshots, open local bounded preview, then confirm **that exact image**, one at a time. Unsupported/missing/changed sources stay protected. No red `Delete permanently` button anywhere.

**Required implementation changes:** create display-level `ProtectionDecision` from `graveyard_protection.protection_action`, return kind/reason/allowed next action; keep existing core's built-in rule as the final authority. Row action needs no manual trip to Settings for exact personal protection. Handle partial UI refresh without losing user selection. `_grave_toggle_protection` behavior can be reused through adapter, but do **not** copy Tk callbacks into Qt. Inherited protection needs a well-defined settings deep-link.

## 8. Game DNA and rest of product

**Game DNA:** use `build_game_dna` as the authority and render a simple relationship diagram: Installed Game, Mods, Saves, Recordings, Screenshots and possible Leftovers. Each connection needs confidence provenance: `Known`, `Possible`, or `Unknown`. Actual sizes only where evidence exists. Never say `safe to clean` merely because `90 days` elapsed or a mod marker was not recognized. Diagram nodes drill down to related item details, not deletion.

**Mods:** Mod Radar evidence cards, owner confidence, manager and source badges, active/unknown protection, `View in manager`, `Send for review` only. No blanket deletion. Large row inventories remain paginated/virtualized.

**Old Files:** original root picker, age filter, honest apparent size, read-only scan, per-file approval and Recycle Bin. Existing original-scope checks remain enforced.

**Undo Center:** verified Windows recovery status, recoverable vs not found vs Recycle Bin emptied, restore operation and logs. Cannot promise to restore what Windows no longer holds.

**Settings/Tools:** preserve Never Touch, screenshot/capture roots, Free/lifetime-Pro state, privacy, user themes, safety diagnostic, optional scan settings, resurrection/Save Vault, advanced views and updates. Appearance includes a default Crimson Command theme and non-crimson accessible alternatives, respecting existing user appearance preferences during migration.

## 9. UI states and transitions (mandatory)

- App launch → no automatic metadata read or network request unless the saved opt-in scan-on-launch setting is enabled.
- `Not scanned` → Scan (read-only) → `Scanning/Cancel` → `Success` or `Partial` or `Canceled`. Cancel must not overwrite the last accepted scan.
- User selects Graveyard entry → populate right panel without filesystem writes.
- `Protected by me` → user confirms unprotect → exact personal rule removed → refresh → `Reviewable` if otherwise safe → *separate* approved Recycle Bin operation → `Recycled/Undo available` or `Skipped`.
- `Protected by parent` → settings deep-link → explicit parent rule edit → refresh; no automatic child override.
- `Protected by app` → explanation; delete disabled.
- Screenshot row → `Preview image` → local bounded decoder → user chooses Keep or separate per-image deletion workflow; no batch eligibility.
- File moved/changed between scan, unprotect, preview and deletion → revalidate → `Changed: rescan`; no retry as permanent delete.
- Any worker error → neutral specific human-readable error, old app/inventory still usable; never claim reclaimed bytes on failure.

## 10. Implementation PR order and exact acceptance

### UI-0. Freeze this contract
**Output:** this document + task checklist + a local rights-cleared original hero asset plan. Record reference appearance without bundling arbitrary copyrighted game cover art. **Acceptance:** safety rules and all routes understood; existing data backend and old Tk startup unchanged.

### UI-1. Theme, component library and new shell
**Output:** `gg_desktop/theme`, navigation rail, desktop window, hero banner, action card, panel, button, status chip, local icons, placeholder/empty-state components, opt-in preview entry point. **Acceptance:** screenshot-visible mock layout at 1440x900 plus 1366x768 and 1280x720; keyboard focus; 100/125/150/200 DPI; only **DEMO** fixture data and all actions harmless or real safe navigation; Tk application unaffected.

### UI-2. Wire Overview to real read-only state
**Output:** `OverviewMetrics` adapter, disk chart, launchers, recent findings, review queue, no-fake-screenshot policy, real Scan/Cancel events. **Acceptance:** empty/partial/offline/error/cancel tests, storage totals reconcile, no invented reclaimed-space metrics or automatic screenshot content reads; no UI freeze.

### UI-3. Ship unified Games
**Output:** `GameRecord` normalization, launcher filters, virtualization, sort, search, context actions, route aliases. **Acceptance:** Steam+Epic+GOG and vendor fixtures appear in **one** list; unknown play date/size never fabricated; no duplicate storage accounting; Steam-only uninstall route never used for EA/Battle.net/etc; optional unsupported vendor warning.

### UI-4. Deliver the Graveyard inline unprotect fix
**Output:** protection detail, per-row action, row refresh, settings deep-link, screenshot preview, risk dialogs and existing background cleanup integration. **Acceptance:** exact personal rule removable directly without deleting; parent rule not removed automatically; built-in protection unoverrideable; check-all skips protected/screenshots; worker refuses changed/linked/hardlinked or manager data; Undo records checked; no permanent fallback.

### UI-5. Game DNA, Mods, Old Files and remaining screens
**Output:** visual evidence breakdown, protected/uncertain explanations, preserved legacy advanced functionality under Tools; Undo Center, Save Vault/Resurrection Lab, Settings, Automation and history are still reachable. **Acceptance:** no feature regression from previous Tk app; each original backend action has explicit verified Qt adapter or legacy fallback; zero dead controls.

### UI-6. Polish, accessibility, Windows performance and package gate
**Output:** consistent hover/focus, transitions, empty/skeleton/error states, original hero art, icons, installer bundling, user guide and QA report. **Acceptance:** keyboard-only critical flows and Narrator/manual acceptance; physical consumer Windows 10/11 at 100/125/150/200% including narrow laptop; large library memory and cancellation budgets; clean installer/upgrade/uninstall; Free/Pro and licensing behavior unchanged; no privacy/asset/Qt license blockers. Keep old Tk entry point if any gate fails.

### UI-7. Controlled switch, never premature 1.0
After feature parity, safety and packaging sign-off, update default `launcher.py` to the new UI and retain a rollback switch for one release cycle. The **M1–M7** ledger remains authoritative. Owner-selected closed beta retains the *same frozen questionnaire*. No UI PR changes `release_gate_status.json` automatically.

## 11. Visual acceptance test grid

| Test fixture or viewport | Must be visible/true |
|---|---|
| 1440x900, 100% | Hero/action strip + three-column dashboard resemble reference; typography readable |
| 1366x768, 125% | Sidebar all routes reachable, page scroll, cards never overlap or truncate primary actions |
| 1280x720, 150% | Dashboard reflows; Undo and Cancel reachable |
| Windows 200% text/DPI | No 7px text, clipped confirmations, inaccessible delete warnings or overlapping panels |
| 0 games, first launch | `Not scanned` prompts; chart and launcher summaries do not invent data |
| Steam 4, Epic 3, GOG 2, EA 1 | Unified Games shows 10 *verified* separate installations if no shared paths |
| Duplicate same install claimed twice | One displayed path/ambiguous source and no doubled capacity |
| Unsupported Blizzard play-history | `Unknown`, not guessed idle duration |
| Manually protected `old.zip` | Inline `Unprotect` → confirm → reviewable; NO auto-delete |
| Protected parent with 300 files | Child row says `Manage parent rule`; never drops entire parent rule |
| Active MO2 profile | Built-in protected; no override or recycle path |
| Screenshot in Steam `userdata/760/remote` | Found by metadata, protected from bulk; local preview before individual approval |
| Recycle unavailable or canary fails | Skip, no deletion, accurate error and preserved source |
| Cancel scan / modal / window | No inconsistent half-applied results, no crash, no worker UI-thread widget calls |
| Recycle Bin still holds moved files | `Reclaimed space` stays zero/unverified; show moved-byte value only |
| Qt shell fails to start | Existing Tk product still starts; no settings or user data lost |
| Offline + no Pro activation | Free features including Undo remain available and no unsolicited network call |

## 12. Definition of done for the visual project

- Close visual gap against the approved crimson Overview at 1440x900 without sacrificing 720p laptop legibility.
- No `Steam Games` *as the primary navigational item*: `Games` is unified and filterable.
- A user can unprotect an exact **personal** Graveyard rule **right there** and separately decide whether to recycle that file.
- Built-in protection and manager/backup guards remain mandatory; there is no permanent-delete shortcut.
- Every screen has a usable no-data state, loading state, error state, cancel/escape path, and keyboard accessibility.
- All existing Free, lifetime-Pro, Resurrection Kit, Graveyard, Save Vault and undo capabilities survive.
- Windows preview/install CI and human interaction checks have evidence attached; license/asset obligations reviewed.
- This completion does **not** mark Game Grave 1.0 stable. The product release requires all independent gates in `RELEASE_1_0_PLAN.md`.

**First coding task after approving this blueprint:** UI-1 component theme + shell, behind an opt-in preview entry point. Keep the old app as fallback until UI-6 has passed.
