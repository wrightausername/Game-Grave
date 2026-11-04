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
| Settings | `gg_desktop/approved_settings.py` | Seven category tabs over existing preference controls, protection/library management, local AI configuration, saved checkpoint/revert |
| More Tools | `gg_desktop/approved_more_tools.py` | Illustrated Resurrection Kit/Save Vault workflows, editable pinned shortcuts, local history and recovery diagnostics |

## Resize and navigation behavior

Desktop proportions stay intact at 1672×941. Native grids and split workspaces
reflow using their available logical width at smaller sizes, including
1366×768 and 1040×720. Resizing does not recreate the current page, discard a
selection, reset a filter or lose an in-flight conversation. The approved image
crops and sidebar remain unchanged. Scrolling exposes controls below the fold.

Settings uses exact launcher identities when counting installations; the string
`EA` inside `Steam` is not EA installation evidence. Ambiguous installations
retain their existing separate classification.

## Scan behavior

Inventory and requested Ghost Watch/Patch Fallout scans run regardless of game,
overlay or fullscreen activity. Workers retain low CPU/IO priority and normal
cancellation. File protection, cleanup confirmation and restoration validation
remain separate from read-only scan scheduling.

## Verification and screenshot evidence

`python -m unittest tests.test_locked_ui_layout -v` exercises all seven populated
and empty pages, resizing the same live page, Graveyard selection retention,
launcher counts and a delayed AI response after its old widgets are destroyed.
It also covers checkbox selection and protected batch rejection, saved Settings
checkpoints, confirmed protection-rule rollback, editable pins, and literal
rendering of HTML-looking conversation text.
Qt is optional for the core test suite; the Windows preview workflow installs
Qt and requires these tests to pass before packaging.

Set `GG_LOCKED_UI_CAPTURE_DIR` to a disposable output folder to capture the
seven running pages at 1672, 1366 and 1040 logical widths. The Windows workflow
uploads these PNGs and `locked-ui-evidence.json`, including when a later check
fails. These screenshots use synthetic inventories, not the owner's PC data.
The existing Windows smoke additionally exercises all 13 routes, real local
artwork discovery, protection/recovery controls, and 125%/150% DPI.

## Reference-driven visual review

The owner supplied a seven-page locked/reference versus running-UI comparison
on November 4. The left column is the target for the current visual pass:
compact controls and coloured metrics; filename/path rows with native
checkboxes; a dense twelve-node interactive DNA map; recovery safety dial and
recorded-state tracks; a wide conversation workspace; compact Settings groups;
and proportionate featured tools with no empty lower tile area. Runtime headers
continue to use the original owner-provided photographic crops.

`python tools/render_locked_visual_review.py --output <folder>` captures the
actual seven Qt pages at 1672×941 and 1366×768 using an isolated, explicitly
synthetic inventory, activity ledger and conversation. It performs no scan,
cleanup, network request or AI inference. Demo game illustrations are labelled
in the fixture; production loads the exact game's verified local publisher art
when available. The Windows workflow also runs this renderer and uploads its
screenshots before packaging. The JSON manifest records platform, dimensions,
commit and fixture provenance.

## Visual acceptance

The supplied comparison establishes composition, artwork placement and visual
hierarchy. Its reduced resolution does not establish exact original font or
pixel dimensions. Passing tests or compiling an installer does not certify
1:1 agreement. The review screenshots show the implemented result directly;
exact pixel parity is not claimed. This UI work does not mark 1.0 ready or
close unrelated release gates.
