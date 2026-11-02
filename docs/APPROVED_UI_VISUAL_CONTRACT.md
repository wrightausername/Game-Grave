# GAME GRAVE — Owner-approved visual contract (LOCKED)

**Authority:** Owner-supplied image `Game Grave_ Cinematic Cleanup Dashboard.png`, posted in Game Grave conversation on **2026-11-02** as the definitive example with the words “THIS IS THE ... THEME.” This specification is binding for all *new UI work*. It supersedes visual treatments in earlier Crimson Command mockups **where they conflict with this image**. The screenshot itself, not an assistant-generated approximation, is the source of truth.

**Reference integrity:** This markdown does not claim the original image is committed here. Keep a separate copy of the owner-supplied image in the design pack and import the original visual reference into the repository when practical. An approximation is not a substitute.

## 1. Identity and visual language: never silently replace

- **Brand:** flat, sharply geometric red double-`G` monogram at top left, bold `GAME GRAVE®` adjacent. Do not substitute tombstone/controller clip-art logo, the older crest, or a fantasy-styled `GG` mark.
- **Dark cinematic desktop shell:** premium charcoal / almost-black window, subdued depth and atmospheric imagery. Red is the recognizable primary brand/action color. Cyan, purple, amber and teal appear sparingly as **functional** graph/metric highlights, not replacement brand colors.
- **Left navigation:** fixed-width dark rail with clear, human-readable white labels, thin simple outline icons, and a broad understated **dark-red active-row highlight**. Ordered destinations visible in the supplied reference: Overview; Ready Room; Games; Mods; Old Files; Other Storage; Captures; Graveyard; Game DNA; Undo Center; AI Assistant; Settings; More Tools. Do not remove/relabel established destinations without owner approval.
- **Top shell:** understated rounded search field across upper page, Ctrl+K hint, notification bell, help, ordinary Windows window controls. Do not reintroduce the old large `SCAN PC / Cancel Scan / THE SCAN IS YOUR CALL` toolbar across every tab.
- **Hero art:** wide cinematic photographic/illustrated forest-and-stone visual, a stone tablet bearing the approved red GG logo, gamepad, rich dark contrast, controlled crimson leaves/light, and generous negative space for page title. Visual richness belongs in the hero, **not** in borders around every widget.
- **Typography:** polished modern sans serif; large readable off-white page title, restrained secondary line. Strong hierarchy. No distressed fantasy fonts, acid-green text, purple cemetery branding, excessive glowing outlines, or cartoonish UI.
- **Component language:** generous alignment and spacing, mostly borderless or subtly separated sections, precise flat controls, clean state badges, restrained gradients. Prefer real content to decorative panels. Don't copy dated box-heavy wireframes.
- **Image/metrics distinction:** example game covers, counts, activity and storage values shown in the reference are **illustrative**. The app must display actual measured results or explicitly say Unknown / Not scanned.

## 2. Overview reference anatomy (fidelity test)

The definitive supplied overview has:
1. Narrow dark sidebar with red GG / GAME GRAVE header, dark-red selected `Overview` row and atmospheric dark-red tree silhouette near bottom.
2. Top global search and notifications/help/window controls.
3. Main hero reading `Overview` and `Your games. All their baggage. Under control.` over large cinematic GG gravestone art with branches and a red controller.
4. One lightweight five-metric band (Games; Mods; Old Files; Other Storage; Captures) with carefully separated cyan, lavender, amber, teal and purple accents.
5. Three balanced mid-page areas: `Recent Activity` with item cover thumbnails, `Space Reclaimed` circular graphic, `Quick Actions` straightforward rows. Do not invent measured reclaimed space.
6. `Your Library` strip with high-quality game cover thumbnails and unobtrusive pagination.
7. Mostly edge-to-edge composition; no unnecessary stack of thick-bordered cards.

## 3. Graveyard overhaul must fit that SAME shell

