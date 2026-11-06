# Ready Room artwork and type

The small PNG assets are extracted from the 1280 × 720 Ready Room reference image
supplied by the product owner for this implementation. They preserve the exact
gaming-room illustration, card-header landscapes and game
thumbnails from that reference. Game names and logos remain their respective
owners' marks. These are reference-derived assets, not independently licensed
replacement game artwork.

Only decorative artwork and thumbnails are images. Ready Room search, counters,
headings, rows, badges, buttons and the health gauge are actual Qt widgets or
vector drawing. The gaming-room illustration excludes the reference's search and
window controls when rendered. All assets load locally, including in the existing
PyInstaller `gg_desktop/assets` bundle.

These assets and their stylesheet are confined to Ready Room. The original
application sidebar, native window frame, toolbar, global theme, startup page and
all other screens retain their previous presentation and behavior.

`RobotoCondensed.ttf` is Roboto Condensed, distributed under the SIL Open Font
License in `OFL.txt`. Source:
https://github.com/google/fonts/tree/main/ofl/robotocondensed

The reference's sample patch notices, hours, backup count and health score are
available only in the explicit `--ready-room-reference` design mode. That mode
has a visible sample-data marker. The ordinary dashboard uses scan evidence and
shows unsupported values as unknown.
