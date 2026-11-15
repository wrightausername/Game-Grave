"""What Game Grave's own features do, in plain words, for the AI Assistant and for hover text. No Qt, no scan data.

Every sentence here describes behaviour that exists in the code today (see resurrection_v2.py, resurrection_lab.py,
blackbox_core.py and the tab subtitles). Nothing here calls a feature "safe": each entry says what it reads, what it
writes, and what it never does.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
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
    opens: str = ""          # what "Open it" opens: tool:<key>, kit:easy, tab:<Tab>[/<inner tab>], bisect, tour
    do: str = ""             # the request "Do it for me" sends to the assistant's automation, when it can run it


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
        "Fix Kit, then Resurrection Kit (also in Toolbox, Backups).", "Fix Kit",
        "Saves a game's whole install, saves, load order and mods into one verified ZIP you can restore later. Opens "
        "a menu to set up, restore, inspect, rehearse, compare or transfer kits. Nothing changes until you confirm."),
    Feature(
        "save_vault", "Save Vault",
        ("save vault", "savevault", "game backup", "save backup", "mod backup", "back up my saves", "backup my saves"),
        "Save Vault copies one folder you choose, such as a save or profile folder, into a new ZIP and verifies the "
        "ZIP afterwards. Game Backup, Save Backup and Mod Backup in Toolbox all use it.",
        ("Choose the folder, choose a new ZIP name, confirm, and it runs in the background.",),
        "It never deletes or overwrites your source files and refuses to write over an existing ZIP. Close the game "
        "first so the files are consistent.",
        "Toolbox, then Backups.", "More Tools",
        "Copies the one folder you pick into a new, verified ZIP. The original files are never touched."),
    Feature(
        "black_box", "Black Box",
        ("black box", "blackbox", "crash report", "crash log", "crashed", "crashing", "why did my game crash"),
        "Black Box gathers what Windows and the game folder recorded about a crash into one report you can read, "
        "copy or save. You pick the game and press Build report.",
        ("It reads the Windows Application log for crashes of that game.",
         "It lists crash logs and dump files found in the game folder and recently changed files there."),
        "It does not say why the game crashed, does not go online and changes nothing on your PC.",
        "Fix Kit, then Black Box. Click the panel to open it.", "Fix Kit",
        "Builds a crash report for one game from the Windows Application log and the game folder. Read-only."),
    Feature(
        "exhume", "Exhume",
        ("exhume", "driver rollback", "older driver", "graphics driver", "roll back driver"),
        "Exhume looks for older graphics drivers that Windows still has stored and lets you bring one back.",
        ("Checking only reads the driver list.", "Rolling back asks first and may need administrator rights."),
        "Checking changes nothing.",
        "Fix Kit, then Exhume.", "Fix Kit",
        "Lists older graphics drivers Windows still has stored. Checking changes nothing; a rollback asks first."),
    Feature(
        "autopsy", "Autopsy",
        ("autopsy", "frame time", "frametime", "frame-time"),
        "Autopsy runs by itself and compares your newest frame-time captures, keeping ten.",
        (), "It does not capture frames itself.", "Fix Kit, then Autopsy.", "Fix Kit",
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
        ("squad sync", "squadsync", "squad code", "co-op mods", "coop mods", "match mods with a friend", "share my mods",
         "share mods", "my mods with a friend", "same mods as my friend", "mods with friends"),
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
        ("undo center", "undo centre", "restore something", "get back a file", "get my file back", "undo a delete",
         "recover a file", "restore a file", "restore what"),
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
        (), "The Mods tab never installs, enables, disables or changes mods. The only installs are Squad Sync's: missing "
        "plain zip mods from a friend's code, added to Mod Organizer 2 as new, switched-off mods.", "Mods in the sidebar.", "Mods",
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
        "drivers_startup", "Drivers & Startup",
        ("drivers", "driver update", "driver updates", "update drivers", "update my drivers", "outdated drivers",
         "startup apps", "startup programs", "start with windows", "starts with windows", "startup", "boot faster"),
        "Drivers & Startup is the third tab inside Hardware. It checks Windows Update for driver updates and installs them, "
        "and lists the apps that start with Windows so you can switch off the ones you don't need.",
        ("Check for driver updates asks Windows Update which driver updates it offers this PC. Update all installs the "
         "ticked ones after Windows asks for administrator permission.",
         "Oldest drivers lists the oldest game-related drivers. An old date is a hint, not proof a newer one exists.",
         "Graphics card makers often have newer drivers than Windows Update; the tab links to their official app.",
         "Starts with Windows lists the same apps as Task Manager's Startup apps, including Store apps, plus scheduled "
         "tasks that run at sign-in, each with an on/off switch. Apps for all users ask for administrator permission.",
         "When a driver needs it, Restart now restarts Windows after 60 seconds, and Cancel restart stops it."),
        "It never deletes a startup entry or an app, and drivers come only from Windows Update. A restart may be needed "
        "after a driver update.",
        "Hardware, then Drivers & Startup.", "Hardware",
        "Driver updates from Windows Update, and on/off switches for apps that start with Windows."),
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
        (), "A match proves the bytes are identical, not that the file is good.", "Toolbox, then Files.",
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

FEATURES = FEATURES + (
    Feature(
        "local_ai", "Local AI",
        ("local ai", "local model", "ai model", "download the ai", "download ai", "offline ai", "llm", "qwen",
         "llama.cpp", "language model"),
        "Local AI is an optional AI model you can download in the AI Assistant tab. It runs on this PC only and writes "
        "the assistant's answers in plain language from the same facts the built-in answers use.",
        ("Pick Small (1.3 GB), Medium (2.5 GB, recommended) or Large (5 GB), then press Download. Game Grave asks first.",
         "The model (Qwen3, from Hugging Face) and llama.cpp's engine (from GitHub) are checked against their published "
         "SHA-256 before use.",
         "Switch it off any time to go back to the built-in answers; Remove deletes it.",
         "It pauses while a game is running and stops after a few idle minutes."),
        "Nothing you ask leaves this PC, and a reply that breaks Game Grave's rules is never shown; the built-in "
        "answer is shown instead.", "AI Assistant, Local AI panel on the right.", "AI Assistant",
        "Optional AI model that runs on this PC only."),
    Feature(
        "automation", "Automation",
        ("automation", "automate", "routine", "routines", "run tools", "run the tools", "do it for me", "autopilot",
         "schedule", "scheduled"),
        "Automation lets the assistant run Game Grave's own tools when you ask, like \"get my PC ready to play\", "
        "\"clean up temp files\" or \"update my drivers\". It is off until you switch on \"Let the assistant run tools\".",
        ("Ask for something and I show a plan: checks (they only read) run straight away, and every change is listed.",
         "Untick anything you don't want, then press Run all. One confirmation names every change.",
         "Add a schedule (\"every Sunday at 9pm clean temp files\") and press Save as routine. Its checks run on time; "
         "its changes wait for your OK in a notice.",
         "Nothing runs while a game is open, and every change is written to the activity log."),
        "It only uses tools from Game Grave's fixed list and never types a command of its own. Closing apps and "
        "switching off startup apps always need you there.", "AI Assistant, Automation panel on the right.",
        "AI Assistant", "Let the assistant run Game Grave's own tools when you ask."),
)

# Every tool in the app, so "how do I ..." always has a walkthrough (owner, 2026-11-14: "if somebody doesn't know how to
# do any of these tools or use them it should be easy enough for them to ask and it implement what ever they want").
FEATURES = FEATURES + (
    Feature(
        "windows_cleanup", "Windows Cleanup",
        ("windows cleanup", "temp files", "temporary files", "temp folder", "clear temp", "clean temp", "junk files",
         "delete temp"),
        "Windows Cleanup deletes temporary files that Windows and your apps left behind and that have not changed for "
        "2 days.",
        ("Open it: Game Grave looks through Windows' temp folders first and shows how many old files it found and their "
         "size. Nothing is deleted yet.",
         "Check the list, then press Delete. One confirmation names the folders.",
         "Files in use are skipped and every file is checked again just before it is deleted.",
         "Or just ask me \"clean up temp files\" and I'll do the same with one OK."),
        "These files are deleted for good, not sent to the Recycle Bin.", "Toolbox, Windows section.", "More Tools",
        "Deletes old temporary files after you confirm."),
    Feature(
        "game_optimizer", "Game Optimizer",
        ("game optimizer", "game mode", "background recording", "game bar recording", "game dvr", "power plan",
         "high performance", "optimize windows for gaming", "windows settings for games"),
        "Game Optimizer switches three Windows settings that can help games: Game Mode on, background recording off, "
        "and the High performance power plan. It saves your current values first, so Undo puts them back exactly.",
        ("Open it: each setting shows how it is set now (On, Off, or \"Windows decides\").",
         "Tick the ones you want and press Apply. One confirmation shows the exact change.",
         "Undo my changes puts every setting back the way it was.",
         "Or ask me \"turn on game mode and turn off background recording\"."),
        "It does not promise more frames; it only changes those three settings.", "Toolbox, Windows section.",
        "More Tools", "Three Windows settings for games, with Undo."),
    Feature(
        "memory_optimizer", "Memory Optimizer",
        ("memory optimizer", "free up memory", "free memory", "free up ram", "close apps", "close programs",
         "using memory", "using ram", "memory hog", "too much memory", "too much ram"),
        "Memory Optimizer lists the apps open right now, biggest memory use first, so you can close the ones you are not "
        "using before you play.",
        ("Open it: the list shows each app and how much memory it uses, and a badge shows total memory use.",
         "Tick the apps to close and press Close. Each one is asked to close normally, like pressing its X, so "
         "anything unsaved can still ask you first.",
         "Or ask me \"close discord and chrome\", or \"get my PC ready to play\"."),
        "Windows itself and Game Grave are never listed, and nothing is forced closed.", "Toolbox, Windows section.",
        "More Tools", "Close apps you're not using, biggest first."),
    Feature(
        "command_runner", "Command Runner",
        ("command runner", "run a command", "run command", "cmd", "command prompt", "ipconfig", "flush dns"),
        "Command Runner runs one Windows command and shows what it prints.",
        ("Pick a ready-made command (network details, flush DNS and others) or type your own.",
         "Press Run. You see the exact line and confirm before it runs.",
         "Exit code 0 usually means it worked; any other code means read the output."),
        "It stops after 2 minutes. I never run commands for you; you type or pick them here.", "Toolbox, Files section.",
        "More Tools", "Run one Windows command after you confirm it."),
    Feature(
        "file_associations", "File Associations",
        ("file associations", "file association", "default app", "default apps", "opens with", "open with",
         "which app opens"),
        "File Associations shows which app opens a type of file, such as .zip or .pak.",
        ("Pick or type a file type and press Look up.",
         "To change it, press Change it in Windows: Windows only lets you change this yourself, so Game Grave opens the "
         "right Windows page."),
        "Nothing is changed here.", "Toolbox, Files section.", "More Tools", "See which app opens a file type."),
    Feature(
        "junction_manager", "Junction Manager",
        ("junction manager", "junction", "junctions", "symlink", "symbolic link", "folder link", "folder links"),
        "Junction Manager shows folder links (junctions), such as a game folder that really lives on another drive, and "
        "can add or remove them.",
        ("Press Choose folder and pick where to look. Each link shows where it points; broken ones are called out.",
         "Remove link deletes only the link, never the folder it points to.",
         "Create junction asks for a name and the folder to point to, then confirms."),
        "Real folders and your Never Touch places are refused.", "Toolbox, Files section.", "More Tools",
        "See, add or remove folder links."),
    Feature(
        "reports", "Reports",
        ("report", "reports", "export", "export my games", "list of my games", "game list", "mod list",
         "system report", "csv"),
        "Reports save a list of your games, your mods or your PC's details as a file you can keep or share.",
        ("Press Games report, Mods report or System report.",
         "Choose where to save it. The file opens in Excel or any text editor."),
        "Reports only read what Game Grave already scanned.", "Toolbox, Reports section.", "More Tools",
        "Save a list of games, mods or PC details."),
    Feature(
        "other_storage", "Other Storage",
        ("other storage", "shader cache", "shader caches", "launcher cache", "launcher caches", "caches", "cache folders"),
        "Other Storage finds game-related folders outside your games: shader caches, launcher caches and logs, crash "
        "dumps and settings folders, with their size.",
        ("Press Scan Other Storage. It only reads known locations.",
         "Each folder says what it is and whether it is Review only, Reviewable or Protected.",
         "Small launcher cache and log folders can go to the Recycle Bin after a confirmation and a file-by-file check.",
         "Or ask me \"scan other storage\"."),
        "Settings and saves are never removable, and driver and Steam caches are review only.", "Clean Up, Other Storage.",
        "Other Storage", "Find caches, logs and other game data."),
    Feature(
        "captures", "Captures",
        ("captures tab", "my captures", "screenshots tab", "recordings tab", "find my screenshots", "find my recordings"),
        "Captures finds your game screenshots and recordings, groups them by game when it can prove which game, and finds "
        "duplicates.",
        ("Press Scan Captures. It reads your capture folders.",
         "Filter by game or type, open a picture, or find duplicates and look-alikes.",
         "Removal sends files to the Recycle Bin after a confirmation and a check.",
         "Or ask me \"scan my captures\"."),
        "A game is named only when Game Grave can prove it.", "Library, Captures.", "Captures",
        "Your screenshots and recordings, by game."),
    Feature(
        "games_tab", "Games",
        ("games tab", "my library", "game library", "launch a game", "uninstall a game", "favorite"),
        "Games shows every installed game from every launcher in one place, with size, last played and launcher.",
        ("Search, sort and filter by launcher, Installed, Favorites or Recently played.",
         "Pick a game for Play, Verify, DLC, Uninstall and Open folder. Those go through the game's own launcher."),
        "Game Grave never uninstalls a game itself; the launcher does it.", "Library, Games.", "Games",
        "All your games from every launcher."),
    Feature(
        "my_mods", "My Mods",
        ("my mods", "turn off a mod", "turn on a mod", "disable a mod", "enable a mod", "load order", "reorder mods",
         "mod order", "workshop", "steam workshop", "workshop items"),
        "My Mods is the simple Mods screen: one game at a time, each mod by its real name with an on/off switch, a list of "
        "what needs you with fix buttons, and Steam Workshop items with their real titles.",
        ("Pick the game (and the Mod Organizer 2 profile if you have several).",
         "Flip a mod's switch, or drag it to change the order. Each change saves a snapshot first, and Undo puts it back.",
         "What needs you lists missing masters, updates and clashes, with a button to fix what can be fixed.",
         "Or ask me \"turn off <mod name>\" or \"turn on <mod name>\"."),
        "Changes are refused while Mod Organizer 2 is open, and mod folders are never deleted.", "Library, Mods.",
        "Mods", "Switch mods on and off, reorder, fix problems."),
    Feature(
        "scan_pc", "Scan PC",
        ("scan pc", "scan my pc", "scan my games", "rescan", "full scan", "first scan"),
        "Scan PC reads your drives for games, mods, old files, captures and saves. It only reads.",
        ("Press Scan PC (or F5) on any tab, or ask me \"scan my games\".",
         "The bar at the bottom shows the step, percent and time left. Cancel stops it and keeps your earlier results.",
         "Results stay until you scan again, and the top bar shows when they were taken."),
        "Nothing is changed by scanning.", "Any tab.", "Overview", "Read your drives for games, mods and files."),
    Feature(
        "never_touch", "Never Touch rules",
        ("never touch", "protect a folder", "exclude a folder", "excluded folders", "ignore a folder"),
        "Never Touch rules are folders Game Grave will never remove anything from, whatever a tab finds there. Excluded "
        "folders are left out of scans entirely.",
        ("Open Settings, then Protection.", "Add a folder; each rule is added or removed one at a time with a confirmation."),
        "Import and Reset never remove a rule.", "PC and Help, Settings.", "Settings", "Folders Game Grave never touches."),
    Feature(
        "welcome_tour", "Welcome tour",
        ("welcome tour", "tutorial", "tour", "walkthrough of the app", "show me around", "how does game grave work",
         "what does game grave do"),
        "The welcome tour is a short walk through every part of Game Grave.",
        ("Press the ? at the top right, or Watch the welcome tour in Settings.",
         "Use Next and Back (or the arrow keys); Skip intro closes it."),
        "", "The ? button at the top right.", "Settings", "A short tour of Game Grave."),
    Feature(
        "fix_game", "Fix my game",
        ("fix my game", "won't start", "wont start", "won't launch", "wont launch", "keeps crashing", "game crashes",
         "game won't open", "black screen", "game freezes", "crashes on startup", "crashes to desktop"),
        "Fix my game checks the usual reasons a game won't start or keeps crashing that are not mods, then offers the "
        "fixes. Ask \"fix\" and the game's name, for example \"fix Elden Ring\".",
        ("It reads the crashes Windows recorded for the game (Black Box) and names the file they happened in.",
         "It lists overlays that hook into games (RivaTuner, Overwolf, Discord's overlay and others) and offers to close them.",
         "It checks Microsoft's Visual C++ runtime and the older DirectX files, and checks Windows Update for drivers.",
         "Fixes it can do after Run all and one OK: Steam's own file check, closing overlays, installing Microsoft's "
         "runtime (from Microsoft, signature checked)."),
        "It never says a cause is certain and never deletes a game file. For mod crashes, Mod Bisect finds the mod.",
        "Ask the AI Assistant, or Fix Kit.", "Fix Kit", "Checks why a game won't run and offers the usual fixes."),
)

_GUIDES = {
    # key: (what Open it opens, what Do it for me asks the automation)
    "resurrection_kit": ("kit:easy", ""), "save_vault": ("tool:save_vault", ""), "black_box": ("tab:Fix Kit", ""),
    "exhume": ("tab:Fix Kit", ""), "autopsy": ("tab:Fix Kit", ""), "soulbind": ("tab:Ready Room", ""),
    "squad_sync": ("tab:Ready Room", ""), "undo_center": ("tab:Undo Center", ""),
    "graveyard": ("tab:Graveyard", "scan for leftovers"), "old_files": ("tab:Old Files", ""),
    "game_dna": ("tab:Game DNA", ""), "mods_library": ("tab:Mods", ""), "mod_bisect": ("bisect", ""),
    "hardware": ("tab:Hardware", ""), "drivers_startup": ("tab:Hardware/Drivers & Startup", "check my drivers"),
    "updates": ("tab:Settings", "check for updates to game grave"), "hash_checker": ("tool:hash", ""),
    "windows_cleanup": ("tool:windows_cleanup", "clean up temp files"),
    "game_optimizer": ("tool:game_optimizer", "turn on game mode and turn off background recording"),
    "memory_optimizer": ("tool:memory_optimizer", "close the apps using the most memory"),
    "command_runner": ("tool:command_runner", ""), "file_associations": ("tool:file_associations", ""),
    "junction_manager": ("tool:junction_manager", ""), "reports": ("tool:game_report", ""),
    "other_storage": ("tab:Other Storage", "scan other storage"), "captures": ("tab:Captures", "scan my captures"),
    "games_tab": ("tab:Games", ""), "my_mods": ("tab:Mods", ""), "scan_pc": ("", "scan my games"),
    "never_touch": ("tab:Settings", ""), "welcome_tour": ("tour", ""), "fix_game": ("tab:Fix Kit", "fix my game"),
}
# Tabs that also hold scan data: "what is in other storage" is a question about the data, so their guide only answers a
# how-to question ("how do I use other storage").
DATA_TABS = frozenset({"other_storage", "captures", "games_tab", "my_mods", "scan_pc", "memory_optimizer"})
_HOW = re.compile(r"\b(how (do|can|would|should) (i|you|we)|how to|how does|how do|teach me|show me how|walk me through|"
                  r"help me (use|with|to)|i don'?t (know|understand) how|what'?s the (best )?way to|guide me|explain how|"
                  r"what does .+ do|what is the .+ for|where (do|can) i (find|get|start))\b")


def is_how_to(question):
    return bool(_HOW.search(" ".join(question.casefold().replace("’", "'").split())))


_STEPS = {
    "autopsy": ("Record a play session with a frame-time tool such as CapFrameX or PresentMon and save the CSV.",
                "Game Grave picks up the newest captures by itself and keeps a short summary of each.",
                "Pick two captures to compare: it shows the frame-time graph, average and lows side by side."),
    "undo_center": ("Every removal Game Grave made is listed with its time, size and where it went.",
                    "Pick items still in the Recycle Bin and press Restore. Each is checked first and goes back only to its "
                    "original place, never over a file that is there now.",
                    "Hide from History only hides a row; it never changes the Recycle Bin."),
    "graveyard": ("Press Scan Leftovers to look in known game-related places for leftovers of games you removed.",
                  "Each item shows its Evidence (Direct, Location, Name hint, Age only, Yours) instead of a guess.",
                  "Tick items (double-click, Shift+click or Select all) and use the delete menu: archives and recordings "
                  "go to the Recycle Bin after a confirmation; games go through Steam, mods through Mods.",
                  "Or ask me \"scan for leftovers\"."),
    "old_files": ("Pick a folder or a drive (Downloads is the default) and press Rescan.",
                  "Old installers, archives and files you haven't opened in a long time are listed with their size.",
                  "Tick files (double-click, Shift+click) and Move to Recycle Bin. Each file is checked again first."),
    "game_dna": ("Pick a game. Game DNA shows everything proven to belong to it: install folder, mods, shader cache, "
                 "screenshots and folders you linked.",
                 "Press Analyze for sizes. Link a save or settings folder yourself if Game Grave can't prove it.",
                 "Cleanup Suggestions send you to the tab that can act on each item."),
    "mods_library": ("Open Mods. The simple My Mods screen shows one game at a time with an on/off switch per mod.",
                     "Advanced shows the detailed view: the library gallery, load order, profiles, conflicts and Bisect."),
    "hash_checker": ("Press Hash Checker and pick a file. Game Grave reads it and shows its SHA-256 fingerprint.",
                     "Paste the checksum from the download page. Green means it matches byte for byte; red means it is "
                     "different."),
}
FEATURES = tuple(replace(f, steps=f.steps or _STEPS.get(f.key, ()), opens=_GUIDES.get(f.key, ("", ""))[0],
                         do=_GUIDES.get(f.key, ("", ""))[1]) for f in FEATURES)
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
