# Locked cinematic UI implementation

The design authority remains [the owner's visual contract](APPROVED_UI_VISUAL_CONTRACT.md).
The seven layouts run as native Qt pages and load the existing photo crops in
`gg_desktop/assets/owner_cinematic_*.jpg`. Each title, metric, filter, selection,
conversation and action is a real widget over the existing local backend.

| Locked page | Implementation | Working interactions |
| --- | --- | --- |
| Overview | `gg_desktop/approved_overview.py` | Scan, five inventory destinations, local activity, cleanup review, installed-game strip |
| Graveyard | `gg_desktop/approved_graveyard.py` | Evidence filters, multi-selection, inline personal Protect/Unprotect, individual media review, confirmed Recycle Bin actions |
| Game DNA | `gg_desktop/approved_dna.py` | Game selection, interactive relationship map, evidence inspector, zoom/pan, Ghost Watch and local-change review |
| Undo Center | `gg_desktop/approved_undo.py` | Search/filter actual ledger, inspect original paths, verify exact Windows match, explicitly restore |
| AI Assistant | `gg_desktop/approved_ai.py` | Optional local conversation, workflow shortcuts, inventory context, session continuity across navigation |
| Settings | `gg_desktop/approved_settings.py` | Seven category tabs over existing preference controls, protection/library management, local AI configuration |
| More Tools | `gg_desktop/approved_more_tools.py` | Illustrated Resurrection Kit/Save Vault workflows, tool shortcuts, local history and recovery diagnostics |

## Resize and navigation behavior

Desktop proportions stay intact at 1672×941. Native grids and split workspaces
reflow using their available logical width at smaller sizes, including
1366×768 and 1040×720. Resizing does not recreate the current page, discard a
selection, reset a filter or lose an in-flight conversation. The approved image
crops and sidebar remain unchanged. Scrolling exposes controls below the fold.

Settings uses exact launcher identities when counting installations; the string
`EA` inside `Steam` is not EA installation evidence. Ambiguous installations
retain their existing separate classification.

## Verification and screenshot evidence

`python -m unittest tests.test_locked_ui_layout -v` exercises all seven populated
and empty pages, resizing the same live page, Graveyard selection retention,
launcher counts and a delayed AI response after its old widgets are destroyed.
Qt is optional for the core test suite; the Windows preview workflow installs
Qt and requires these tests to pass before packaging.

Set `GG_LOCKED_UI_CAPTURE_DIR` to a disposable output folder to capture the
seven running pages at 1672, 1366 and 1040 logical widths. The Windows workflow
uploads these PNGs and `locked-ui-evidence.json`, including when a later check
fails. These screenshots use synthetic inventories, not the owner's PC data.
The existing Windows smoke additionally exercises all 13 routes, real local
artwork discovery, protection/recovery controls, and 125%/150% DPI.

## Acceptance still separate

The complete original approved PNGs are catalogued in the owner's Library by
the visual contract; the repository contains cropped runtime artwork. Passing
layout tests or compiling an installer does not establish pixel-for-pixel
agreement with those originals. Exact visual comparison, physical gameplay
FPS/1%-low measurements, commercial signing and the existing release gates
remain separate acceptance steps. This implementation does not mark 1.0 ready.
