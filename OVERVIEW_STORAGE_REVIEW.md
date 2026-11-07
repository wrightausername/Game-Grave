Overview now includes installed games in the storage pie and measures detected
folders from file metadata rather than trusting stale launcher totals. The
existing machined ring paint, hero, library artwork, panels and shell are kept.

The five categories form a disjoint union of measured file identities. Captures,
cache/config findings, and mod files have explicit category precedence; game
files follow, then remaining old files. Nested roots are traversed once.
Hardlinks use device/inode identity and deployed mod links are attributed to
Mods regardless of enumeration order. Sparse/compressed physical allocation
and reclaimable space are not inferred. Unknown, inaccessible, redirected and
bounded content remains explicit partial coverage. No accepted inventory,
source file, cleanup decision, shared engine or protected tab is changed.

The native breakdown exposes folder bytes, exact chart contributions, launcher
estimates for comparison, warnings, refreshed timestamps and separate per-drive
capacity readings. Refresh/cancel retains the last successful reading on error.
Present individual mod packages are counted where manager metadata supports
them; fallback counts are labeled locations. Overview cards use measured sizes.

Existing Overview controls now support persisted favorites, library/activity
search and Enter-to-inspect results, exact installation selection, bounded
search results, complete shelf paging, scan busy/cancel states, source coverage,
validated scan-location edits, and event-specific activity details. All existing
metrics, quick actions, history and cleanup-review links retain their routes.

Validation: 19 new measurement tests; the full 514-test suite passes (one skip).
The actual Overview Qt smoke covers controlled bytes and hardlinks, refresh,
cancel/error retention, all existing controls, 513 installations and four sizes.
The twelve other tabs pass 72 baseline pixel comparisons against approved
Ready Room commit 471eb2bb088915573d99e7010f8472a28a274b9a. A source guard
restricts the shared integration change to Overview's builder; all protected
runtime source, artwork and data engines match that baseline.

Preview version: 0.2.10. Ready Room remains owner-approved and locked at 0.2.9.
Overview remains pending owner signoff; this work does not authorize another tab.

Windows directory-entry metadata omits file IDs and link counts; measurement
re-queries lstat before identifying files. A dedicated zero-ID regression test
and native NTFS hardlink fixtures cover this distinction. Overview metric
values fit their existing available width at the narrow viewport.
