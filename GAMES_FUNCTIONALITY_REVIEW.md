Games is the only active tab. The owner reopened it for a triple functionality
check and launcher cards/artwork across Steam, EA, Rockstar, Epic and others.
The original Games photo remains unchanged in assets/references/games.jpg.
The owner has not signed off on Games or authorized moving to another tab.

The photo Games builder and controller are now isolated. Shared photo builders,
artwork, widgets, scan engines, Overview and Ready Room are untouched. The only
shared integration edits delegate Games-specific methods into the new module.
The source guard compares every other desktop source/asset with df6bd662 and
all twelve other tabs in empty/populated states at three sizes: 72 exact image
comparisons, including Overview and the locked Ready Room.

Launcher cards count actual local records and filter their games. Rockstar
gets its own card/badge. The Games-only source adapter reads game-specific
Rockstar and legacy EA registry keys in both Windows views, validates ordinary
existing install directories, excludes launcher/social-club entries and counts
an already accepted install directory once. Extra Games records do not mutate
the common inventory or change the data shown by another tab.

Cards preserve launcher identities when downloading artwork. Exact public Steam
title matches can supply covers for EA, Rockstar, Epic, Ubisoft, GOG, Xbox,
Battle.net and other verified installations. Existing chosen/local/cached
covers work offline; custom covers, explicit artwork IDs, reset, retry and
cancel remain available from Game options. No automatic network requests are
made by drawing Games. A real public-service probe successfully downloaded
Red Dead Redemption 2 artwork for a Rockstar record and read it back offline.
The record stayed Rockstar and gained no Steam action capability.

Right-click selects the game under the pointer. Favorites survive a fresh app
instance through the existing preferences file. Search handles multiple words
across title, launcher and install path. Exact launcher selection clears a
previous launcher-card filter. Steam Play/Verify/DLC revalidate installation
evidence before dispatch. Epic uses its own launch URI. Other Play actions
offer an EXE chooser, retain/revalidate that choice and let cancel exit safely.
Steam uninstall uses Steam's dialog after confirmation; no game is removed by
Game Grave. Artwork download cancellation and page/window lifetime are scoped
to Games, and artwork never publishes into another tab's image service.

Validation runs actual Qt events on disposable mixed-launcher installations.
It covers ten launcher cards, six tabs, six chips, all six sorts, card favorites,
restart persistence, search, launcher choice, Steam/Epic/EA launch dispatch,
Steam verify/DLC/uninstall, non-Steam guidance, correct context selection,
artwork choose/reset/download/offline/corrupt/cancel, failed preference writes,
stale manifests, folders, Save Vault entry, Game DNA/Mods navigation, grid/list,
the final game in a 1,003-game library, Scan PC and the narrow Details drawer.
There are 65 journeys per process, run in three fresh processes (195 checks).
The existing local unit suite passes 527 tests with one platform skip.
The existing photo functionality and all-route geometry smoke also pass.
Native Windows repeats the matrix and locked-tab comparisons before packaging.

Limits are explicit: these are agent-run user-style checks, not human participant
testing or inspection of the owner's PC. OS launch calls are intercepted in QA;
no real game is launched, repaired or uninstalled. Non-Steam repair/DLC/uninstall
use native-launcher guidance where no verified direct shortcut exists. No
online library ownership, update state or unsupported playtime is invented.
Unknown titles without a verified cover retain a fallback and can be assigned
artwork manually; this preview does not promise official artwork for every
possible title. Captures use disposable reference/synthetic covers, not the
owner's personal library. Windows bundle Build-Info and checksums identify the
actual tested source and executables; passing checks does not lock the tab.
