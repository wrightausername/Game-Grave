# Overview and Ready Room: supplied full-size reference pass

The owner supplied two 1672×941 images in this conversation on November 4, 2026
(client date), requested the dashboard to look exactly like the first image,
including its faint glow, and then requested Ready Room to match the second.
These images supersede older interpretations of these two layouts. They are
visible in the conversation but are not exposed as downloadable original image
files in this execution workspace. No source-image hash is invented here.

## Implemented composition

- Shared shell: 296px rail, the reference's outline navigation glyphs, larger
  labels and geometric red monogram, dark red selected-row light, integrated
  search/keycap and working minimize/maximize/close controls. Dragging the
  title area and resizing the window use native system operations. Startup
  size respects the available monitor. A notification dot reflects actual
  scan warnings rather than a fabricated unread count.
- Overview: title and negative space above a five-metric band; measured column
  proportions for Recent Activity, Space Reclaimed and Quick Actions; the
  reference's five quick-action rows; a compact library with actual pagination.
  At the reference size the library starts around y=630 and its covers are
  approximately 200×170. Only real records populate activity and game cards.
- Light: restrained colored icon halos and feathered metric underlines, a
  shaded red ring, a subtle red cleanup-button bloom, and reflections from
  verified cover images. All effects are static paint; no animation, polling,
  network calls or game hooks are introduced by these widgets.
- Ready Room: five status categories; Patch Watch and Your Games at a Glance
  in a 61:39 split; Mod Radar, Save Vault and System & Game Health beneath.
  Real game rows and their verified covers remain tied to inventory records.
  The existing searchable, sortable inventory is preserved in a disclosed
  advanced view and drives the new summaries. Save Vault and scan buttons
  invoke the existing consent and backup workflows.

## Data stays factual

The reference's 127 games, update counts, playtime, backup coverage and 92%
health are illustrative. Existing discovery records provide real counts and
sizes. Patch feeds and release/follow sources are not connected, compatibility
and overall health have not been assessed, and Save Vault has no global index
of verified backup coverage. These states are shown explicitly. Recycle Bin
moves are still distinguished from verified free space; Run Cleanup opens
Graveyard review and never silently removes files.

## Artwork limit remains explicit

The existing `owner_cinematic_overview.jpg` is a cropped photographic strip,
not the complete new Overview source image. It is reused proportionally and
feathered into the shared backdrop. It cannot recover pixels outside its crop.

The Ready Room workstation photograph and its lower-card artwork are **not**
in the repository or mounted uploads. `ReferenceSurface` supports the dedicated
`gg_desktop/assets/owner_cinematic_readyroom.jpg` when the original is available;
until then the existing approved photo family is a fallback. This fallback is
not the pictured workstation, and the UI must not be called a complete exact
match while that asset is missing. No generated replacement is presented as the
owner's original.

## Validation

525 local regressions (3 platform-specific skips), including 16 Qt layout and
interaction tests. The added checks exercise real carousel paging and game
selection, Ready Room filtering and source status, and window controls without
rebuilding the active page. Both pages and the other routes are rendered at
1672×941 and 1366×768; native Windows, 125%/150% DPI, EXE and installer validation
are linked from PR #88 and the versioned preview release.
