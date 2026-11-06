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

For the Ready Room task, preserve its supplied reference layout and local artwork.
Connect its live controls and evidence without changing other screens. Keep
sample data confined to the explicitly labeled reference preview.

Active tab: Ready Room. The owner has explicitly reopened only this tab to match
the attached 1536×864 mockup. Its sidebar/header presentation must be scoped to
Ready Room and released before navigating elsewhere. Other tabs must remain
unchanged, including through shared code. Ready Room is awaiting owner signoff;
do not move on or record it as completed without that signoff.
