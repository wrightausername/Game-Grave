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
        return " ".join(label.text() for label in window.assistant_scroll.widget().findChildren(QLabel))

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
            assert "Resurrection Kit:" in text and "single ZIP file" in text and "Open More Tools" in buttons(window), text
            assert text.count("I answer from what Game Grave has already scanned") == 0, "A feature question is answered, not deflected"
            ask(window, "tell me a joke")
            assert "don't have an answer for that one yet" in transcript(window)
            ask(window, "hi")
            assert "Ask me anything about your games" in transcript(window)
            ask(window, "how many games do I have")
            assert "You have " in transcript(window) and " games across " in transcript(window), transcript(window)
            ask(window, "which game should I uninstall")
            assert "where the most space sits" in transcript(window) or "Nothing big stands out" in transcript(window)

            # Local AI panel: nothing downloaded, so the switch is off and disabled and Download is offered.
            from gg_desktop import local_ai_core as ai
            from gg_desktop import local_ai_ui
            w = local_ai_ui.state_of(window).widgets
            assert w is not None and w.get.isVisible() and not w.switch.isEnabled(), "Local AI panel"
            assert "Not downloaded" in w.status.text() and w.combo.count() == 3, w.status.text()
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
            with patch.object(ai, "start_best", return_value="cpu"), \
                    patch.object(ai.LocalServer, "chat", return_value="<think></think>You have 2 games, from Steam."), \
                    patch.object(ai.LocalServer, "running", new=True):
                ask(window, "how many games have i got")
                deadline = time.time() + 10
                while "You have 2 games, from Steam." not in transcript(window) and time.time() < deadline:
                    settle()
                    time.sleep(0.05)
            assert "You have 2 games, from Steam." in transcript(window), transcript(window)
            assert "Local AI: Medium" in transcript(window), "the local model is named as a source"
            assert window.assistant_input.isEnabled()
            # A reply that breaks the rules is never shown; the built-in answer is.
            with patch.object(ai, "start_best", return_value="cpu"), \
                    patch.object(ai.LocalServer, "chat", return_value="Cyberpunk is safe to delete."), \
                    patch.object(ai.LocalServer, "running", new=True):
                ask(window, "what about cyberpunk")
                deadline = time.time() + 10
                while "didn't keep Game Grave's rules" not in transcript(window) and time.time() < deadline:
                    settle()
                    time.sleep(0.05)
            low = transcript(window).lower().replace("is it safe to delete", "")
            assert "didn't keep game grave's rules" in low and "cyberpunk is safe to delete" not in low, low
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
