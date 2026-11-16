"""Self-help knowledge for the local AI: what each tab is for, common PC-gaming problems with the usual fixes, and what
common error messages mean. Pure data and matching; no Qt, no files, no network.

Everything here is widely known general advice, labelled as such to the user ("known fix", "usually means"). It never
says something is certain or safe to delete, and every step that Game Grave can do names where.
"""
from __future__ import annotations

import re

TABS = {
    "Overview": "Totals for games, mods, old files, other storage and captures; Scan PC; Recent Activity; Quick Actions "
                "(Fix a game, Find a crashing mod, Free up space, Open Mods, Review Old Files).",
    "Ready Room": "Patch Watch (official Steam news per game), Your Games at a Glance, Mod Radar, Soulbind (apply your "
                  "preferred settings to games), Squad Sync (share a mod setup or plan a game night with friends), "
                  "Backup Now for a save folder.",
    "Games": "Every installed game from Steam, Epic, GOG, EA, Ubisoft, Battle.net and Xbox. Filters, Library options, "
             "per-game details with Open install folder (Ctrl+O), Open save folder, Verify, DLC, Uninstall (through the "
             "launcher) and Make it run better (right-click).",
    "Mods": "My Mods (one game at a time: switch Mod Organizer 2 or plain-folder mods on and off, drag to reorder, Undo, "
            "Mod Doctor's fixes, Game crashing? Find the mod), Steam Workshop items, and Advanced (Library, Mod Radar, "
            "Load Order, Profiles, Conflicts, Cleanup, Bisect).",
    "Old Files": "Files in scanned folders not changed for 6+ months, by type (installers, archives, videos). Tick, then "
                 "Move to Recycle Bin or Review later in Graveyard.",
    "Other Storage": "Shader caches, launcher caches, logs, crash dumps and settings folders. 'Can clear here' lists the "
                     "ones that can go to the Recycle Bin; driver and Steam library caches are review only.",
    "Captures": "Screenshots and recordings grouped by game, Find Duplicates, Older than 6 months, Move to Recycle Bin.",
    "Graveyard": "Leftovers of removed games and items you sent to review later; Scan Leftovers; the low-space card "
                 "suggests games not played in 90+ days to put to rest with a Resurrection Kit.",
    "Fix Kit": "Game crashing or won't start? (Check the usual fixes, Find the crashing mod with Crash Doctor, Mod "
               "Bisect), Resurrection Kit (back up and restore a whole game), Black Box (crash records), Autopsy (frame "
               "time captures), Exhume.",
    "Game DNA": "Every proven place one game uses (install, mods, shader cache, screenshots, linked folders) with "
                "Cleanup Suggestions that open the owning tab.",
    "Hardware": "Your PC (parts, live load), Upgrade Advisor (notes from recorded play sessions), Drivers & Startup "
                "(Windows Update drivers, the graphics maker's latest driver, firmware, apps that start with Windows), "
                "Registry Cleanup.",
    "Undo Center": "History of every change; restore items Game Grave moved to the Recycle Bin.",
    "Toolbox": "Windows Cleanup, Game Optimizer, Memory Optimizer, Registry Cleanup, File Associations, Junction "
               "Manager, Command Runner, Back up a Folder, Resurrection Kit, Reports, Hash Checker.",
    "AI Assistant": "This chat. Settings (top right): conversations, Local AI model, Let the assistant run tools, "
                    "routines.",
    "Settings": "General (start with Windows, start minimized, scan at start, welcome tour), Scanning (folders, ages), "
                "Protection (Never Touch rules), Notifications, Appearance (interface scale), Data & Privacy, updates.",
}

