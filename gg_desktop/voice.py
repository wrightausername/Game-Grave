"""Game Grave's editorial voice.

Short, useful sentences, written for someone who actually plays games.
The personality never replaces evidence, consent, or the exact meaning of
a scan result. No random quips, fake confidence scores, or unearned claims.
"""

# Keep these consistent across the hero, sidebar, and discovery workspaces.
# Titles still identify the feature for accessibility and navigation.
PAGE_LANGUAGE = {
    "Overview": (
        "YOUR PC, WITHOUT THE GUESSWORK",
        "Keep the games. Know what's taking space.",
    ),
    "Ready Room": (
        "GOOD TO HAVE YOU BACK",
        "Your library, the games you play, and what's changed.",
    ),
    "Games": (
        "THE WHOLE LIBRARY",
        "Steam, Epic, Rockstar and the rest. One place to look.",
    ),
    "Mods": (
        "THE MOD SHELF",
        "Mod folders have a habit of spreading. Here's where to keep tabs.",
    ),
    "Old Files": (
        "THE DUSTY CORNER",
        "Those downloads you meant to clean up six months ago? Start here.",
    ),
    "Other Storage": (
        "WHERE DID THE SPACE GO?",
        "What's taking the rest of your drive? Choose somewhere to look.",
    ),
    "Captures": (
        "THE GOOD PARTS, ON REPEAT",
        "You took the screenshots. Now you can actually enjoy them.",
    ),
    "Graveyard": (
        "NOT QUITE GONE",
        "Leftovers turn up here. Nothing leaves without your say-so.",
    ),
    "Game DNA": (
        "EVERY GAME LEAVES A TRAIL",
        "Follow an install through the files we can actually tie to it.",
    ),
    "Undo Center": (
        "SECOND THOUGHTS?",
        "Check what Windows can still bring back.",
    ),
    "Settings": (
        "MAKE IT YOURS",
        "Change the look, the rules, and what Game Grave scans.",
    ),
}

# Use real state where the text references what was found.
EMPTY_STATES = {
    "Mods": (
        "Nothing on the radar.",
        "We didn't find mod folders in the places checked. "
        "That doesn't mean your mods disappeared. Try another scan or "
        "point Game Grave at a library you use.",
    ),
    "Graveyard": (
        "Nothing to bury.",
        "No candidates turned up in this scan. Your games and saved files "
        "are right where you left them.",
    ),
    "GraveyardPartial": (
        "Not the whole picture.",
        "Some places couldn't be checked. A quiet Graveyard doesn't mean "
        "your PC is spotless; read the scan notes before calling it done.",
    ),
    "Captures": (
        "No screenshots in sight.",
        "We haven't found game captures in the folders checked. "
        "You can add your capture folder in Settings.",
    ),
    "Undo Center": (
        "A clean slate.",
        "No Game Grave recycle actions have been logged here yet. "
        "Windows manages the Recycle Bin separately.",
    ),
}

# Deliberately plain microcopy on buttons; there is no mystery meat navigation.
ACTIONS = {
    "scan_again": "Scan again",
    "choose_library": "Add a game folder",
    "mod_sources": "Show every mod location",
    "why_flagged": "Why is this here?",
    "show_breakdown": "Show the breakdown",
    "open_folder": "Open its folder",
    "view_saves": "View protected saves",
}
