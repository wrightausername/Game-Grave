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
0b6083ff645395692b144c4cb34fe382cffcaeeb, Windows preview 0.2.8:
https://github.com/wrightausername/Game-Grave/actions/runs/42311267197

Preserve Ready Room's layout, typography, artwork, scaling, controls and behavior.
This includes its dedicated sidebar/header, search, icons, actions, data/services,
assets and shared-app lifecycle hook. Changes to shared styles, components or
backend code must not alter the approved Ready Room. Its presentation must stay
scoped to Ready Room and release the shared shell when navigating elsewhere.
Keep sample data confined to the explicitly labeled reference preview.

Read-only inspection and regression checks are allowed. A discovered issue,
refactor or work on another tab does not authorize reopening Ready Room.
Only the owner's explicit instruction to change Ready Room can unlock it.

Limited reopening: the owner has explicitly reopened Ready Room to fix its
zoomed appearance and make its scale consistent with the rest of the app.
Use the existing native app sidebar/header and normal widget sizing; preserve
the approved artwork, card composition and functionality. No other tab is
authorized for changes. The earlier approval remains the visual foundation;
this specific scaling correction awaits renewed owner signoff.

Active tab: Ready Room, scaling correction only. Do not move on automatically.
