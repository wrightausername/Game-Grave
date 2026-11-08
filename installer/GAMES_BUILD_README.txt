GAME GRAVE - GAMES MULTI-LAUNCHER WINDOWS PREVIEW 0.2.15

This revision fixes only the Games banner artwork: the original scene aligns
continuously across the header, with its aspect ratio preserved. The banner
size, labels, controls, cover grid and library functionality are unchanged.

Only Games is reopened. Overview remains at preview 0.2.12; Ready Room and
all twelve other tabs retain their protected source and rendered baselines.
The owner's locked photos remain the visual foundation. The owner decides
when Games is complete; passing checks does not constitute owner signoff.

LIBRARIES
Use the small (...) Library options button, then Connect game libraries.
Sign in to Steam, Epic, EA or GOG on its official website inside the app.
Passwords stay on that website. Windows protects the saved connection with
current-user DPAPI. The embedded browser is off the record. Refresh, switch
account, cancel and disconnect are available. No account sign-in is required
to display the installations found by Scan PC.

Connected accounts populate owned games, including Not Installed. Install
opens the exact provider's installer. Ownership matches verified product IDs
or a link you explicitly choose, never a similar title. Favorites survive
the transition from an owned card to its installed record.

Steam, Epic and GOG supply available account playtime. Steam can also supply
its selected local profile. Other games show time tracked on this PC while
Game Grave is open, with the source named in the inspector. Imported totals
and tracked sessions are reconciled without double-counting. Steam update
flags and connected Epic live versions populate Updates. A plus sign and
tooltip identify installations whose update status remains launcher-managed.

Other launcher cards include Rockstar, Ubisoft, Battle.net, Xbox PC, GOG,
Riot and custom libraries when installations are detected. Rockstar,
Ubisoft, Battle.net and Xbox do not yet have account-wide owned/uninstalled
connectors. Their native controls and local tracked playtime remain usable.

NATIVE ACTIONS
Play and Install use verified provider identities where available. A chosen
game EXE must remain inside the installation and is revalidated before use.
Repair, DLC and uninstall open a direct native control or the real launcher
library when no direct command exists. Buttons identify these handoffs.
GOG and matching registered Windows games can invoke their native
uninstallers. Uninstall requires confirmation and revalidation. Game Grave
does not remove game files itself or report a handed-off request completed.

ARTWORK
Local, chosen and cached covers work offline. Missing covers automatically
try connected catalogue artwork, an exact Steam match and an exact Wikipedia
game page. You can disable automatic downloads, retry them, choose a local
image or set an artwork-only Steam ID without changing launch identity.
Images receive no account credentials. Unknown/unavailable posters retain
a labeled cover or game icon; official artwork is not guaranteed for every
possible custom title.

VALIDATION
The Windows workflow runs real Qt mouse/keyboard journeys in three fresh
processes, provider contract and native-dispatch tests, current-user DPAPI
storage checks, real QtWebEngine rendering/cancellation, 72 exact pixel
comparisons for the twelve other tabs, and isolated installer checks.
Authentication responses and launcher dispatch are intercepted in automated
tests: no personal account or installed game is started, repaired or removed.
Actual account access must be verified by signing in on the owner's PC.

Screenshots use disposable QA installations and explicit connected-library
fixtures. The mixed-launcher image uses original reference crops and two
public game-art test fixtures. These are not the owner's library or scan.
Build-Info.txt identifies the source commit and Windows build.
SHA256SUMS.txt identifies the standalone EXE and installer.
This is an unsigned engineering preview.
