# Approved UI foundation

The owner's locked photos are the visual specification, not the current code or
prior preview screenshots. The unmodified originals are in
`gg_desktop/assets/references/`; the Ready Room original is also in the owner's
conversation. Do not replace their shell, artwork, proportions, cover grid,
filter columns, metrics, tabs or right-side inspectors with generic tables.
Prior code-baseline pixel checks do not establish fidelity to the photos.

Before editing UI,
acknowledge the exact requested sections in chat. Confine changes to those
sections and preserve all other screens, the shell, navigation, styling and
behavior. An overall redesign requires an explicit request from the owner.

## One tab at a time; completed tabs stay locked

- Work only on the single tab the owner currently names. Acknowledge that tab
  and the requested sections in chat before editing. Do not expand the scope
  to other tabs or start the next tab on your own.
- The owner decides when the tab is complete and when to move on. Passing
  checks or declaring the work finished does not replace the owner's signoff.
- Once the owner accepts a tab and says to move on, that tab stays locked
  across later tasks, turns and branches. Do not change its layout, artwork,
  controls or behavior unless the owner explicitly instructs you to change
  that tab again. Record explicit tab signoffs here as they occur.
- This restriction includes indirect changes through shared styles, widgets,
  navigation, controllers or backend code. Work on the active tab must preserve
  every locked tab. Read-only inspection and regression checks are allowed.
- If the requested work requires changing a locked tab, identify the exact
  dependency and wait for the owner's explicit instruction before that change.
  Continue only independent work within the active tab. Refactoring, cleanup,
  consistency work or an incidental fix does not authorize reopening a tab.

## Locked tabs

Ready Room: OWNER APPROVED AND LOCKED. The owner explicitly accepted the result
and instructed that it must not be touched unless they specifically say otherwise.
The approved runtime baseline is commit
471eb2bb088915573d99e7010f8472a28a274b9a, Windows preview 0.2.9:
https://github.com/wrightausername/Game-Grave/actions/runs/42320457095

Preserve Ready Room's layout, typography, artwork, scaling, controls and behavior.
This includes its native app scale and shared sidebar/header, search, icons,
actions, data/services and assets. Changes to shared styles, components or
backend code must not alter the approved Ready Room. It must not replace,
resize or magnify the shared app shell when navigating into the tab.
Keep sample data confined to the explicitly labeled reference preview.

Read-only inspection and regression checks are allowed. A discovered issue,
refactor or work on another tab does not authorize reopening Ready Room.
Only the owner's explicit instruction to change Ready Room can unlock it.

The owner explicitly approved and locked the native-scale correction, then
instructed work to move back to Overview. Ready Room is no longer open for edits.

Active tab: Mods. The owner directed work to the Mods section ("Mods section needs
full functionality right now... we are working each section 1 at a time"). Games is not
signed off but is frozen at commit 593354b0e24b1ad03b513b04e6902b44fe511b1a; do not change it, its controllers or its
artwork until the owner says. Mods work is confined to the Mods methods of
`PhotoIntegration`, `gg_desktop/mods_page.py`, `gg_desktop/mods_insight.py` and the
existing Mods modules; `tools/mods_tab_lock.py` enforces this. Mod managers' files are never
modified, and nothing in Mods deletes anything: managed mods, profiles and saves stay protected.

Previous active tab (Games). The owner explicitly reopened Games to triple-check its
functionality and ensure launcher cards and game artwork cover Steam, EA,
Rockstar, Epic and other launchers. Preserve the locked Games photo layout.
Confine fixes to Games, its own controllers, artwork and launcher adapters.
The owner has not signed off on Games or authorized moving to the next tab.
The owner has now explicitly authorized finishing the remaining Games gaps:
real launcher management actions, ownership/update/playtime integration, and
automatic artwork coverage. Account connections, their private storage and
provider adapters must remain Games-only. Show accurate capabilities and data
sources; never substitute fake ownership, playtime or completion messages.

Preserve Overview exactly as it stands in Windows preview 0.2.12, commit
df6bd6628adf6dd9713fe41235acb618da594574. The owner moved the current work to
Games; this does not authorize further Overview edits or imply new signoff.
Protect all twelve other tabs, including Overview and the locked Ready Room,
against this source and rendered baseline during Games work.

Latest request: fix the Games banner artwork only. Preserve its geometry,
title, subtitle, header controls, library layout and existing functionality.
Use the original artwork; align its header rendering without changing shared
TitleBar/PageBanner implementations or any other tab.
