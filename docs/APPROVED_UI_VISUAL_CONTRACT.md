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

## 6. Graveyard tab — owner APPROVED on 2026-11-02

- **Approved exact image**: `Game_Grave_Graveyard_APPROVED_2026-11-02.png`, 1672×941, SHA-256 `e41b67713983e1c8cc822ad0a2f1659db493145b7753f2c0ec1380692d72eb79`.
- **Persistent reference**: user's Library folder `/Game Grave/Approved UI/2026-11-02 - LOCKED - Graveyard Overhaul.png`. It is the **same PNG bytes** as the owner-approved image, not a regenerated approximation.
- **Approval language**: owner explicitly said `i like... lock it in... next ... tab` after seeing this exact mockup. **Status: APPROVED AND LOCKED**.
- **Visual layout**: identical original red geometric GG logo, sidebar and top global search bar as the cinematic Overview; forest, stone GG marker with red leaves and controller; `Graveyard` heading; inline candidate summary/stat row, scan call-to-action, search and filters; dense two-column table + contextual item details, in-row protected/unprotected states; action strip; storage-impact footer.
- **Feature needs**: age-based discovery, per-item evidence and reason, drive/source/type filters, selectable entries, Protect/Unprotect, safe Delete via confirmation/Recycle Bin/Undo, Open Path and Keep List; do not assume content is safe to delete based only on age. 
- **Illustrative aspects of mockup, not production claims**: counts, sizes, space reclaimed, game associations, risk levels, path contents and any `safe to remove` copy. In the real app, replace misleading mockup risk/safety language with evidence-based action states, and distinguish potential space from reclaimed space. Preserve the owner-approved visual composition while correcting copy/data and enforcing non-overridable protections.
- **Locked design is not yet coded as the final production UI**. This GitHub PR holds the contract; Library holds the reference PNG. To change its visual design, require explicit owner approval and update this log.

**Next page:** Game DNA is next in navigation. Its new mockup must continue this identical visual language, not the prior fantasy/neon or old toolbar-heavy design.

## 7. Game DNA tab — owner APPROVED on 2026-11-02

- **Exact approved reference:** `cyberpunk_2077_game_dna_map.png`, 1672×941, SHA-256 `2021461dbbdb3a6d2605a912298c12758dbecab7b58e9e0d3991521e5fb27c07`. Persistent user Library location: `/Game Grave/Approved UI/2026-11-02 - LOCKED - Game DNA.png`.
- **Owner decision:** explicitly requested a richer, non-basic **interactive relationship map**, then approved the resulting map mockup: `good lock it in... next tab`. **Status: APPROVED AND LOCKED**.
- **Visual contract:** the exact Overview/Graveyard shell and palette with immersive node graph centered on the selected game, distinct connected storage/launcher/mod/workshop/save/cache/media/profile/unknown nodes, vivid but restrained relationship lines, selected node glow, map zoom/filter tools and an adjacent evidence-led node inspector. Contextual metrics, Ghost Watch, Patch Fallout, storage split and concise action strip support the map without replacing it.
- **Behavior contract:** actual interactive navigation, selection and zoom, drive paths and owner relationships backed by detected evidence, uncertainty when no reliable match, built-in save/active game protections, low-impact opt-in scan comparisons, links to Save Vault/Mod Radar; no claim of 97% verified confidence, actual size, compatibility or automatic repair without supporting evidence. Illustrated numbers/text are placeholders only.
- Never replace this map with a simple static pie chart or basic wireframe without owner approval.

## 8. Undo Center tab — owner APPROVED on 2026-11-02

