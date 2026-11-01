# Game Grave | Ready Room approved Crimson Command design

**Status: VISUAL DESIGN LOCKED BY PRODUCT OWNER — 2026-11-01**

The owner explicitly approved the **third, simplified Ready Room mockup** in the Game Grave ChatGPT design conversation on 2026-11-01 ("perfect.. lock it in"). This is the **canonical Ready Room layout and visual direction** for implementation. Do not substitute earlier, busier mockups or automatically generated generic cards. Any substantive design change needs owner signoff.

## Nonnegotiable look and layout

- Professional, restrained **Crimson Command** visual language: charcoal/near-black panels; soft burgundy depth; selective crimson highlights on selected or primary actions; bright legible white text; generous margins and negative space.
- A narrow illustrated red-moon/graveyard background in the header and bottom-left sidebar only. **Do not** turn every card into a neon-outlined image. No persistent flashing or GPU-heavy animations.
- Left navigation stays consistent with all Crimson Command screens. A **large, clearly visible SCAN PC** action remains prominent, not hidden in a top corner.
- Header: **READY ROOM**, brief preparation tagline and unobtrusive system/game-readiness state based on verified evidence. Avoid falsely saying READY when unsupported.
- Main content should match the approved mockup's hierarchy, spacing and density:
  1. **Your Lineup:** large authentic game covers across the top-left, selected cover emphasized, a clean selected-game card with launcher/status information and **Launch Game**, **Open Folder**, **Game Tools**. Use verified Steam/local official artwork where available; no fabricated cover substitutions.
  2. **Right-side column:** three concise panels, **Patch Watch**, **Performance Watch**, **Storage Watch**. Each presents the most relevant information at a glance and opens details on click.
  3. **Recap Center:** the major middle panel, prominent but not overpowering. Three clearly distinguished views **This Year**, **This Month**, **This Session**. Show real total playtime for chosen year, average session duration, number of sessions, most-played game, modest playtime timeline/chart, and recent session screenshots/video thumbnails. Clicking a session shows that session's actual captures and timestamps.
  4. **Below Recap Center:** three simple feature-entry cards, **Game Time Machine**, **Launch Guard**, **Mod Radar**.
  5. **Bottom:** **Session Notes** and **Daily Game Suggestion** in two balanced panels.
- Use subtle grouping, thin separators, gentle shadows and size differences instead of dozens of red glowing borders. Focus on legibility and calm scanning.

## Recap Center: functional requirements

- Yearly/2026 recap uses **measured sessions** with start/end timestamps (or verified launcher history with known provenance), not estimates passed off as fact.
- Show time-span controls for **This Year / This Month / This Session** and reflect selection in every number and graph.
- Annual hours, average length, session count, most-played game and time by month must all come from the same bounded source dataset.
- Per-session media gallery: use only actual screenshot/video files with defensible timestamp-to-session associations. Show ambiguous/unlinked captures separately; never claim a capture came from a session merely because the game titles look similar.
- Source gaps and incomplete history are common. Display **No data / Partial history / Only tracked since [date]** honestly. Do not invent example numbers in the product or assume a full year's activity was captured.
- Video thumbnails decode on demand; preserve existing user controls and safety around deletion/recycling.
- Simple local-first session records; optional collection, no invasive game injection, FPS hooks, anticheat interference, constant deep scans or expensive continuous polling.

## Supporting feature rules

- Patch Watch: original verified publisher/Steam sources, dated releases and links, not fabricated live updates.
- Performance Watch: no invented FPS/CPU/GPU readouts. Show manually recorded benchmark trends or a clearly marked **Not measured** until safe, opt-in measurement exists.
- Storage Watch: real disk OS counters, with uncertainty about the cause of changes.
- Launch Guard: only validated file/drive/mod evidence; must not claim game readiness, mod compatibility or save integrity without evidence. Never block launching.
- Game Time Machine is a gateway to genuine user-confirmed Resurrection Kit backup and recovery, not a pretend "restore" control.
- Privacy first; default no unnecessary accounts or telemetry, no background work reducing game performance.

## Visual acceptance checklist

- At Windows 1440-wide and 1080-wide, screenshot/visual review confirms the **approved simplified mockup's layout**, not the two earlier cluttered proposals.
- Main lineup, right status column, and Recap Center are easy to distinguish without excessive red accents.
- Recap Center provides actual-time metrics and session captures, and looks coherent with empty/partial data.
- Controls and captions remain readable at 100% and 125% display scaling; keyboard navigation and screen-reader labels exist.
- The prominent main **SCAN PC** action is visible; per-panel interactions are functional; no layout overlaps.
- No placeholder imagery, fake graphs, fictional FPS data or magic performance promises in production.
- No substantial visual or feature substitutions unless approved by the product owner.

**Reference:** The *last* Ready Room image generated and explicitly approved in the Game Grave conversation on 2026-11-01, described as the simplified, low-clutter Crimson Command Ready Room with Recap Center. The image itself lives in that design conversation; this Markdown file is the durable source specification in the repository. This document does not establish that the UI has been implemented.
