"""What Game Grave's own features do, in plain words, for the AI Assistant and for hover text. No Qt, no scan data.

Every sentence here describes behaviour that exists in the code today (see resurrection_v2.py, resurrection_lab.py,
blackbox_core.py and the tab subtitles). Nothing here calls a feature "safe": each entry says what it reads, what it
writes, and what it never does.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Feature:
    key: str
    title: str
    keywords: tuple          # lower-case phrases; a single word must match a whole word
    what: str                # what it is, one or two sentences
    steps: tuple = ()        # what you can do with it, one short line each
    never: str = ""          # what it will not do
    where: str = ""          # how to open it
    tab: str = ""            # a tab name for the hand-off button
    hover: str = ""          # a short, specific tooltip for the feature's own button or tile


FEATURES = (
    Feature(
        "resurrection_kit", "Resurrection Kit",
        ("resurrection", "ressurection", "resurection", "kit", "kits", "resurrection kit", "ggkit"),
        "A Resurrection Kit is a single ZIP file that holds one game's whole install, its saves, its load-order file "
        "and, if you use Mod Organizer 2, its profile and mods, so the game can be restored and played without "
        "downloading or setting it up again. A small manifest file sits next to it, and Game Grave checks the "
        "finished ZIP against that manifest.",
        ("Set up a kit for a game (easiest): pick the game, see what it found and how big it is, tick or untick parts, "
         "choose a folder and press Create. It shows progress and you can cancel.",
         "Restore a game from a kit: pick the kit and a library folder. The install comes back as a new folder, and "
         "saves and load order go back to their original place only where nothing exists yet.",
         "Rehearse recovery in isolation: extract into a temporary folder and compare file hashes. It never launches "
         "the game.",
         "Check missing pieces: a diagnostic from the kit's own contents, not proof that a kit is complete.",
         "Compare two kit snapshots, browse Time Machine snapshots, or prepare a portable PC-to-PC kit."),
        "There is no size limit, only your free space. It never overwrites a file, never changes your game, and every "
        "action asks first. Launcher accounts and licences are not part of a kit, so a launcher may sign in or "
        "re-verify the files the first time you start the restored game. Saves are only included when the save "
        "scanner labeled the folder with that exact game or you linked it in Game DNA.",
        "More Tools, then Backup and Recovery, then Resurrection Kit.", "More Tools",
        "Saves a game's whole install, saves, load order and mods into one verified ZIP you can restore later. Opens "
        "a menu to set up, restore, inspect, rehearse, compare or transfer kits. Nothing changes until you confirm."),
    Feature(
        "save_vault", "Save Vault",
        ("save vault", "savevault", "game backup", "save backup", "mod backup", "back up my saves", "backup my saves"),
        "Save Vault copies one folder you choose, such as a save or profile folder, into a new ZIP and verifies the "
        "ZIP afterwards. Game Backup, Save Backup and Mod Backup in More Tools all use it.",
        ("Choose the folder, choose a new ZIP name, confirm, and it runs in the background.",),
        "It never deletes or overwrites your source files and refuses to write over an existing ZIP. Close the game "
        "first so the files are consistent.",
        "More Tools, then Backup and Recovery.", "More Tools",
        "Copies the one folder you pick into a new, verified ZIP. The original files are never touched."),
    Feature(
        "black_box", "Black Box",
        ("black box", "blackbox", "crash report", "crash log", "crashed", "crashing", "why did my game crash"),
        "Black Box gathers what Windows and the game folder recorded about a crash into one report you can read, "
        "copy or save. You pick the game and press Build report.",
        ("It reads the Windows Application log for crashes of that game.",
         "It lists crash logs and dump files found in the game folder and recently changed files there."),
        "It does not say why the game crashed, does not go online and changes nothing on your PC.",
        "Ready Room, then Black Box. Open the panel with the Open button.", "Ready Room",
        "Builds a crash report for one game from the Windows Application log and the game folder. Read-only."),
    Feature(
        "exhume", "Exhume",
        ("exhume", "driver rollback", "older driver", "graphics driver", "roll back driver"),
        "Exhume looks for older graphics drivers that Windows still has stored and lets you bring one back.",
        ("Checking only reads the driver list.", "Rolling back asks first and may need administrator rights."),
        "Checking changes nothing.",
        "Ready Room, then Exhume.", "Ready Room",
        "Lists older graphics drivers Windows still has stored. Checking changes nothing; a rollback asks first."),
    Feature(
        "autopsy", "Autopsy",
        ("autopsy", "frame time", "frametime", "frame-time"),
        "Autopsy runs by itself and compares your newest frame-time captures, keeping ten.",
        (), "It does not capture frames itself.", "Ready Room, then Autopsy.", "Ready Room",
        "Compares your newest frame-time captures. Runs automatically and keeps ten."),
    Feature(
        "soulbind", "Soulbind",
        ("soulbind",),
        "Soulbind lets you set your game preferences once and apply them to every game Game Grave can verify.",
        ("A preference counts for a game only when its exact key is found in that game's real settings file.",
         "Apply keeps a dated backup of the file first, and Undo puts it back if the file has not changed since.",
         "The Soulbind new games switch in Settings applies your preferences to newly installed games after a scan, "
         "once their settings file exists. It is off until you turn it on."),
        "It never touches a game it cannot verify and never runs while a game is running.",
        "Ready Room, then Soulbind.", "Ready Room",
        "Set your game preferences once and apply them to every game Game Grave can verify."),
    Feature(
        "squad_sync", "Squad Sync",
        ("squad sync", "squadsync", "squad code", "co-op mods", "coop mods", "match mods with a friend"),
        "Squad Sync gets a co-op group onto the same mods. One person hosts and shares a code; everyone else pastes "
        "it and Game Grave shows what they are missing and helps get it.",
        ("Hosting: pick the game, press Copy squad code, and paste it to your friends in Discord or a text. For a "
         "long code, press Save code as file and send the file.",
         "Joining: copy the code your friend sent and press Paste a friend's code. Game Grave reads it from your "
         "clipboard, even inside a whole chat message. Or press Open a code file.",
         "Get what's missing opens each missing Steam Workshop item in Steam, where you press Subscribe. With Nexus "
         "Premium it downloads the missing Nexus files and installs the plain zip ones into Mod Organizer 2, "
         "switched off. Mods with an installer that asks questions, and 7z or rar files, wait in Mod Organizer 2's "
         "Downloads tab.",
         "Make squad profile adds a NEW Mod Organizer 2 profile with your friend's mods switched on in your "
         "friend's order. You pick it in Mod Organizer 2."),
        "The code holds mod names and Workshop numbers only: no files, paths or user name. Squad Sync never "
        "overwrites a mod and never changes your own profile. Plugin order is not part of a code.",
        "Ready Room, then Squad Sync.", "Ready Room",
        "Reads your mod setup so you can compare it with a friend's."),
    Feature(
        "undo_center", "Undo Center",
        ("undo center", "undo centre"),
        "Undo Center checks whether Windows still holds a file Game Grave recycled, and lets you approve a restore.",
        (), "A recorded recycle is not a promise Windows can restore it; it checks again before any restore.",
        "Undo Center in the sidebar.", "Undo Center",
        "Checks whether Windows still holds a recycled file, then lets you approve restoring it."),
    Feature(
        "graveyard", "Graveyard",
        ("graveyard",),
        "Graveyard is where you review apparent storage, see which folders are protected and approve individual "
        "Recycle Bin moves.",
        (), "Nothing moves until you approve that one item.", "Graveyard in the sidebar.", "Graveyard",
        "Review apparent storage and approve individual Recycle Bin moves."),
    Feature(
        "old_files", "Old Files",
        ("old files", "old file", "file scan"),
        "Old Files lists older ordinary files inside the folder you select. File age does not prove a file is unused.",
        (), "It never removes a folder automatically and never touches installed games or managed profiles.",
        "Old Files in the sidebar.", "Old Files",
        "Lists older ordinary files in the folder you selected. Age does not prove a file is unused."),
    Feature(
        "game_dna", "Game DNA",
        ("game dna", "dna"),
        "Game DNA shows how a game's verified files relate to its mods, saves, captures and unknown leftovers.",
        (), "", "Game DNA in the sidebar.", "Game DNA",
        "Shows how a game's verified files relate to its mods, saves and captures."),
    Feature(
        "mods_library", "Mods Library",
        ("mods library", "mod radar", "mod conflicts", "conflicts tab"),
        "The Mods tab lists mod locations the scan found with the evidence for each. Cards that Game Grave flags "
        "offer Review or Details.",
        (), "Game Grave never installs, enables, disables or changes mods.", "Mods in the sidebar.", "Mods",
        "Lists detected mod locations with the evidence behind each. Game Grave never changes mods."),
    Feature(
        "mod_bisect", "Mod Bisect",
        ("bisect", "mod bisect", "which mod is crashing", "which mod crashes", "find the crashing mod",
         "find the bad mod", "mod causing the crash", "mod causing crashes"),
        "Mod Bisect hunts for the mod, or group of mods, that makes a game crash. It proposes one test at a time "
        "(exactly these mods on), you launch the game yourself and answer crashed, fine or not sure, and it narrows "
        "the list until your own launches prove the cause.",
        ("Tell it when the crashes started or which mods you added last. Clues only order the search; a wrong clue "
         "costs launches, never the answer.",
         "With Mod Organizer 2 it writes each test into a copy of your profile named GG Bisect. Other mod managers get "
         "a list to apply by hand.",
         "It handles one mod, a pair, a group, or several separate causes, and crashes that do not happen every time."),
        "It never launches the game, never changes your original profile and never deletes anything. If it cannot "
        "prove a cause within its launch limit it says undetermined and shows what it narrowed to.",
        "Mods, then the Bisect tab.", "Mods",
        "Guided hunt for the mod that makes a game crash. You launch and answer; it narrows the list."),
    Feature(
        "hardware", "Hardware",
        ("hardware", "hardware tab", "upgrade advisor", "pc specs", "my specs", "what should i upgrade"),
        "Hardware shows the parts Windows reports for this PC, live load, and upgrade notes based on play sessions "
        "you record.",
        ("Your PC: parts as cards, live gauges and charts, drives, Copy Specs and Save as .txt.",
         "Upgrade Advisor: press Record Play Session while you play. Notes appear after at least 3 sessions of at "
         "least 2 minutes, and each says what was measured and what it cannot tell."),
        "It never shows a CPU temperature, a frame rate or a price, and it does not tell you what to buy.",
        "Hardware in the sidebar.", "Hardware",
        "The parts Windows reports for this PC, live load, and upgrade notes from sessions you record."),
    Feature(
        "updates", "Check for Updates",
        ("check for updates", "updater", "update game grave", "new version", "new build", "latest version",
         "latest build", "how do i update"),
        "Check for Updates in Settings asks GitHub whether a newer Game Grave build exists and tells you in words. "
        "Open Updater starts the separate Game Grave Updater, which downloads and installs after its own "
        "confirmation.",
        ("Settings, version box, Check for Updates.",
         "The Check for updates on launch switch asks once each time Game Grave starts. It is off until you turn it on."),
        "The check itself downloads and installs nothing. If this PC has no record of which build is installed, it "
        "says so instead of guessing.",
        "Settings, in the version box.", "Settings",
        "Asks GitHub whether a newer build exists. Downloads and installs nothing."),
    Feature(
        "hash_checker", "Hash Checker",
        ("hash checker", "checksum", "sha-256", "sha256"),
        "Hash Checker computes the SHA-256 checksum of any file you choose and compares it with one you paste.",
        (), "A match proves the bytes are identical, not that the file is good.", "More Tools, then Utilities.",
        "More Tools",
        "Computes a SHA-256 checksum of a file you choose. Read-only."),
    Feature(
        "data_used", "Data Used",
        ("data used",),
        "Data Used is the list of scan results this assistant may read: game library, storage scans, cleanup history, "
        "mods inventory and captures index. Turn a source off and I will not use it.",
        (), "", "The Data Used panel on this page.", "AI Assistant",
        "Choose which scan results the assistant may read."),
)

BY_KEY = {f.key: f for f in FEATURES}


def hover(key, fallback=""):
    """The tooltip for a feature's button. Falls back to the caller's own text for keys not described here."""
    feature = BY_KEY.get(key)
    return feature.hover if feature and feature.hover else fallback


def _padded(text):
    return " " + re.sub(r"[^a-z0-9.' -]+", " ", text.casefold()) + " "


def match(question):
    """(feature, matched phrase) for the question, or (None, ""). The longest phrase wins so 'save vault' beats 'save'."""
    text = _padded(question)
    best, phrase = None, ""
    for feature in FEATURES:
        for word in feature.keywords:
            if f" {word} " in text and len(word) > len(phrase):
                best, phrase = feature, word
    return best, phrase


def find_feature(question, game_name=""):
    """The feature the question is about, or None. A phrase that is only there as part of the named game's title
    ("Graveyard Keeper", "First Aid Kit Simulator") does not count."""
    feature, phrase = match(question)
    if feature is None:
        return None
    if game_name and f" {phrase} " in _padded(game_name):
        without = _padded(question).replace(_padded(game_name).strip(), " ")
        again, _ = match(without)
        return again
    return feature


def explain(feature):
    """Plain text for the assistant: what it is, what you can do, what it never does, where to find it."""
    parts = [f"{feature.title}: {feature.what}"]
    if feature.steps:
        parts.append("\n".join("• " + s for s in feature.steps))
    if feature.never:
        parts.append(feature.never)
    if feature.where:
        parts.append("Where: " + feature.where)
    return "\n\n".join(parts)
