# Game Grave: zero-interference gameplay policy

**Status: implementation started; Windows validation required before release.**

The product requirement is to avoid measurable interference with users' games.
A universal guarantee of exactly zero FPS impact is not technically possible:
operating systems and hardware share resources, and a process can start between
two activity checks. Game Grave must err on the side of deferring nonessential
work rather than claiming performance neutrality without measurement.

## Shipping rules

1. Game Grave does **not** launch a heavy background scan by default
   (existing scan-on-launch option remains opt-in).
2. All inventory workers run at Windows background CPU and I/O priority,
   reducing competition with the foreground game **without lowering UI priority**.
3. Nonessential inventory work pauses at cooperative checkpoints when a
   known installed game process or another fullscreen app is detected.
   Cancelling a paused scan still works, and partial results are not published.
4. Scheduled cleanup exits/defer rather than waiting or deleting while a
   game is detected. A game starting during an automatic run aborts its
   remaining scan or cleanup work.
5. Game detection is lightweight and rate-limited; it uses a process executable
   path list and Win32 foreground-window geometry. No injection, overlays,
   driver access, anticheat tampering, or per-frame FPS hooks.
6. A game outside known launcher directories may be missed if windowed and
   not yet in Game Grave's verified inventory. Treat detector improvements as
   a release blocker for any broad "automatic background" features.
7. Ready Room Patch Watch should fetch **cached, low-frequency metadata**
   without doing disk-intensive local sweeps during play. Artwork, patch
   summaries and analysis are loaded on demand when panels are visible.
8. Save backups, Resurrection Kit builds, screenshot/video indexing,
   performance monitoring, and local AI must not become continuous services.
   All heavy tasks need the same game-aware scheduler and cancellation path
   before being enabled automatically. Never auto-delete or auto-restore.
9. No always-on capture, overlay, hardware telemetry, or continuous frame
   monitoring is permitted by default. Optional measurements require informed
   opt-in and compatibility safeguards.

## Required Windows acceptance tests

Run on Windows 10/11, multiple SSD/HDD setups, low-memory systems and at
least one machine with modest CPU core count. Test exclusive fullscreen,
borderless, windowed games, and game launched during a deep scan.

- Capture a reproducible 5-run baseline per game with Game Grave absent,
  idle, and scanning before a game launches. Compare average FPS and 1% lows
  using the same hardware, scene, driver and settings.
- **Acceptance target, not a claim:** <=1% median FPS difference and <=2%
  difference in 1% lows across paired tests, within measurement noise.
  Investigate any statistically repeatable regression even if under target.
- Confirm the scan visibly pauses when gameplay starts and resumes after
  gameplay ends; cancel must terminate promptly while paused.
- Confirm no disk-intensive automatic cleanup begins while gaming.
- Confirm no GPU polling or game process injection is used.
- Confirm CPU, disk and memory usage at idle and during gameplay, and inspect
  power/battery behavior and laptop thermals.
- Repeat with an unknown game installed to a custom library location and
  with a second monitor. Document any missed detection and address it before
  turning on new automatic features.
- Confirm all existing safety, inventory, Recycle Bin, licensing and recovery
  tests continue to pass. Actual Windows results are required, not just mocks.

**Important:** The current implementation covers the core scan paths,
scheduled cleanup, and low priority for Crimson jobs. It is a first guardrail,
not proof that every existing or future workflow is gameplay-neutral.
