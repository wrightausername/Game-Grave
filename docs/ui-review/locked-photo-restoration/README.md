# Locked-photo restoration

The owner's photos remain the specification. Earlier plain-table previews were
the wrong baseline. This correction restores the original cinematic shell and
native page compositions from the earlier implementation and connects the
completed controllers to them.

The following captures are from the running Qt app at 1280×720 on Linux/offscreen,
using disposable QA libraries. Counts, paths and evidence reflect those fixtures;
they are not fabricated live user data. Windows produces its own native captures
in the build artifact. The Ready Room capture uses its explicitly labeled sample
mode. Native rendering checks do not replace the owner's visual judgment.

| Page | Original owner photo | Running app |
| --- | --- | --- |
| Games | ![Original Games](../../../gg_desktop/assets/references/games.jpg) | ![Native Games](photo-games-functional-1280.png) |
| Mods | ![Original Mods](../../../gg_desktop/assets/references/mods.jpg) | ![Native Mods](photo-mods-functional-1280.png) |
| Old Files | ![Original Old Files](../../../gg_desktop/assets/references/old_files.jpg) | ![Native Old Files](photo-old-files-functional-1280.png) |
| Other Storage | ![Original Other Storage](../../../gg_desktop/assets/references/other_storage.jpg) | ![Native Other Storage](other-storage-1280.png) |
| Captures | ![Original Captures](../../../gg_desktop/assets/references/captures.jpg) | ![Native Captures](captures-1280.png) |
| Graveyard | ![Original Graveyard](../../../gg_desktop/assets/references/graveyard.jpg) | ![Native Graveyard](graveyard-1280.png) |
| Game DNA | ![Original Game DNA](../../../gg_desktop/assets/references/dna.jpg) | ![Native Game DNA](game-dna-1280.png) |
| Undo Center | ![Original Undo Center](../../../gg_desktop/assets/references/undo.jpg) | ![Native Undo Center](undo-center-1280.png) |

Ready Room's original is attached in the owner's conversation. Its actual native
render is [here](ready-room-reference-1280.png). Overview's original header crop
was recoverable, along with the original dashboard composition; its native
render is [here](overview-1280.png). A full Overview photo is not present locally.

All eight full photos are byte-identical to commit
`25f5955583b3d7a596a8f50cba9cf2bf9b9d17cb`; their checksum manifest is in the
reference directory. `photo_reference_guard.py` verifies those original bytes
and the existing safety/data engines. `photo_ui_smoke.py` exercises the cover
grid, game actions, mod hover/conflict tools, drive/full scan, paging, cancellation,
protected manual review and confirmed recycling through disposable transports.
It also checks all thirteen routes and 1280, 1440 and 960-pixel windows.

The Windows download includes `Compare-Locked-Photos.html`, the unmodified
originals, native Windows captures, both EXEs, checksums and source build identity.

Local validation: 495 unit tests passed, with one skipped; the photo integration,
original-photo/data guard and live Ready Room news/backup checks passed.