# problem key -> (words that point to it, the usual fixes in order; "GG:" marks a step Game Grave can do and where)
PROBLEMS = {
    "crash_on_start": (("crash on start", "crashes on start", "won't start", "wont start", "won't launch", "doesn't "
                        "launch", "closes immediately", "crash at launch", "crashes at launch", "nothing happens"),
                       ["GG: Fix Kit > Check the usual fixes (crash records, overlays, Visual C++ runtime, drivers).",
                        "GG: Games > the game > Verify (the launcher repairs damaged or missing game files).",
                        "Install the newest graphics driver from NVIDIA, AMD or Intel (GG: Hardware > Drivers & Startup "
                        "shows whether the maker has a newer one).",
                        "Close overlays that hook into games (Discord, Overwolf, RivaTuner, MSI Afterburner) and try again.",
                        "If the game is modded: GG: Mods > My Mods > Game crashing? Find the mod (Crash Doctor).",
                        "Check that the antivirus didn't quarantine a game file, then verify again."]),
    "crash_midgame": (("crash while playing", "crashes randomly", "crashes after", "crash mid", "crashes mid", "ctd",
                       "crash to desktop", "random crash"),
                      ["GG: Fix Kit > Black Box shows which file each crash happened in.",
                       "A crash in the graphics driver's file usually means a driver problem or an unstable overclock: "
                       "update the driver and remove GPU/CPU overclocks to test.",
                       "If modded, crashes after loading a save often come from a missing master or a broken mod: GG: My "
                       "Mods > Mod Doctor, then Crash Doctor with 'loading a save'.",
                       "Memory running slower than rated or an unstable XMP/EXPO profile can cause random crashes (GG: "
                       "Hardware > Your PC shows the memory speed)."]),
    "stutter": (("stutter", "stuttering", "lag", "low fps", "fps drops", "frame drops", "choppy", "runs badly",
                 "performance", "slow"),
                ["GG: right-click the game > Make it run better (measures before and after any change).",
                 "GG: Toolbox > Game Optimizer: Game Mode on, background recording off, High performance power.",
                 "Shader compilation stutter is common in the first minutes of a new game or after a driver update; "
                 "it usually settles after the shader cache builds.",
                 "Install the game on an SSD rather than a hard drive (GG: Games shows which drive each game is on).",
                 "Close heavy apps in the background (GG: Toolbox > Memory Optimizer).",
                 "Check the graphics driver is current (GG: Hardware > Drivers & Startup)."]),
    "mods_not_loading": (("mods not working", "mods don't load", "mods not loading", "mod not showing", "mods aren't",
                          "mod doesn't work"),
                         ["Launch the game through the mod manager (Mod Organizer 2 or Vortex), not the launcher.",
                          "Script-extender games (Skyrim, Fallout) need the script extender installed and must be "
                          "started through its loader.",
                          "GG: Mods > My Mods > Mod Doctor lists missing masters and switched-off requirements.",
                          "After a game update, script-extender and engine mods often need their own update."]),
    "out_of_space": (("out of space", "drive full", "no space", "not enough space", "disk full", "free up space",
                      "low space"),
                     ["GG: Overview > Free up space, then Graveyard: games you haven't played in months, biggest first.",
                      "GG: Other Storage > Can clear here (caches and logs) and Old Files (old installers and archives).",
                      "GG: Captures > Find Duplicates and Older than 6 months.",
                      "Move a game to another drive with its launcher's own Move option (Steam: Properties > Installed "
                      "Files > Move install folder).",
                      "GG: Graveyard > Put to rest backs a game up with a Resurrection Kit before the launcher "
                      "uninstalls it."]),
    "black_screen": (("black screen", "blank screen", "screen goes black"),
                     ["Press Alt+Enter to switch between full screen and windowed.",
                      "Try the game's windowed or borderless mode in its settings file or launcher options.",
                      "Unplug extra monitors to test, and update the graphics driver.",
                      "Close overlays (Discord, Overwolf, RivaTuner)."]),
    "controller": (("controller not working", "controller not detected", "gamepad", "controller"),
                   ["In Steam, Settings > Controller: turn Steam Input on or off for that game and test again.",
                    "Unplug other controllers and adapters, then reconnect.",
                    "Update the controller's firmware with its maker's app (Xbox Accessories, DualSense updater)."]),
    "download_slow": (("download slow", "slow download", "downloading slowly"),
                      ["In the launcher, change the download region or server and clear its download cache "
                       "(Steam: Settings > Downloads > Clear Download Cache).",
                       "Pause other downloads and streaming on the network."]),
    "save_lost": (("lost my save", "save missing", "saves gone", "save disappeared", "lost progress"),
                  ["GG: Games > the game > Open save folder shows where saves are.",
                   "Check the launcher's cloud saves (Steam: the game's Properties > General > Steam Cloud).",
                   "GG: Undo Center shows if Game Grave moved anything to the Recycle Bin, and restores it.",
                   "GG: Fix Kit > Resurrection Kit restores saves from a kit you made earlier."]),
    "update_broke": (("after update", "since the update", "patch broke", "update broke"),
                     ["Mods and script extenders often break after a game update until their authors update them: "
                      "check their pages (GG: My Mods shows updates Mod Organizer 2 recorded).",
                      "Verify the game's files with the launcher (GG: Games > Verify).",
                      "GG: Ready Room > Patch Watch shows the update's official notes."]),
}

KNOWN_GAMES = {
    "skyrim": ["Skyrim Special Edition updates often break SKSE plugins; Address Library for SKSE Plugins and SKSE "
               "itself must match the game version.", "Start through skse64_loader.exe (Mod Organizer 2 or Vortex does "
               "this when set up)."],
    "fallout 4": ["The 2024 next-gen update broke many F4SE plugins; match F4SE and Address Library to the game version.",
                  "Start through f4se_loader.exe."],
    "starfield": ["Stutter in the first minutes is often shader compilation; it usually settles.",
                  "SFSE plugins must match the game version after each update."],
    "cyberpunk": ["Mods need RED4ext, ArchiveXL and TweakXL kept current after each patch.",
                  "REDmod mods are deployed from the launcher's REDmod option."],
    "baldur's gate 3": ["Mod load order is in modsettings.lsx; after a patch, script extender mods may need an update."],
    "elden ring": ["Mods need Easy Anti-Cheat off (offline only); online play with mods risks a ban."],
}

