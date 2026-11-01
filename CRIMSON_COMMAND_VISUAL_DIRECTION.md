# Game Grave — Crimson Command Visual Direction (Locked Reference)

**Design language:** **The Archivist's Workbench**  
**Purpose:** Turn the approved mockups into a recognizably authored Windows application, not a stack of interchangeable AI-dashboard cards.  
**Reference images:** “Crimson Command Mod Control Center.png”; “Crimson Command Mods Dashboard.png”; “Old Files: Digital Archive Cleanup.png”; “Game Graveyard Dashboard(1).png”; previously approved Crimson Command Game DNA / Undo Center references.  
**New concept:** 2026-11-01 Game Library / RDR2 discovery illustration with persistent **Back / Ready Room → Games → Discovery / Home** navigation. Illustrative data in mockups must never become product data.

## Visual character

A retired dungeon archivist with a Windows PC: technical clarity, a small amount of weathered fantasy personality, and generous breathing room.

**Do:**
- Give each screen **one dominant designed surface** and one supporting context surface; not six equal-weight rectangles.
- Use dark navy-charcoal (#080D15), velvet crimson (#E63B58), icy cyan (#48C8DF), parchment white (#E7E7E5), and warm slate only for supporting text.
- Retain the recognizable Game Grave emblem, black raven, old fortress, carved headstone and subtle atmospheric ruin scenes. Make them *contextual*, not repeated decorative wallpaper.
- Use serif only for a short hero/editorial heading and major one-word section markers. Use a consistent contemporary sans serif for all actions, labels, table text, data and dialog contents. No swirly script or gimmicky medieval UI fonts on functional controls.
- Draw the app's own razor-thin route dividers, modest etched corner treatment, source seals and precise icons. Every ornamental element is subordinate to actions.
- Align to an 8-pixel rhythm; 12/16/24 px internal padding; 34–42 px primary controls; high contrast at 125–200% Windows scaling.
- Keep confidence status distinct: green = positively verified, amber = incomplete evidence, crimson = destructive review or risk, cyan = information/navigation. Reserve bright red backgrounds for selected/important actions, not every widget.
- Let empty states breathe with a single custom illustration and a useful next action. Don't fake empty charts or placeholder products.
- Make screenshots real, game covers real where retrieved, and every status count sourced. A convincing fictional screenshot is **not** a valid scanned fact.

**Do not:**
- Use the same hero art, same row of KPI cards and same 70/30 table on every screen.
- Flood every border with neon red, every section with icons, and every paragraph with tiny all-caps. That is decorative noise, not identity.
- Pretend unknown games have official images; don't generate fictional game boxes and label them real.
- Invent "87% healthy," "5 conflicts," "12.6 GB recoverable," RDR2 playable status or license entitlements.
- Embed flat mockup PNGs as the app UI. Interactive, native high-DPI Qt Widgets must remain real controls with real data.

## Global shell (all 7 feature tabs)

- Fixed left nav rail, 210–225 px; black charcoal background, Game Grave mark at top.
- Compact scan controls, visible stop/cancel state, then a narrow **Back ← / breadcrumb / Ready Room** navigation ribbon; never hidden in a scrolling tab.
- Content is scrollable with persistent top navigation. Tab changes must not lose Back history. Keyboard **Alt+Left** goes Back.
- Hero/header ~190–248 px high, with custom relevant illustration and short explanatory headline. Don't take over half the screen. No fictitious "live" metrics in artwork.
- Use hand-tuned grid proportions based on actual minimum readable widths. Responsive collapse before clipping; scroll real tables horizontally if required.
- Modal dialogs use the same readable palette, maintain keyboard focus, confirm dangerous actions and never present white-on-white text.

## Panel A — Mods / The Mod Atlas

**Approved signature:** five artwork-led game cards per row (at 1440-wide window), two rows when possible; six compact metrics arranged below hero; a tall right-hand Mod Radar inspector.

- Hero: red moon, ruined castle silhouette, one crowned archive symbol. *Not the same picture used on Old Files.*
- Main: a cover-grid showing actual game/manager paths, not a generic file table. Selected tile has a restrained crimson frame, with linked mods and reported sizes clearly labeled.
- Right: round red Mod Radar instrument, source/protection/evidence breakdown, "Run Scan", "Open folder", "Review in Graveyard". No fake conflict/unused analysis.
- Advanced inventory is collapsed initially; searchable and sortable under the designed grid.
- Empty state: “No verified mod locations in this scan” plus investigate options.
- Required state visuals: **discovered, no data, incomplete scan, protected source, selected game**.

## Panel B — Old Files / The Archive

**Approved signature:** cold cyan hard-disk and holographic folder art; 5 category shelves; file ledger left and stacked cleanup insights right.

- Selected folder and Quick/Full scan controls are at the top, visible. C: fixed drive selection remains available where safe.
- Category shelves: Cache / Logs / Temporary / Install Remnants / Other. Each tile has a visually distinct hand-drawn icon, a count, and a measured apparent-size figure.
- The results list is functional, readable at 1024 and 1440, with classification tags, dates, file-specific protection state, and deliberate selection.
- Right: actual age chart and total **apparent** size, scope note, "Choose folder / Rescan / Review in Graveyard" actions.
- “Last modified” is not “last used.” Recycle Bin **may not free space until emptied**. Never call a guessed amount “estimated reclaim.”
- Empty state should look like a satisfying clean archive, not a blank table.

## Panel C — Other Storage / The Map Room

**Signature:** an illustrated drive-platter / cyan-segment architecture distinct from the red moon pages.

- A genuinely useful single-drive selector, **Quick Scan**, **Full Scan**, **Cancel** and precise progress/ETA caveats at eye level.
- A large measured category breakdown is the visual anchor. The data legend and source/coverage note are adjacent, not lost 2 screens down.
- File/root ledger under the chart (sort by category/size/count); relevant folder inspector and open-path control in a secondary space.
- Unknown, inaccessible, encrypted, system, and unscanned regions never masquerade as categorized bytes.

## Panel D — Captures / The Screening Room

**Signature:** large actual widescreen image with small film-strip controls, elegant crimson “5 SEC” cadence marker; separate Videos tab.

- Screenshot gallery autoplays every **5 seconds** through the entire discovered gaming screenshot list. Previous, Next, Play/Pause always accessible.
- The screenshot itself is the hero, no table before the photo. Maintain aspect ratio; do not enlarge tiny images to blurry fills.
- Keep a filename, local modified date, source information and 1/N position legible but secondary.
- The normal screenshot inventory is behind an optional toggle. Videos remain accessible and open only in the Windows media app when requested.
- Timer pauses on background, navigation and hidden tab. The slideshow is for viewing, not automatic deletion.
- Fullscreen review has independent per-image Keep/Recycle safety; Undo remains authoritative.

## Panel E — Graveyard / The Burial Ledger

**Approved signature:** blue moon cemetery header with raven and controller tombstone; central “No items found” holographic folder artwork when empty; right “Scan options / What gets found” sidebar.

- In populated state: a search/filter row, evidence-focused review ledger and a side inspector. Data row shows why flagged, last modified, apparent size and protection.
- Allow per-item protection override where permitted; managed active games/mods remain protected by default.
- “Select reviewable” is not “Delete All”; confirmation explicitly lists and revalidates candidates.
- Recycle Bin move is never shown as immediate disk space reclaimed. No hidden bulk deletion of screenshots.

## Panel F — Game DNA / The Forensic Observatory

**Signature:** large, glowing interactive central relationship map (>500 px on roomy window) with source-proven edges, selected-game verified artwork and a focused inspector.

- Center game node → installs, mods, saves, captures, configs and leftovers. Links must be proven by paths/manifests, not fuzzy names.
- Cyan for source-evidenced nodes, crimson/amber for unknown or review-only.
- Hover/click a node to see the actual path, source, category, protection and last checked.
- Evidence listing follows diagram, not vice versa. Protected saves remain first-class.
- No unsupported “complete game DNA” or “reclaimable bytes” claims.

## Panel G — Undo Center / The Recovery Desk

**Signature:** a quiet precision instrument, not a folder-cleanup clone. Four clear recovery action tiles and a simple original→Recycle Bin→restore strip.

- Left: recorded deletion ledger, searchable/sortable, not packed with decoration. Right: selected record, recovery status dial and Verify/Restore buttons.
- Green only after current Windows verification. Gray if unknown or absent; no guarantees about Windows retention time.
- Keep “Browse Windows Recycle Bin” and manual recovery path visible; never overwrite originals silently.
- Show a clear distinction between **logged action** and **currently recoverable entry**.

## Signature interface details that make Game Grave feel authored

1. **The route ribbon**: the same narrow carved-back plate above every screen. Always useful, never ornamental-only.
2. **Source seals**: truthful, readable badges such as “Steam manifest,” “Rockstar registry + RDR2.exe,” or “Unknown owner.” Not fake green badges.
3. **The inspection margin**: a common right-hand 300–345 px column on investigative screens, with different content per feature.
4. **The archival typography**: one restrained serif heading plus plain body, not fifteen fonts.
5. **Red as focus, cyan as evidence**: meaning stays consistent between screens.
6. **One meaningful illustration per screen**: Raven/tombstone only in Graveyard, circular radar in Mods, disk stack in Other Storage, filmstrip in Captures, linked nodes in DNA, loop arrow in Undo.
7. **Real scan progress and states**: nothing staged merely to fill space.

## Screenshot review checklist for every build

Visually inspect at **1440 × 900, 1024 × 768 and 125% Windows scaling**:
- Hero matches approved subject and tone; no stretched/pixelated assets.
- Primary action and essential controls visible without needless scrolling.
- No clipped buttons, overlapping labels, tables below minimum legible width, missing mouse targets, or white-on-white dialogs.
- Data panels reflect real test fixtures or real scans; fixture renders clearly named SYNTHETIC QA.
- Back navigation and breadcrumb, Play/Pause gallery and input search/sort functions really work.
- Running a game does not cause unexpected CPU/disk-intensive activity or FPS/1%-low regression.
- Before owner visual signoff, mark **design fidelity: in progress** even if the CI installer is green.

## Specific acceptance images

Use **Crimson Command Mods Dashboard.png** or **Crimson Command Mod Control Center.png** for Mods; **Old Files: Digital Archive Cleanup.png** for Old Files; **Game Graveyard Dashboard(1).png** for Graveyard; the approved per-screen Game DNA and Undo Center images for those panels; and the new RDR2 library concept for the navigation/discovery language. The reference is a *design target*, not a screenshot to be pasted over broken real controls.

**Implementation milestone:** owner reviews fresh native screenshots of each page. Do not declare final visual parity without owner approval.
