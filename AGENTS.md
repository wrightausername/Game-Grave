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

Mods: OWNER SIGNED OFF AND LOCKED ("Good lock it in"). The approved baseline is commit
d83f972716d258aa10d8e1005539f460160fe2d1 on branch `claude/mods-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42458764179. Do not change its
layout, tabs, controls, statuses or behavior, or anything that reaches it through shared
styles, widgets, navigation, controllers or backend code, unless the owner explicitly
reopens it. The next tab's lock must freeze Mods against this commit.

Old Files: built with full functionality on branch `claude/old-files-full-functionality`
(latest verified Windows run for its content:
https://github.com/wrightausername/Game-Grave/actions/runs/42465551781). The owner moved on to
Other Storage after the banner fix, so Old Files stays locked unless the owner reopens it. There was
no separate "lock it in" message, so treat that as not formally signed off. Nothing in Old Files
permanently deletes; removal is Recycle Bin only after the existing re-checks.

Other Storage: OWNER SIGNED OFF AND LOCKED ("good lock it in"). The approved baseline is commit
0689695ee5ada524f0c96eaa674488b8c2e180be on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42469660937. Do not change its layout,
tabs, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: no invented "safe to clear"; driver and Steam
library caches are review only; settings and saves are never removable; launcher cache and log folders
of 200 files or fewer go to the Recycle Bin only after confirmation and per-file re-checks. Widening
deletion (core is byte-guarded) needs the owner's explicit approval, which has not been given. The
next tab's lock must freeze Other Storage against this commit.

Captures: OWNER SIGNED OFF AND LOCKED ("good lock it in"). The approved baseline is commit
8402ac06a190b3e7164a21c48322c17043f190bf on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42475554496. Do not change its layout,
tabs, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: ownership only from proof, never a "safe to
delete" claim, Recycle Bin only after confirmation and per-file re-checks. The next tab's lock must
freeze Captures against this commit.

Graveyard: OWNER SIGNED OFF AND LOCKED ("Yes lock it in"). The approved baseline is commit
1202b47cad0103c3a8aed61d2c13b67cdbf2de15 on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42478374434. Do not change its layout,
tabs, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: the Evidence column (Direct, Location, Name hint,
Age only, Yours) replaces any confidence claim, "Reviewable" never means safe to remove, leftover
scanning only runs when the owner presses Scan Leftovers, and removal is only single archives or
recordings to the Recycle Bin through the existing verified path (screenshots one at a time after
preview; games via Steam; mods via Mods; folders via Other Storage). The next tab's lock must freeze
Graveyard against this commit.

Game DNA: OWNER SIGNED OFF AND LOCKED ("yup lock it in"). The approved baseline is commit
7936f7e73fe9d28295715a48b65ca8a0998659c9 on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42498533084. Do not change its layout,
tabs, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: only proven locations are counted (install folder,
mods in it or tied by Steam Workshop ID, Steam shader cache by app ID, Steam per-game screenshots, folders
the owner links), saves and configs are never matched by name, Cleanup Suggestions hand off to the
owning tab and never delete, and nothing is called safe to remove. The next tab's lock must freeze Game
DNA against this commit.

Undo Center: OWNER SIGNED OFF AND LOCKED ("lock it in"). The approved baseline is commit
e96fd44bf86d79a882e42f34b210a4783fe7ce63 on branch `claude/old-files-full-functionality`, Windows run
https://github.com/wrightausername/Game-Grave/actions/runs/42505113783. Do not change its layout,
filters, controls or behavior, or anything that reaches it through shared code, unless the owner
explicitly reopens it. Its honest-claims rules stay: recycled bytes are "Recycled Size", never freed
space; no reversibility percentage; restore only through the protected recovery engine after a fresh
check and confirmation (one matching Recycle Bin item, free original path, never overwrite, batch of
20 at most); "Hide from History" only hides a row through settings and never edits recovery records or
the activity log. "Restore to Custom Location" is not built because the engine restores to the original
path only; adding it needs the owner's explicit approval to change `recovery.py`. The next tab's lock
must freeze Undo Center against this commit.

Next tabs: AI Assistant, Settings and More Tools wait for the owner's photos. Do not start any of them
until the owner sends the photo for that tab and names it. Every locked tab above stays frozen.

Earlier history (kept for context; none of these tabs is open):

Games: the owner reopened it to finish launcher management, ownership/update/playtime
integration and artwork coverage, then fixed its banner artwork. Not signed off; frozen at
the commit above. Account connections, private storage and provider adapters stay Games-only.
Show accurate capabilities and data sources; never substitute fake ownership, playtime or
completion messages.

Overview: preserve exactly as in Windows preview 0.2.12, commit
df6bd6628adf6dd9713fe41235acb618da594574. No further Overview edits and no new signoff.