ERRORS = (
    (r"msvcp1[24]0|vcruntime14|msvcp140_1|vcruntime140_1|concrt140|mfc140",
     "A Microsoft Visual C++ runtime file is missing or damaged. Installing Microsoft's Visual C++ 2015-2022 runtime "
     "usually fixes it.", "GG: Fix Kit > Check the usual fixes can install it from Microsoft."),
    (r"d3dx9_\d+|d3dx10|d3dx11|xinput1_3|x3daudio|xaudio2_7|d3dcompiler_4[0-3]",
     "An older DirectX file is missing. Microsoft's DirectX End-User Runtime (June 2010) adds those files; newer "
     "games don't need it.", "Download it from Microsoft's site."),
    (r"steam_api(64)?\.dll", "The game's Steam connection file is missing or blocked, often quarantined by antivirus.",
     "Restore it from the antivirus quarantine, then GG: Games > Verify."),
    (r"0xc0000005|access violation", "An access violation: the program read memory it shouldn't. Usually a mod, an "
     "overlay, a damaged file or an unstable overclock, not something Windows got wrong.",
     "GG: Fix Kit > Black Box shows which file it happened in."),
    (r"0xc000007b", "A 32-bit and 64-bit mix-up: usually a damaged or wrong Visual C++ or DirectX file.",
     "Reinstall the Visual C++ runtimes (both x64 and x86), then verify the game."),
    (r"0xc0000142|0xc0000135", "The program couldn't start because a file it needs didn't load (often the .NET or Visual "
     "C++ runtime).", "Install the runtimes, update Windows, then verify the game."),
    (r"0xc0000409|stack buffer overrun", "The program stopped itself after detecting damaged memory; often a mod or "
     "overlay.", "Check Black Box for the file, close overlays, test without mods."),
    (r"0x887a0006|dxgi_error_device_hung|device hung|0x887a0005|device removed|dxgi_error_device_removed",
     "The graphics card stopped responding (device hung/removed). Usually the driver, an unstable GPU overclock, or "
     "heat.", "Update the driver, remove overclocks, check temperatures."),
    (r"vulkan-1\.dll|vk_error", "Vulkan isn't working: usually an old or broken graphics driver.",
     "Install the newest driver from NVIDIA, AMD or Intel."),
    (r"out of video memory|out of vram", "The game ran out of graphics memory.",
     "Lower texture quality and resolution, close other programs using the GPU."),
    (r"easyanticheat|battleye|anti-?cheat", "The anti-cheat service didn't start or blocked a file.",
     "Repair it from the game's folder or launcher (Verify), close overlays and mod tools."),
    (r"nvwgf2umx|nvlddmkm|nvoglv", "The crash was in NVIDIA's graphics driver.", "Update or clean-reinstall the driver."),
    (r"amdxx64|atidxx64|amdkmdag", "The crash was in AMD's graphics driver.", "Update or clean-reinstall the driver."),
    (r"igd10iumd|igdumdim", "The crash was in Intel's graphics driver.", "Update the driver with Intel's assistant."),
    (r"ntdll\.dll|kernelbase\.dll", "The crash was recorded in a core Windows file; that's usually where a problem shows "
     "up, not its cause.", "Look at what else the crash report names, or use Black Box."),
    (r"skse|f4se|sfse|script extender", "The script extender doesn't match the game version, or the game wasn't started "
     "through it.", "Update the script extender and its plugins, and start the game through its loader."),
    (r"\.net framework|clr20r3|mscorlib", "A .NET program failed (often a mod tool or launcher).",
     "Install the .NET runtime the program asks for from Microsoft."),
)


def known_fixes(problem="", game=""):
    text = f" {str(problem).casefold()} "
    found = []
    for key, (words, steps) in PROBLEMS.items():
        if any(w in text for w in words):
            found.append({"problem": key.replace("_", " "),
                          "usual_fixes": [s.replace("GG: ", "In Game Grave: ") for s in steps]})
    for name, notes in KNOWN_GAMES.items():
        if name in str(game).casefold() or name in text:
            found.append({"game": name, "known_notes": notes})
    if not found:
        return {"note": "No known fix matches; ask for more detail (when it happens, any error text) or use the "
                        "lookups.", "problems_known": [k.replace("_", " ") for k in PROBLEMS]}
    return {"known_fixes": found[:4], "label": "General known fixes, not read from this PC."}


def explain_error(text=""):
    low = str(text).casefold()
    hits = []
    for pattern, means, next_step in ERRORS:
        if re.search(pattern, low):
            hits.append({"usually_means": means, "next_step": next_step.replace("GG: ", "In Game Grave: ")})
    files = sorted(set(re.findall(r"[a-z0-9_\-]+\.(?:dll|exe|sys)", low)))[:8]
    codes = sorted(set(re.findall(r"0x[0-9a-f]{8}", low)))[:5]
    if not hits:
        return {"files_named": files, "codes": codes, "note": "No known pattern; look the exact message up online, or "
                                                               "check the game's crash records (game_crashes)."}
    return {"matches": hits[:4], "files_named": files, "codes": codes, "label": "What these usually mean in general."}


def tab_help(name=""):
    want = str(name).casefold()
    for tab, text in TABS.items():
        if tab.casefold() in want or want in tab.casefold():
            return {"tab": tab, "what_it_has": text}
    return {"tabs": TABS}