- **Exact approved reference:** `game_grave_undo_center_dashboard.png`, 1672×941, SHA-256 `ce483d2ec16486e562a5870bc68dbab086c9fbfb52150df5307d32d8ba5f0034`. Persistent user Library location: `/Game Grave/Approved UI/2026-11-02 - LOCKED - Undo Center.png`.
- **Owner decision:** immediately after viewing the Undo Center UI mockup, said `good lock it in. next tab`. **Status: APPROVED AND LOCKED**.
- **Visual contract:** consistent original Game Grave cinematic Overview shell, matching top search and left nav, a distinct red glowing stone Undo motif within forest hero, a prominent five-stat horizontal summary, operation filters, a dense readable history table, right-hand restore details with path/evidence and action status, lower Recovery Safety and Undo Insights modules, and clear bottom restore/review actions.
- **Behavior contract:** log and review real actions, distinguish recoverable vs completed vs no longer restorable, deep inspect affected paths and provenance, restore through verified/explicitly confirmed backend recovery flow, never imply Recycle Bin retention has a fixed countdown, never promise restore when the item is gone or partial, never misstate moved bytes as reclaimed bytes, and do not offer forced restoration past validated protections. All mockup counts and retention days are illustration-only.

**Next tab to design after Undo Center:** AI Assistant. It must be **optional, OFF by default**, use opt-in local Ollama, explain it is not required for cleanup, and visually match the same Game Grave theme.

## 9. AI Assistant tab — owner APPROVED on 2026-11-02

- **Exact approved PNG:** `a_highly_detailed_cinematic_futuristic_ui_concep.png` (1672×941), SHA-256 `cce0b92db83ed6b607aec632bc42121242090bf91e53cee42956d44c32d6e6e8`. Preserved in user Library `/Game Grave/Approved UI/2026-11-02 - LOCKED - AI Assistant.png`.
- **Owner approval:** “I like it... lock it in... next tab” after reviewing richer second AI Assistant concept. **Status: APPROVED AND LOCKED**.
- **Visual lock:** Original GG shell; cinematic red-dark forest/stone banner; top status of local AI model/availability and clear enable control; left investigation/workflow modes (chat, analyze, troubleshoot, optimize, mod help, guides, game intelligence, custom tools), central AI conversation with embedded evidence and review buttons, right-context summary/insights panels, quick prompt/workflow cards along bottom. Richer than a generic chatbot.
- **Functional limits:** Local Ollama, optional, **disabled by default**, consent required to activate; no gameplay performance impact; no auto delete, direct unreviewed repair or override of protected files; only claim local metadata, performance status, findings, AI confidence or model availability when verified by the application. Screenshot's enabled state and sample findings are illustrative, not defaults or detected facts.

## 10. Settings tab — owner APPROVED on 2026-11-02

- **Exact approved PNG:** `game_grave_settings_control_center.png` (1672×941), SHA-256 `68f031509bb421c8f8c3463838e181d1744018048de93467826406375ac7dda3`. Preserved in user Library `/Game Grave/Approved UI/2026-11-02 - LOCKED - Settings.png`.
- **Owner approval:** “i like it lock it in... next” after viewing this exact Settings page. **Status: APPROVED AND LOCKED**.
- **Visual lock:** Original GG shell, cinematic red forest/stone GG banner; page title “Settings”; seven horizontal settings section tabs (General, Libraries, Safety, Performance, AI Assistant, Notifications, Advanced); strong multi-column but clean groups: Libraries & Detection, Protection & Cleanup Safety, Gaming Performance Guard, System Status, Storage Paths, Connected Services, optional local AI, Notifications & Ready Room, Privacy & Data, License/Edition, Quick Actions; prominent save/revert actions. Preserve subtle hierarchy and matching approved palette.
- **Functional limits:** Gaming FPS guard is essential, with suspension/deferment of heavy scans during play, low CPU/disk priority, low polling; owner-controlled protection, confirmation and Recycle Bin/Undo; AI **off by default**; privacy-first metrics and no uploads of filenames/game lists; all connected-service, health, license, model, system and storage values in screenshot illustrative only. Use verified data, never assume Pro active, Ollama connected, or launcher connected. Do not imply user can “turn off” non-overrideable built-in safety.
- **Next tab after Settings:** More Tools, which should match this exact shell and cinematic visual design, provide clear access to genuine existing or planned utilities (such as Save Vault, Resurrection Kit, Make Room, intelligent cleanup, exports) with functionality represented truthfully, and avoid marketing empty cards as finished.

