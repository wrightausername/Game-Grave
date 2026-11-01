# Game Grave / Crimson Command — Implementation Specification

**Revision:** 2026-11-01 · Engineering acceptance contract · Source of truth for PR #86  
**Status legend:** **Implemented** in development source is not the same as **QA accepted** or released.

## 0. Non-negotiable requirements

- Only real read-only scan results may populate application data. Concept/mockup statistics and game posters must never ship as customer facts.
- No unconfirmed cleanup. Saves, installed games, active mods and personal folders are protected; all destructive actions require explicit approval, per-item identity checks, and Windows Recycle Bin / Undo verification.
- Core app must never measurably lower game FPS or 1% lows: no overlays/injection, no always-on scans, yielding foreground-game detection, low-priority disk/CPU work. Verify on physical Windows hardware, not just GitHub Actions.
- Graphics and screen composition must be tested against **approved image references**, not merely launch and widget-existence tests.
- Design intent: a distinctive **crafted game archivist's command center**, not a uniform grid of generic dashboard cards.

## 1. Route navigation contract

**Implemented in** `gg_desktop/app.py`, `gg_desktop/theme.py`.

- A persistent, high-contrast **← BACK** button, a readable `Previous / Current` breadcrumb ribbon, and a **READY ROOM** home control are visible above the scrolling content on every tab.
- Clicking a different route pushes the current route onto a bounded back stack (maximum 40). Opening the same route or refreshing a scan does **not** push a duplicate.
- Back pops exactly one route without immediately putting the route being left back onto the stack. Alt+Left performs the same action.
- When there is no history, Back is disabled. Ready Room home control is disabled while already there.
- The local AI companion is not a route and does not contaminate history. Existing screenshots/video aliases resolve into Captures with the correct subtab.
- Follow-on refinement: add intra-tab breadcrumb segments for modal drill-down/details once actual nested route identifiers exist, not fake depth labels.

**Acceptance:** back through `Overview → Games → Mods → Other Storage` gives Mods, Games, Overview; every screen stays navigable with keyboard.

## 2. Cross-launcher game discovery / RDR2

**Implemented in** `game_signatures.py`, `launchers.py`, `gg_desktop/models.py`, and `gg_desktop/screens.py`.

1. **First-party evidence:** existing Steam appmanifest/library records, Epic `*.item` manifests, GOG registry, Riot product settings, EA/Ubisoft game keys, and verified Battle.net uninstall registrations.
2. **Rockstar evidence:** known Rockstar game registry subkeys under Windows HKLM/HKCU, 32/64-bit views; bounded fields such as `InstallFolder`, `InstallFolderEpic`, `InstallLocation`, `InstallDir`; plus exact standard Rockstar install directories. Accept only a normal existing folder containing an actual known game-specific executable.
3. **Selective Windows installed-game registry fallback:** trusted game publishers plus actual known executable at `InstallLocation`; no blanket acceptance of all installed applications.
4. **Explicit custom library fallback:** Games → **+ ADD GAME FOLDER…**. Scan only the selected directory and immediate child directories, max 15 roots and 400 children per root. Recognize exact known game executables and keep unknown folders labeled unverified. Never recursively crawl all disks.
5. **RDR2 signature:** `RDR2.exe` or `PlayRDR2.exe` in a validated install root; Steam AppID **1174180** and Epic manifests remain separate, independent evidence. Presence of the executable does **not** prove a license, working launcher authentication, ability to launch, or safe removal.
6. **Corroborating data:** Rockstar service registration and local executable evidence must not turn a single Steam or Epic install into a falsely ambiguous duplicate. Truly conflicting Steam/Epic install claims remain ambiguous.
7. **Additional exact executable signatures:** GTA V, GTA IV, L.A. Noire, Max Payne 3, Cyberpunk 2077, Skyrim SE, Fallout 4, Starfield, Elden Ring, Baldur's Gate 3, The Witcher 3, Hogwarts Legacy. Catalog expansions must use verified exact paths and regression cases.

**Important scope limit:** Microsoft Store/Xbox packaged app enumeration and Amazon Games native database support are not asserted as implemented by this change. Some locked installations and launcher-specific encryption cannot be inspected. Surface unavailable evidence rather than inventing coverage.

