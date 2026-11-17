"""Native Qt check of the AI Assistant page: local answers from scanned data, honest limits, saved chats, no file changes."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QInputDialog, QLabel, QPushButton, QWidget
    from core import ModFolder, OldFile, SteamGame, default_settings
    from gg_desktop import assistant_page
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.assistant_page import state_of
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def transcript(window):
        return " ".join(label.property("plain") or label.text()
                        for label in window.assistant_scroll.widget().findChildren(QLabel))

    def buttons(window):
        return [b.text() for b in window.assistant_scroll.widget().findChildren(QPushButton)]

    def ask(window, text):
        window.assistant_input.setText(text)
        QTest.keyClick(window.assistant_input, Qt.Key_Return)
        settle()

    now = datetime.now().astimezone()
    GB = 1024 ** 3
    played = (now - timedelta(days=400)).timestamp()
    recent = (now - timedelta(days=2)).timestamp()
    steam = [SteamGame("1", "Cyberpunk 2077", "C:\\Steam", "C:\\Steam\\steamapps\\common\\Cyberpunk 2077", 70 * GB, played, "Steam"),
             SteamGame("2", "Starfield", "C:\\Steam", "C:\\Steam\\steamapps\\common\\Starfield", 120 * GB, recent, "Steam")]
    mods = [ModFolder("Texture Pack", "C:\\Steam\\steamapps\\common\\Starfield\\Data\\tex", "C:\\Steam", "Mod folder", (),
                      2 * GB, 4, False, "Steam game folder", "Review manually")]
    files = [OldFile("C:\\Logs\\crash.log", 5000, 1.0)]
    records = [{"id": "r1", "path": "C:\\Steam\\steamapps\\common\\Starfield\\old.bin", "size": 4000,
                "time": (now - timedelta(days=1)).isoformat(timespec="seconds"), "action": "Old Files",
                "state": "Available", "note": "Windows reports a matching Recycle Bin item."}]

    with tempfile.TemporaryDirectory(prefix="GG-assistant-page-") as temp:
        root = Path(temp)
        (root / "fixture.txt").write_text("untouched", encoding="utf-8")
        before = tree_bytes(root)
        settings = default_settings()
        saved = []

        def keep(updated):
            saved.append(dict(updated))

        stack = ExitStack()
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core.save_settings", dict(side_effect=keep)),
            ("gg_desktop.backend.save_settings", dict(side_effect=keep)),
            ("gg_desktop.backend.log_event", {}),
            ("gg_desktop.assistant_page.save_settings", dict(side_effect=keep)),
            ("gg_desktop.assistant_page.get_records", dict(side_effect=lambda: [dict(r) for r in records])),
            ("gg_desktop.assistant_page.get_activity", dict(return_value=[])),
            ("gg_desktop.recovery_screens.save_settings", dict(side_effect=keep)),
            ("gg_desktop.recovery_screens.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_activity", dict(return_value=[])),
            ("gg_desktop.undo_page.get_records", dict(return_value=[])),
            ("gg_desktop.undo_page.get_activity", dict(return_value=[])),
            ("gg_desktop.reference_library.save_settings", {}),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
            ("gg_desktop.local_ai_core.ai_dir", dict(side_effect=lambda base=None: Path(base) if base else root / "AI")),
            ("gg_desktop.local_ai_core._opener", dict(side_effect=AssertionError("No automatic AI download"))),
        ):
            stack.enter_context(patch(target, **options))
        real_error = CrimsonWindow.error
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        confirm = stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=True))
        chooser = stack.enter_context(patch.object(QInputDialog, "getItem", return_value=("All games", True)))
        with stack:
            window = CrimsonWindow()
            window.settings = dict(window.settings, assistant_enabled=True)  # the tab is optional and starts off
            window._sync_assistant_nav()
            window.show()
            window.resize(1280, 720)
            window.inventory = Inventory(steam=steam, games=merge_games(steam, []), mods=mods, files=files,
                                         scanned_at=(now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"))
            window.navigate("AI Assistant")
            settle()
            state = state_of(window)

            # Metrics come from the scan; the assistant says it is read only.
            strip = [v.text() for v in window.assistant_metrics.values]
            assert strip[0] == "0" and strip[1] == "2" and strip[3] == "2h ago" and strip[4] == "Read Only" and strip[5] == "5 of 5", strip
            assert "never change any file" in transcript(window), transcript(window)
            assert window.assistant_scope.text() == "All Games"
            using = [l.text() for l in window.findChildren(QLabel) if l.text() in ("Game library", "Storage scans", "Cleanup history")]
            assert using, "The sources in use are shown"

            # A question is answered from scan data, with sources, rows and a hand-off, and saved.
            ask(window, "What are my largest games by size?")
            text = transcript(window)
            assert "What are my largest games by size?" in text and "Starfield" in text and "Cyberpunk 2077" in text, text
            assert "not measured disk use" in text and "Game library" in text, text
            assert "Open Games" in buttons(window) and "Copy" in buttons(window), buttons(window)
            assert buttons(window).count("Open Games") == 1 and "Show" in buttons(window), buttons(window)
            assert window.assistant_mode.text() in ("Tools: Off", "Tools: Ask first"), window.assistant_mode.text()
            assert window.assistant_input.text() == ""
            assert saved and "assistant_chats" in saved[-1] and saved[-1]["assistant_chats"][0]["messages"], saved[-1:]
            assert [v.text() for v in window.assistant_metrics.values][0] == "1"
            assert window.assistant_title.text() == "What are my largest games by size?"
            assert window.grab().save(str(args.output / "assistant-chat-1280.png"))

            # Quick prompts, safety and history answers; nothing is ever called safe.
            for prompt in window.findChildren(QPushButton):
                if prompt.text() == "Explain my last cleanup":
                    prompt.click()
                    break
            settle()
            text = transcript(window)
            assert "1 recycled" in text and "isn't a promise" in text and "Open Undo Center" in buttons(window), text
            ask(window, "Is it safe to delete my caches?")
            text = transcript(window)
            assert "can't tell you that something is safe" in text and "Open Graveyard" in buttons(window), text
            ask(window, "Which games haven't I played lately?")
            assert "Cyberpunk 2077" in transcript(window) and "never remove anything" in transcript(window)
            ask(window, "help me with the resurrection kit")
            text = transcript(window)
            assert "Resurrection Kit A Resurrection Kit" in text and "single ZIP file" in text and "Open Fix Kit" in buttons(window), text
            assert text.count("I answer from what Game Grave has already scanned") == 0, "A feature question is answered, not deflected"
            ask(window, "tell me a joke")
            assert "not sure what you mean yet" in transcript(window), "a miss offers best guesses"
            assert "don't have an answer for that one yet" not in transcript(window)
            guess = next(b for b in window.assistant_scroll.widget().findChildren(QPushButton) if b.text() == "Largest games")
            guess.click()
            settle()
            assert "What are my largest games?" in transcript(window), "a guess button asks its question"
            ask(window, "hi")
            assert "Ask me anything about your games" in transcript(window)
            ask(window, "how many games do I have")
            assert "You have " in transcript(window) and " games across " in transcript(window), transcript(window)
            ask(window, "which game should I uninstall")
            assert "where the most space sits" in transcript(window) or "Nothing big stands out" in transcript(window)

            # With no model downloaded, an empty chat shows the big Local AI card; Not now hides it for good.
            from PySide6.QtWidgets import QFrame
            previous = state_of(window).current
            assistant_page.new_chat(window)
            settle()
            cards = [f for f in window.assistant_scroll.widget().findChildren(QFrame) if f.objectName() == "localAICard"]
            assert cards and cards[0].isVisible(), "the Local AI card shows in an empty chat"
            assert [k for k, b in cards[0].picks if b.isChecked()] == ["medium"]
            cards[0].picks[0][1].click()
            settle()
            assert window.settings.get("local_ai_model") == "small"
            cards = [f for f in window.assistant_scroll.widget().findChildren(QFrame) if f.objectName() == "localAICard"]
            window.grab().save(str(args.output / "assistant-local-ai-card-1280.png"))
            next(b for b in cards[0].findChildren(QPushButton) if b.text() == "Not now").click()
            settle()
            assert window.settings.get("local_ai_card_hidden") is True
            assert not [f for f in window.assistant_scroll.widget().findChildren(QFrame)
                        if f.objectName() == "localAICard" and f.isVisible()], "Not now hides the card"
            empty = state_of(window).current
            state_of(window).chats = [c for c in state_of(window).chats if c["id"] != empty]
            state_of(window).current = previous
            assistant_page.refresh(window)
            settle()
            from gg_desktop import local_ai_ui as _lui
            _lui.state_of(window).widgets.combo.setCurrentIndex(1)
            settle()
            assert window.settings.get("local_ai_model") == "medium"

            # Local AI panel: nothing downloaded, so the switch is off and disabled and Download is offered.
            from gg_desktop import local_ai_core as ai
            from gg_desktop import local_ai_ui
            from gg_desktop import assistant_page
            assistant_page.show_side(window, True)    # Local AI, Automation and Data Used sit behind the Settings button
            settle()
            w = local_ai_ui.state_of(window).widgets
            assert w is not None and w.get.isVisible() and not w.switch.isEnabled(), "Local AI panel"
            assert "Not downloaded" in w.status.text() and w.combo.count() == 4, w.status.text()
            assert w.combo.currentData() == "medium"
            # Pretend the Medium model and engine are on disk, then answer through the real background path with a
            # stand-in server: the model's text replaces the built-in text and its source is named.
            (root / "AI" / "models").mkdir(parents=True, exist_ok=True)
            (root / "AI" / "models" / "medium.gguf").write_bytes(b"m")
            (root / "AI" / "runtime" / "cpu").mkdir(parents=True, exist_ok=True)
            (root / "AI" / "runtime" / "cpu" / "llama-server.exe").write_bytes(b"e")
            local_ai_ui.sync(window)
            assert w.switch.isEnabled() and w.remove.isVisible() and not w.get.isVisible(), w.status.text()
            w.switch.click()
            settle()
            assert window.settings.get("local_ai_enabled") is True
            def said(text):
                return {"content": text}

            def wait_for(words, seconds=10):
                deadline = time.time() + seconds
                while words not in transcript(window) and time.time() < deadline:
                    settle()
                    time.sleep(0.05)
            with patch.object(ai, "start_best", return_value="cpu"), \
                    patch.object(ai.LocalServer, "chat_message", return_value=said("<think></think>You have 2 games, from Steam.")), \
                    patch.object(ai.LocalServer, "running", new=True):
                ask(window, "how many games have i got")
                wait_for("You have 2 games, from Steam.")
            assert "You have 2 games, from Steam." in transcript(window), transcript(window)
            assert "Local AI: Medium" in transcript(window), "the local model is named as a source"
            assert window.assistant_input.isEnabled()
            # The model looks a game up first, then answers; the answer says what it checked.
            lookup = {"content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "look_up_game", "arguments": "{\"name\": \"cyberpunk\"}"}}]}
            with patch.object(ai, "start_best", return_value="cpu"), \
                    patch.object(ai.LocalServer, "chat_message", side_effect=[lookup, said(
                        "Cyberpunk 2077 reports 70.0 GB on drive C:.")]) as asked, \
                    patch.object(ai.LocalServer, "running", new=True):
                ask(window, "tell me about cyber punk")
                wait_for("reports 70.0 GB on drive C:")
            sent = asked.call_args_list[1].args[0]
            assert any(m.get("role") == "tool" and "Cyberpunk 2077" in m.get("content", "") for m in sent), sent[-2:]
            assert "Checked: Games" in transcript(window), transcript(window)
            # Not helpful keeps the exchange on this PC and copies a report; nothing is sent.
            bad = [b for b in window.assistant_scroll.widget().findChildren(QPushButton) if b.text() == "Not helpful"]
            bad[-1].click()
            settle()
            kept = window.settings.get("assistant_feedback") or []
            assert kept and kept[-1]["question"] == "tell me about cyber punk", kept
            from PySide6.QtGui import QGuiApplication
            assert "Question: tell me about cyber punk" in QGuiApplication.clipboard().text()
            # A size the data doesn't back up is sent back once for correction.
            with patch.object(ai, "start_best", return_value="cpu"), \
                    patch.object(ai.LocalServer, "chat_message", return_value=said("Cyberpunk 2077 takes 999 GB.")), \
                    patch.object(ai.LocalServer, "chat", return_value="Cyberpunk 2077 reports 70.0 GB.") as fixed, \
                    patch.object(ai.LocalServer, "running", new=True):
                ask(window, "how big is cyberpunk really")
                wait_for("Cyberpunk 2077 reports 70.0 GB.")
            assert fixed.call_count == 1 and "999 GB" not in transcript(window).split("how big is cyberpunk really")[-1]
            # A request becomes a plan the model picked from Game Grave's own jobs; nothing runs without OK.
            planned = {"content": "", "tool_calls": [{"id": "p1", "type": "function", "function": {
                "name": "make_plan", "arguments": "{\"summary\": \"Clear out old temp files.\", \"jobs\": "
                "[{\"job\": \"clean_temp_files\"}, {\"job\": \"format_drive\"}]}"}}]}
            with patch.object(ai, "start_best", return_value="cpu"), \
                    patch.object(ai.LocalServer, "chat_message", return_value=planned), \
                    patch.object(ai.LocalServer, "running", new=True):
                ask(window, "my pc feels full of junk, sort it out")
                wait_for("nothing changes until you say OK")
                for _ in range(10):
                    settle()
            text = transcript(window)
            assert "Clear out old temp files." in text and "left out: format_drive" in text, text[-600:]
            # A reply that breaks the rules is retried once; if the retry keeps the rules, that is what shows.
            with patch.object(ai, "start_best", return_value="cpu"), \
                    patch.object(ai.LocalServer, "chat_message", return_value=said("Cyberpunk is safe to delete.")), \
                    patch.object(ai.LocalServer, "chat", return_value="Cyberpunk is 70 GB. Review it in Games.") as asked, \
                    patch.object(ai.LocalServer, "running", new=True):
                ask(window, "what about cyberpunk")
                wait_for("Review it in Games.")
            assert asked.call_count == 1 and "Review it in Games." in transcript(window), transcript(window)
            # Broken twice: never shown, the built-in answer is, and it says why.
            with patch.object(ai, "start_best", return_value="cpu"), \
                    patch.object(ai.LocalServer, "chat_message", return_value=said("Cyberpunk is safe to delete.")), \
                    patch.object(ai.LocalServer, "chat", return_value="Cyberpunk is safe to delete."), \
                    patch.object(ai.LocalServer, "running", new=True):
                ask(window, "and cyberpunk again")
                wait_for("safety rules twice")
            low = transcript(window).lower().replace("is it safe to delete", "")
            assert "safety rules twice" in low and "cyberpunk is safe to delete" not in low, low
            local_ai_ui.stop(window)
            w.switch.click()
            settle()
            assert window.settings.get("local_ai_enabled") is False
            import shutil
            shutil.rmtree(root / "AI")  # the stand-in model files this check made; the app itself wrote nothing
            # The only allowed "safe to remove" is the refusal itself and the user's own question.
            low = transcript(window).lower().replace("i can't tell you that something is safe to remove", "")
            low = low.replace("is it safe to remove", "")
            assert "safe to remove" not in low and "freed" not in low and "reclaimed" not in low, low

            # Hand-off buttons open the owning tab; nothing is changed by asking.
            next(b for b in window.assistant_scroll.widget().findChildren(QPushButton) if b.text() == "Open Games").click()
            settle()
            assert window.current_route == "Games", window.current_route
            window.navigate("AI Assistant")
            settle()
            # A game row's Show button opens Games filtered to that game.
            next(b for b in window.assistant_scroll.widget().findChildren(QPushButton) if b.text() == "Show").click()
            settle()
            assert window.current_route == "Games" and window.game_search.text() == "Starfield", window.game_search.text()
            window.game_search.clear()
            window.navigate("AI Assistant")
            settle()
            assert "Starfield" in transcript(window), "The conversation was saved and comes back"
            assert window.assistant_list.count() == 1 and state_of(window).chats[0]["messages"]

            # Copy puts the question and answer on the clipboard.
            next(b for b in window.assistant_scroll.widget().findChildren(QPushButton) if b.text() == "Copy").click()
            assert app.clipboard().text().startswith("Q: "), app.clipboard().text()[:30]

            # Turning a data source off is honoured, shown and saved; the answer says it is off.
            assistant_page.toggle_source(window, "library", False)
            settle()
            assert [v.text() for v in window.assistant_metrics.values][5] == "4 of 5"
            assert saved[-1]["assistant_sources"] == ["storage", "history", "mods", "captures"], saved[-1].get("assistant_sources")
            ask(window, "largest games")
            assert "Game library is turned off" in transcript(window), transcript(window)
            assistant_page.toggle_source(window, "library", True)
            settle()
            assert [v.text() for v in window.assistant_metrics.values][5] == "5 of 5"

            # Scope to one game.
            chooser.return_value = ("Starfield (Steam)", True)
            window.assistant_scope.click()
            settle()
            assert window.assistant_scope.text() == "Starfield" and saved[-1]["assistant_scope"].startswith("Steam:"), saved[-1]
            ask(window, "how big is it?")
            assert "Starfield reports " in transcript(window) and "Mod locations inside it" in transcript(window), transcript(window)
            chooser.return_value = ("All games", True)
            window.assistant_scope.click()
            settle()
            assert window.assistant_scope.text() == "All Games"

            # New chat, switching, clearing and deleting only touch saved chat text.
            first = state_of(window).current
            assistant_page.new_chat(window)
            settle()
            assert state_of(window).current != first and "never change any file" in transcript(window)
            ask(window, "where does my storage space go")
            assert "don't add these rows" in transcript(window)
            assert window.assistant_list.count() == 2
            def select_chat(chat_id):
                for i in range(window.assistant_list.count()):
                    if window.assistant_list.item(i).data(Qt.UserRole) == chat_id:
                        window.assistant_list.setCurrentRow(i)
                settle()

            second = state_of(window).current
            select_chat(first)
            assert state_of(window).current == first and "Starfield" in transcript(window)
            confirm.reset_mock()
            assistant_page.clear(window)
            assert confirm.called and "never change any file" in transcript(window)
            assert not next(c for c in state_of(window).chats if c["id"] == first)["messages"]
            select_chat(second)
            assert state_of(window).current == second and "don't add these rows" in transcript(window)
            assistant_page.delete_chat(window)
            settle()
            assert not any(c["messages"] for c in state_of(window).chats) and state_of(window).chats
            assert saved[-1]["assistant_chats"] == [], saved[-1]["assistant_chats"]

            # Clickable answers: game names, tabs and folders are links; follow-up buttons under the newest answer.
            ask(window, "when did I last play Starfield")
            rich = [l.text() for l in window.assistant_scroll.widget().findChildren(QLabel) if 'href="game:Starfield"' in l.text()]
            assert rich, "The game name in the answer is a link"
            assert "Is Starfield modded?" in buttons(window), buttons(window)
            assistant_page.open_link(window, "game:Starfield")
            settle()
            assert window.current_route == "Games" and window.game_search.text() == "Starfield"
            window.game_search.clear()
            assistant_page.open_link(window, "tab:More Tools")
            settle()
            assert window.current_route == "More Tools", window.current_route
            window.navigate("AI Assistant")
            settle()
            next(b for b in window.assistant_scroll.widget().findChildren(QPushButton) if b.text() == "Is Starfield modded?").click()
            settle()
            assert "is Starfield modded" in transcript(window), transcript(window)[-300:]

            # Pin an answer; it is listed at the top of Conversations and opens in its own window.
            next(b for b in reversed(window.assistant_scroll.widget().findChildren(QPushButton)) if b.text() == "Pin").click()
            settle()
            assert len(window.settings.get("assistant_pins") or []) == 1, window.settings.get("assistant_pins")
            assert window.assistant_list.item(0).text().startswith("Pinned answers (1)")
            window.assistant_list.setCurrentRow(0)
            settle()
            pins = window._assistant_pins_dialog
            assert pins.isVisible() and "Starfield" in pins.findChildren(__import__("PySide6.QtWidgets", fromlist=["QTextBrowser"]).QTextBrowser)[0].toPlainText()
            pins.close()
            settle()
            # Search past chats by any word in them.
            window.assistant_find.setText("modded")
            settle()
            assert window.assistant_list.count() == 1 and window.assistant_list.item(0).data(Qt.UserRole) == state_of(window).current
            window.assistant_find.setText("zzzz nothing")
            settle()
            assert window.assistant_list.item(0).text() == "No chats match"
            window.assistant_find.clear()
            settle()

            # Guided troubleshooting: one fix at a time, "Did that work?", and what helped is remembered.
            ask(window, "help me fix Starfield, it won't start")
            assert "Step 1 of" in transcript(window) and "No, next step" in buttons(window), transcript(window)[-400:]
            assert "Check it for me" in buttons(window), buttons(window)
            ask(window, "no, still broken")
            assert "Step 2 of" in transcript(window), transcript(window)[-400:]
            ask(window, "yes it worked")
            assert "glad that sorted it" in transcript(window)
            history = (window.settings.get("fix_history") or {}).get("Starfield") or []
            assert [r["result"] for r in history] == ["not_fixed", "fixed"], history
            ask(window, "no")      # the session is over, so "no" is an ordinary message again
            assert "Step 3 of" not in transcript(window)

            # Attach a crash log: only the lines that stand out are asked about; the file is not changed.
            logs = Path(tempfile.mkdtemp(prefix="GG-log-"))
            log = logs / "crash.log"
            log.write_text("boot ok\nloading SkyUI\nERROR: missing master Foo.esm\nfine\n", encoding="utf-8")
            stamp = log.read_bytes()
            assistant_page.attach_file(window, window.assistant_input, str(log))
            settle()
            text = transcript(window)
            assert "From the file crash.log" in text and "missing master Foo.esm" in text and "boot ok" not in text, text[-500:]
            assert log.read_bytes() == stamp

            # Explain things for: saved and passed to the Local AI.
            window.assistant_level.setCurrentIndex(window.assistant_level.findData("new"))
            settle()
            assert window.settings.get("assistant_level") == "new"

            # Every warning offers "Ask the assistant", which asks about it in the pop-out.
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QMessageBox

            def press_ask():
                box = app.activeModalWidget()
                if isinstance(box, QMessageBox):
                    next(b for b in box.buttons() if b.text() == "Ask the assistant").click()
            QTimer.singleShot(150, press_ask)
            real_error(window, "Scan failed", "Access is denied.")
            settle()
            from gg_desktop import assistant_popout
            pop = assistant_popout.current(window)
            assert pop is not None and pop.isVisible()
            last_user = [m for m in assistant_page.current_chat(window)["messages"] if m["role"] == "user"][-1]
            assert '"Scan failed"' in last_user["text"], last_user
            pop.close()
            settle()
            window.navigate("AI Assistant")
            settle()

            # Layout at the supported sizes: no sideways scrolling and the composer is never cut off.
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                settle()
                QTest.qWait(40)
                settle()
                if window.page.horizontalScrollBar().maximum() != 0:
                    wide = sorted(((w.minimumSizeHint().width(), type(w).__name__, w.objectName())
                                   for w in window.page.findChildren(QWidget)), reverse=True)[:12]
                    print("Horizontal overflow at", (width, height), "viewport", window.page.viewport().width(), "widest:", wide)
                assert window.page.horizontalScrollBar().maximum() == 0, (width, height)
                if height >= 720:
                    bottom = window.assistant_send.mapTo(window, window.assistant_send.rect().bottomLeft()).y()
                    assert bottom <= window.height(), ("Send is cut off", (width, height), bottom)
                assert window.grab().save(str(args.output / f"assistant-page-{width}.png"))
            errors.assert_not_called()
            window.close()
            settle()
        assert tree_bytes(root) == before, "Nothing may change on disk"
    print("PASS: AI Assistant page: local answers from scanned data with sources and hand-offs, nothing called safe, "
          "sources switch on and off, chats saved and managed, and no file changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