- Reuse **exact** sidebar, GG header mark, global search, typographic scale, page margins, primary red, dark surfaces, icon stroke and spacing from the approved Overview. Avoid changing shell just for Graveyard.
- Keep one appropriately atmospheric **Graveyard-specific** cinematic hero matching the forest/stone/red GG visual family, with `Graveyard` heading and an explanatory line; avoid big synthetic green/purple graveyard art or unrelated skull/sword imagery.
- Main task: search/filter **genuine discovered file candidates**, not score installed games as fictitious “critical risk” based on age or delisting. Filters: age, source/game/launcher, type, drive, sort and protection status, subject to reliable data.
- File table: readable item and actual path, related game/launcher/mod manager, category, candidate size, grounded age/last-used evidence (Unknown if unavailable), classification, protection and action availability. Select single/multiple; row click opens side details and a right-click context menu.
- **Evidence/details pane:** explicit “Why flagged”, actual detection signals, source, confidence/uncertainty, action consequences, related game, protected reason, preview/open path. Do not claim `safe to delete` from age alone.
- **User control:** Protect / Unprotect visibly accessible **from Graveyard** for eligible user-added Never Touch rules, with confirmation. Built-in system/active install/save/manager protections remain non-overrideable; explain restriction. Send to Graveyard from supported related tabs if owner-approved. `Delete` only after explicit review and confirmation, through the established safe Recycle Bin + Undo flow. No background or automatic deletion, and no indiscriminate `Delete All` bypass. Saves remain protected.
- Distinguish **potentially reviewable size** vs **bytes actually reclaimed**. Unknown is not zero. The right-side details panel must not eat so much width that table content becomes unreadable.
- Real empty, scanning, partial, cancelled, error and completed states. Empty means `Nothing found` and explains filters/scope; no fake examples in production.
- Preserve gaming FPS/1%-low priority: pause/defer heavy scans during gaming, low-priority bounded background work, no game injection/overlays.
- Match at 1440x900 and adapt cleanly to 1366x768 and 125%/150% Windows DPI; responsive layout must not clip controls.

## 4. Change control: what “LOCK IT IN” means

1. **No re-approval by default.** A locked visual reference stays the reference until the owner explicitly replaces it. Later casual brainstorming does not supersede locked design.
2. **Every future approved layout** must have (a) named/dated reference image or exact source asset, (b) its associated decision/spec, and (c) explicit status: proposed, approved, superseded. Never treat a generated mockup as implementation.
3. **Before editing a page**, read this contract and its per-page addendum. Compare to the approved reference image, not to a previous assistant's paraphrase.
4. **No silent theme drift.** A change to logo, dominant palette, sidebar, hero style, navigation, typography, or shared shell needs explicit owner approval. Keep functional adjustments inside the visual system.
5. For every UI PR, attach actual **running app screenshots** of changed pages (not AI renders) at reference resolution, list visual diffs, and run layout/contrast/DPI plus behavior tests. If source art is missing, call it out as a blocker rather than drawing unrelated art.
6. The newest confirmed screenshot beats older text descriptions when there is a conflict; nonvisual features remain governed by their own verified safety specs. Preserve previous page-specific approvals unless expressly superseded.
7. Do not state a UI is implemented, “pixel perfect”, installer-ready or released without the actual artifact and validation evidence. No invented status.

## 5. Change log

- 2026-10-31: earlier `UI_REDESIGN_BLUEPRINT.md` documented an initial Crimson Command direction and safety/architecture constraints.
- **2026-11-02: OWNER VISUAL REFERENCE LOCK**: owner re-supplied the premium *Game Grave Cinematic Cleanup Dashboard* screenshot and explicitly clarified it, **not** the old toolbar-based or neon/green/purple mockups, defines the intended Game Grave Theme. Graveyard must be brought into visual parity with this reference.
- Status of this file: **locked visual contract proposed for inclusion in main**. Until PR merge, its branch is a durable review copy; do not pretend it is already in main.