**Acceptance:** RDR2 in the Rockstar registry + exe appears; missing exe does not; Steam and Rockstar agreeing on the same root display once; manually added game folder is scanned on next explicit scan; no user saves or unrelated executables opened or deleted.

## 3. Page structure and UI data contracts

| Page | Primary workspace | Supporting workspace | What must remain factual |
|---|---|---|---|
| **Mods** | 5-column (when space allows) real game-cover / mod-source grid and source filters | Right-hand Mod Radar inspector with review actions | No invented orphan/conflict/update counts |
| **Old Files** | Five metadata category tiles, searchable selection ledger | Age diagram + cleanup insights + quick actions | Age means modified time, not last used; no reclaim guarantee |
| **Other Storage** | Chosen-drive overview, clear Quick/Full scan controls, large categorized breakdown | Top folders, evidence/scope, browse path | Unknown/inaccessible bytes are labeled, never rolled into measured categories |
| **Captures** | Large real local screenshot theater, 5-second automatic loop | Play/Pause, Previous/Next, separately accessible video tab and optional file inventory | Never autoplay video, permanently remove or upload user images |
| **Graveyard** | Readable evidence-led review queue or illustrated no-findings state | Safe eligibility, exact protect/unprotect and item details | Unknowns and protected data stay protected |
| **Game DNA** | Large clickable forensic relationship map and selected-game cover | Verified asset/path inspector, evidence list and protected saves | Unverified links are not drawn as fact |
| **Undo Center** | Four recovery actions, animated-free recovery timeline, searchable ledger | Windows Recycle Bin status dial and item restore inspector | Logged deletion ≠ guaranteed recoverability |

## 4. Screenshot gallery requirements

- Use all detected gaming photos in inventory, sorted most-recent first, not merely a 700-row table subset.
- Advance every **5,000 ms** on the UI timer, looping from last to first. Explicit previous, next, play and pause. No automatic deletion.
- Decode one actual capture on demand in a bounded low-priority worker using the existing identity-checked image preview path.
- Pause timer whenever the Captures page or screenshot subtab is hidden, or window inactive. No active background scanning/upload/cache construction. On review deletion update slideshow source list.
- Test the 810th image exists in the sequence and slideshow wraps, pause/resume and hides.

## 5. Visual acceptance gates

**Never label a build “mockup matched” merely because it passes install/launch automation.**

1. Capture 1440-wide and 1024-wide fresh screenshots **of each page** on disposable real Qt/Windows UI, for both populated and empty states where applicable.
2. Overlay each screenshot against the correct named design reference; a human compares silhouette, relative panel proportions, hero height, artwork, typography, density, interactive placement and legibility. Record differences.
3. Test all page actions end-to-end with disposal-only fixtures: navigation, filters, previews, cancellation, protected-item override, recycle/undo.
4. Test lower resolutions/high Windows DPI and focus/contrast; reject clipped tables, washed-out panels and inaccessible controls.
5. Run Windows + Ubuntu safety tests, Windows native Qt smoke, slideshow and navigation tests, installer build/install/uninstall, and on-device FPS / 1%-low comparisons **before** 1.0.
6. Beta acceptance: obtain user's explicit visual sign-off on the actual app captures, then distribute signed beta builds when release gates are satisfied.

## 6. Engineering change list

- `gg_desktop/app.py`: global route history and ribbon; no changes to cleanup authority.
- `gg_desktop/theme.py`: high-contrast small navigation/detail chrome, named styling rather than overgeneralized panels.
- `gg_desktop/screens.py`: user-chosen custom library root; honest discovered-source chips; distinct page compositions.
- `game_signatures.py`: bounded game-specific executable evidence with symlink/reparse safety.
- `launchers.py`: broader Rockstar/EA/multi-launcher scan, registry and folder fallback, cancellation and metadata limits.
- `gg_desktop/models.py`: dedup corroborating evidence without double count.
- `tests/test_launcher_discovery.py`, `tests/test_crimson_navigation.py`: disposable regression coverage.
- `.github/workflows/windows-crimson-preview.yml`: tests gate packaging.

## 7. Definition of done

**Functional committed ≠ Windows package built ≠ visual acceptance ≠ production-ready.**  
The owner should receive the actual newest unsigned preview artifact after **success** of CI. Do not link to an older artifact as though it were the new build. Visual fidelity remains incomplete until verified with side-by-side screenshots against owner-approved references.
