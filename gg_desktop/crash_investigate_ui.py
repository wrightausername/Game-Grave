"""Why did it crash? The crash investigation window (Fix Kit). Display and the person's choices only; every rule is in
crash_investigate. Reading is automatic once the person presses Find out why; anything that changes the PC asks first,
says exactly what it changes, and is logged. Online lookups ask first (or follow the "always allow" choice)."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea, QWidget

from core import load_settings, log_event, save_settings
from gg_desktop import crash_investigate as ci
from gg_desktop import tools_shell as shell
from gg_desktop.tools_words import GOOD as DONE, WARN as NEEDS, BAD as STOPPED, WORKING, INFO
from gg_desktop.widgets import button, column, row

FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ONLINE_KEY = "investigate_online"            # "" ask each time, "yes" always allow
SETTINGS_BACKUP_KEY = "investigate_settings_backup"
TONE = {"Very likely": DONE, "Likely": NEEDS, "Possible": INFO}
GROUPS = ("Software", "Hardware", "Game")


def open_investigation(window, game=None):
    dialog = InvestigateDialog(window, game)
    window.crash_investigation = dialog
    dialog.show()
    return dialog


def _games(window):
    seen, items = set(), []
    for game in getattr(getattr(window, "inventory", None), "games", ()) or ():
        path = getattr(game, "install_path", None)
        if not path or game.name.casefold() in seen or not Path(path).is_dir():
            continue
        seen.add(game.name.casefold())
        items.append(game)
    return sorted(items, key=lambda g: (-(getattr(g, "last_played", None) or 0), g.name.casefold()))


class InvestigateDialog(shell.ToolDialog):
    def __init__(self, window, game=None):
        super().__init__(window, "investigate", "Why did it crash?", "warning", width=760,
                         summary="Game Grave reads every crash record Windows and the game kept, checks the PC and what "
                                 "changed before the crashes started, and tells you the likely cause with the evidence. "
                                 "If that doesn't settle it, it gives you the tests that will.",
                         step_names=("Pick the game", "Read the clues", "Fix or test"), color=shell.HEX["red"])
        self.window_ = window
        self.inv = None
        self.game = None
        self.resize(820, 760)
        top = row(spacing=10)
        self.games = QComboBox()
        self.games.setAccessibleName("Game to investigate")
        self.games.setMinimumWidth(320)
        for g in _games(window):
            self.games.addItem(g.name, g)
        if game is not None:
            at = self.games.findText(game.name)
            if at >= 0:
                self.games.setCurrentIndex(at)
        top.addWidget(shell.text("Game", "toolNote", wrap=False))
        top.addWidget(self.games, 1)
        self.go = button("Find out why", self.start, kind="primary",
                         tip="Reads only: Windows' crash records and error reports, the system log, the game's own logs, "
                             "and this PC's state. Nothing is changed.")
        top.addWidget(self.go)
        self.body.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(420)
        self.results = QWidget()
        self.results_box = column(spacing=10)
        self.results.setLayout(self.results_box)
        self.scroll.setWidget(self.results)
        self.scroll.hide()
        self.body.addWidget(self.scroll, 1)
        self.copy_button = button("Copy report", self.copy, kind="actionLink",
                                  tip="Copies the whole investigation. The Windows user name is hidden.")
        self.copy_button.setEnabled(False)
        self.add_actions(self.copy_button)
        if not self.games.count():
            self.go.setEnabled(False)
            self.result("Scan your PC first so Game Grave knows your games.", NEEDS)

    # ------------------------------------------------------------ running
    def start(self):
        game = self.games.currentData()
        if game is None:
            return
        self.game = game
        self.go.setEnabled(False)
        self.step(1)
        self.result(f"Reading everything Windows and {game.name} recorded…", WORKING)

        def work(progress):
            src = ci.read_sources(game, progress=lambda words: progress(0, words))
            return ci.investigate(game, src)

        def moved(_n, words):
            try:
                self.result(words, WORKING)
            except RuntimeError:
                pass
        self.window_.job(work, self.show_investigation, error_title="The investigation couldn't finish", progress=moved)

    def show_investigation(self, inv):
        self.inv = inv
        self.go.setEnabled(True)
        self.copy_button.setEnabled(True)
        self.step(2)
        self.result(ci.headline(inv), DONE if inv.settled else NEEDS)
        log_event("crash_investigation", f"Investigated {inv.game}: {len(inv.crashes)} crashes, "
                  + (f"top cause {inv.causes[0].title} ({inv.causes[0].sure})" if inv.causes else "no clear cause"),
                  source="Fix Kit")
        self.fill()
        if not inv.settled and load_settings().get(ONLINE_KEY) == "yes":
            QTimer.singleShot(200, lambda: self.online(asked=True))   # the person chose "always allow"

    def clear(self):
        while self.results_box.count():
            item = self.results_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                while item.layout().count():
                    inner = item.layout().takeAt(0)
                    if inner.widget() is not None:
                        inner.widget().deleteLater()

    def section(self, title):
        self.results_box.addWidget(shell.text(title, "toolTitle", wrap=False))

    def fill(self):
        inv = self.inv
        self.clear()
        self.scroll.show()
        crashes = len(inv.crashes)
        self.results_box.addWidget(shell.text(
            f"{crashes} crash{'es' if crashes != 1 else ''} of {inv.game} recorded in the last {ci.WINDOW_DAYS} days."
            + (f" Newest {inv.crashes[0][0]:%d %b %H:%M}." if crashes else ""), "toolSummary"))
        if inv.causes:
            self.section("Likely causes")
        for cause in inv.causes[:5]:
            frame, lay = shell.card(spacing=6, margins=(14, 10, 14, 10))
            head = row(spacing=10)
            head.addWidget(shell.text(cause.title, "toolTitle", wrap=False), 1)
            head.addWidget(shell.pill(cause.sure, TONE.get(cause.sure, INFO)))
            lay.addLayout(head)
            title, meaning, fix, tests = ci.CAUSES[cause.id]
            lay.addWidget(shell.text(meaning, "toolSummary"))
            lay.addWidget(shell.text("Fix: " + fix))
            evidence = []
            for clue, times in cause.evidence[:6]:
                when = f", newest {clue.when:%d %b %H:%M}" if clue.when else ""
                evidence.append(f"{clue.source}: {clue.text}" + (f" ({times} times{when})" if times > 1 else
                                                                 (f" ({clue.when:%d %b %H:%M})" if clue.when else "")))
            details = shell.Details(["Evidence:"] + ["  " + line for line in evidence])
            details.open(True)
            lay.addWidget(details)
            actions = row(spacing=8)
            for test in tests[:3]:
                actions.addWidget(self.test_button(test))
            actions.addStretch()
            lay.addLayout(actions)
            self.results_box.addWidget(frame)
        if inv.changes:
            self.section("What changed before the crashes started")
            self.results_box.addWidget(shell.text("\n".join(f"{w:%d %b %H:%M}  {words}" for w, _k, words in inv.changes[:8])))
        self.section("Tests that settle it" if not inv.settled else "If that doesn't fix it")
        for group in GROUPS:
            tests = [t for t in inv.tests if ci.TEST_WORDS.get(t, ("",))[0] == group]
            if not tests:
                continue
            frame, lay = shell.card(spacing=4, margins=(14, 8, 14, 8))
            lay.addWidget(shell.text(group, "toolNote", wrap=False))
            for test in tests:
                line = row(spacing=10)
                _g, name, plain = ci.TEST_WORDS[test]
                words_box = column(spacing=1)
                words_box.addWidget(shell.text(name, "toolSummary"))
                words_box.addWidget(shell.text(plain))
                line.addLayout(words_box, 1)
                line.addWidget(self.test_button(test, short=True))
                lay.addLayout(line)
            self.results_box.addWidget(frame)
        if inv.fine:
            self.section("Checked and fine")
            self.results_box.addWidget(shell.text("\n".join("✓  " + line for line in inv.fine)))
        self.results_box.addWidget(shell.text("Looked at: " + "; ".join(inv.looked), "toolNote"))
        self.results_box.addStretch(1)

    # ------------------------------------------------------------ tests
    def test_button(self, test, short=False):
        labels = {"verify": "Verify files", "crash_doctor": "Find the mod", "reset_settings": "Reset settings",
                  "online": "Look online", "overlays_off": "Close overlays", "driver_back": "Open Exhume",
                  "driver_new": "Check drivers", "runtimes": "Get runtimes", "defender": "Open Windows Security",
                  "pagefile": "Open the setting", "space": "Free up space", "disk_health": "Show drive health",
                  "memory_test": "Test memory", "temps": "Open Hardware", "no_overclock": "How to", "lower_settings": "How to"}
        name = labels.get(test, "Go")
        control = button(name, lambda: self.run_test(test), kind="actionLink" if short else "secondary",
                         tip=ci.TEST_WORDS.get(test, ("", "", ""))[2])
        control.setAccessibleName(f"{name}: {ci.TEST_WORDS.get(test, ('', name))[1]}")
        return control

    def run_test(self, test):
        game, window = self.game, self.window_
        try:
            handler = getattr(self, "test_" + test)
        except AttributeError:
            return
        handler(game, window)

    def ask(self, title, text):
        return self.window_.confirm(title, text)

    def test_verify(self, game, window):
        from gg_desktop import fixgame_core as fx
        link = fx.verify_link(game)
        if not link:
            window.info("Verify the game's files", fx.verify_words(game))
            return
        if self.ask("Verify the game's files?", f"Game Grave opens Steam's own check for {game.name} ({link}). Steam "
                    "checks every file and downloads only damaged or missing ones. Mods inside the game folder may be "
                    "replaced by the original files."):
            QDesktopServices.openUrl(QUrl(link))
            log_event("investigate_verify", f"Opened Steam's file check for {game.name}", source="Fix Kit")
            self.result("Steam is checking the files. Play again when it finishes.", INFO)

    def test_crash_doctor(self, game, window):
        from gg_desktop import crashdoctor_ui
        crashdoctor_ui.open_doctor(window, game)

    def test_overlays_off(self, game, window):
        from gg_desktop import fixgame_core as fx, winpc
        try:
            running = [p for p in winpc.list_processes(winpc.Runner()) if p.name.casefold() in fx.OVERLAYS]
        except Exception:
            running = []
        if not running:
            window.info("Overlays", "No known overlay is running right now. Steam's and Discord's in-game overlays can "
                        "also be switched off in their own settings (Steam: Settings, In Game; Discord: Settings, Game "
                        "Overlay).")
            return
        names = sorted({fx.OVERLAYS[p.name.casefold()] for p in running})
        if not self.ask("Close these overlays?", "Game Grave asks these programs to close the normal way, so they can "
                        "save first:\n\n  " + "\n  ".join(names) + "\n\nNothing else is closed. Start them again any time."):
            return
        for proc in running:
            try:
                subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True, timeout=15, creationflags=FLAGS)
            except Exception:
                pass
        log_event("investigate_overlays", "Asked overlays to close: " + ", ".join(names), source="Fix Kit")
        self.result("Overlays asked to close: " + ", ".join(names) + ". Play again and see if it still crashes.", DONE)

    def test_driver_back(self, game, window):
        self.close_to(lambda: window.navigate("Fix Kit"))
        def open_strip():
            panel = getattr(window.page, "exhume", None)
            for name in ("expand", "open_body", "set_open"):
                fn = getattr(panel, name, None)
                if callable(fn):
                    try:
                        fn(True) if name == "set_open" else fn()
                    except TypeError:
                        continue
                    break
        QTimer.singleShot(150, open_strip)

    def test_driver_new(self, game, window):
        from gg_desktop import autopilot_ui
        self.close_to(lambda: autopilot_ui.open_target(window, "tab:Hardware/Drivers & Startup"))

    def test_runtimes(self, game, window):
        from gg_desktop import fixgame_core as fx
        if self.ask("Get Microsoft's runtimes?", "Opens Microsoft's own download for the Visual C++ 2015-2022 runtime "
                    f"({fx.VC_DOWNLOAD}). Run it to install or repair it. For 32-bit games, also install the x86 one from "
                    "Microsoft's page."):
            QDesktopServices.openUrl(QUrl(fx.VC_DOWNLOAD))

    def test_defender(self, game, window):
        QDesktopServices.openUrl(QUrl("windowsdefender://threat/"))

    def test_pagefile(self, game, window):
        if self.ask("Open the page file setting?", "Opens Windows' Performance Options. Go to Advanced, Virtual memory, "
                    "Change, and tick 'Automatically manage paging file size for all drives'. Game Grave changes nothing "
                    "itself."):
            try:
                subprocess.Popen(["SystemPropertiesPerformance.exe"], creationflags=FLAGS)
            except OSError:
                window.info("Page file", "Open System Properties, Advanced, Performance Settings, Advanced, Virtual memory.")

    def test_space(self, game, window):
        self.close_to(lambda: window.navigate("Graveyard"))

    def test_disk_health(self, game, window):
        disks = ci.disks()
        if not disks:
            window.info("Drive health", "Windows didn't report drive health on this PC.")
            return
        window.info("Drive health", "What Windows reports for each drive:\n\n" + "\n".join(
            f"  {d.get('FriendlyName', 'Drive')}: {d.get('HealthStatus', 'unknown')}"
            + (f" ({d.get('MediaType')})" if d.get("MediaType") not in (None, "", 0, "Unspecified") else "") for d in disks)
            + "\n\nAnything other than Healthy: back up important files and check the drive maker's tool.")

    def test_memory_test(self, game, window):
        if not self.ask("Test the memory?", "Opens Windows Memory Diagnostic. It asks you whether to restart now or "
                        "test at the next restart; the test takes about 10 to 20 minutes and the result shows after you "
                        "sign in. Save your work before restarting."):
            return
        try:
            subprocess.Popen(["mdsched.exe"])
            log_event("investigate_memory_test", "Opened Windows Memory Diagnostic", source="Fix Kit")
        except OSError as problem:
            window.error("Memory test", f"Windows Memory Diagnostic didn't open: {problem}")

    def test_temps(self, game, window):
        self.close_to(lambda: window.navigate("Hardware"))

    def test_no_overclock(self, game, window):
        window.info("Remove overclocks for a test", "For one test, play with nothing overclocked:\n\n"
                    "  1. Graphics: in MSI Afterburner or your card's app, press Reset (default clocks).\n"
                    "  2. Memory: in the BIOS, turn XMP or EXPO off.\n  3. Processor: turn off any manual overclock or "
                    "PBO tuning.\n\nIf the crashes stop, put things back one at a time to find the one. Game Grave doesn't "
                    "change the BIOS or clocks.")

    def test_lower_settings(self, game, window):
        window.info("Lower the graphics settings", "In the game's settings: lower texture quality first, then "
                    "resolution or render scale, and turn off ray tracing and frame generation. If it stops crashing, "
                    "the graphics card was running out of memory.")

    def test_reset_settings(self, game, window):
        backup = load_settings().get(SETTINGS_BACKUP_KEY) or {}
        if backup.get("game") == game.name and backup.get("moved"):
            if self.ask("Put the settings back?", "Moves your old settings files back where they were:\n\n  " +
                        "\n  ".join(Path(m[1]).name for m in backup["moved"]) + "\n\nA file the game has made since is "
                        "left where it is and its name is listed."):
                kept = []
                for original, saved in backup["moved"]:
                    try:
                        if Path(original).exists():
                            kept.append(Path(original).name)
                            continue
                        Path(saved).replace(original)
                    except OSError:
                        kept.append(Path(original).name)
                settings = load_settings()
                settings.pop(SETTINGS_BACKUP_KEY, None)
                save_settings(settings)
                log_event("investigate_settings_back", f"Put {game.name}'s settings back", source="Fix Kit")
                self.result("Settings put back." + (f" Left alone (the game made new ones): {', '.join(kept)}." if kept
                                                    else ""), DONE if not kept else NEEDS)
            return
        files = settings_files(game)
        if not files:
            window.info("Reset the game's settings", "Game Grave didn't find this game's settings files in the usual "
                        "places. Most games have a 'Reset to defaults' button in their own graphics settings.")
            return
        if not self.ask("Reset the game's settings?", "Game Grave moves these settings files into a backup folder next "
                        "to them, so the game makes fresh ones the next time it starts. Saves are not touched.\n\n  " +
                        "\n  ".join(str(f) for f in files) + "\n\nPress the same button again to put them back."):
            return
        stamp = time.strftime("%Y-%m-%d %H-%M")
        moved = []
        for path in files:
            target_dir = path.parent / f"Game Grave settings backup {stamp}"
            try:
                target_dir.mkdir(exist_ok=True)
                target = target_dir / path.name
                if target.exists():
                    continue
                path.replace(target)
                moved.append((str(path), str(target)))
            except OSError:
                continue
        settings = load_settings()
        settings[SETTINGS_BACKUP_KEY] = {"game": game.name, "moved": moved}
        save_settings(settings)
        log_event("investigate_settings_reset", f"Moved {len(moved)} of {game.name}'s settings files aside", source="Fix Kit")
        self.result(f"Moved {len(moved)} settings file{'s' if len(moved) != 1 else ''} aside. Start the game; it makes "
                    "fresh settings. 'Reset settings' again puts the old ones back.", DONE if moved else STOPPED)

    def test_online(self, game, window):
        self.online(asked=False)

    def online(self, asked=False):
        game, inv = self.game, self.inv
        if game is None or inv is None:
            return
        app_id = str(getattr(game, "app_id", "") or "")
        if app_id.isdigit() and not asked:
            settings = load_settings()
            if settings.get(ONLINE_KEY) != "yes":
                box = self.window_.confirm(
                    "Look online for this game?", f"Game Grave asks Steam for {game.name}'s recent news and patch notes, "
                    "to see if an update came out just before the crashes started. Only the game's Steam number is "
                    f"sent ({app_id}), nothing about you or your PC.\n\nAllow this from now on for crash checks?")
                if not box:
                    self.offer_links()
                    return
                settings[ONLINE_KEY] = "yes"
                save_settings(settings)
        if app_id.isdigit():
            self.result(f"Checking {game.name}'s recent Steam news…", WORKING)

            def work(_progress):
                return ci.steam_news(app_id)

            def got(news):
                try:
                    clue = ci.news_clue(news, inv.crashes)
                    if clue:
                        ci.add_clue(inv, clue, game)
                    self.fill()
                    latest = news[0] if news else None
                    self.result(ci.headline(inv) + (f" Latest Steam news: \"{latest[1]}\" ({latest[0]:%d %b})." if latest
                                                    else " Steam has no recent news for it."),
                                DONE if inv.settled else NEEDS)
                    self.offer_links(news)
                except RuntimeError:
                    pass
            self.window_.job(work, got, error_title="Steam couldn't be reached")
        else:
            self.offer_links()

    def offer_links(self, news=()):
        inv = self.inv
        frame, lay = shell.card(spacing=6, margins=(14, 8, 14, 8))
        lay.addWidget(shell.text("Look for other players with this crash", "toolSummary"))
        lay.addWidget(shell.text("These open in your browser with the game's name and the crash details filled in. "
                                 "Nothing about you is included."))
        line = row(spacing=8)
        for name, url in inv.search.items():
            line.addWidget(button(name, lambda u=url: QDesktopServices.openUrl(QUrl(u)), kind="actionLink"))
        line.addStretch()
        lay.addLayout(line)
        for when, title, url in list(news)[:4]:
            if url.startswith("https://"):
                lay.addWidget(button(f"{when:%d %b}: {title[:70]}", lambda u=url: QDesktopServices.openUrl(QUrl(u)),
                                     kind="actionLink"))
        self.results_box.insertWidget(max(0, self.results_box.count() - 1), frame)

    def close_to(self, go):
        """Open another part of Game Grave; this window stays open beside it."""
        go()

    def copy(self):
        if self.inv is not None:
            QApplication.clipboard().setText(ci.render(self.inv))
            self.result("Report copied. The Windows user name is hidden.", INFO)


def settings_files(game):
    """The game's own settings files in the places engines keep them (never saves): *.ini / *.cfg directly in its
    Documents\\My Games folder, and Unreal's Saved\\Config\\Windows* folders."""
    out = []
    for place in ci.log_places(game.name, game.install_path):
        text = str(place).casefold()
        folders = []
        if "my games" in text and not text.endswith(("skse", "f4se", "sfse", "obse")):
            folders.append(place)
        if text.endswith("saved\\logs") or text.endswith("saved/logs"):
            config = place.parent / "Config"
            folders += [p for p in ci._children(config) if p.name.casefold().startswith(("windows", "wingdk"))]
        for folder in folders:
            try:
                for item in folder.iterdir():
                    if item.is_file() and item.suffix.casefold() in (".ini", ".cfg") and "save" not in item.name.casefold():
                        out.append(item)
            except OSError:
                continue
    unique = {}
    for p in out:
        unique.setdefault(str(p).casefold(), p)
    return list(unique.values())[:20]
