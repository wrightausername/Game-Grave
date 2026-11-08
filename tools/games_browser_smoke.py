"""Run the real embedded browser without accounts or network access."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    from PySide6.QtCore import QCoreApplication, QEvent, QUrl, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget
    from gg_desktop.games_connections import SignIn
    from gg_desktop.games_account_store import PROVIDERS
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.show()
    control = SimpleNamespace(window=window, _task=Mock(side_effect=AssertionError("No account request permitted in this smoke")))
    cases = []
    def settle():
        QTest.qWait(25)
        time.sleep(.004)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    def wait(predicate):
        deadline = time.monotonic()+15
        while not predicate() and time.monotonic() < deadline:
            settle()
        assert predicate(), "The real embedded browser did not finish"
    for provider in PROVIDERS:
        with patch("gg_desktop.games_connections.login_url", return_value="about:blank"):
            dialog = SignIn(control, provider)
            connected = Mock()
            dialog.connected.connect(connected)
            dialog.show()
            assert dialog.profile.isOffTheRecord()
            results = []
            loaded = []
            dialog.view.loadFinished.connect(loaded.append)
            dialog.view.setUrl(QUrl("about:blank"))
            def query():
                dialog.browser_page.runJavaScript("document.body.innerHTML='<h1>Games browser smoke</h1>'; document.body.innerText", results.append)
            wait(lambda: loaded and loaded[-1])
            query()
            wait(lambda: results)
            if results[-1] != "Games browser smoke":
                results.clear()
                QTest.qWait(200)
                query()
                wait(lambda: results)
            assert results[-1].strip() == "Games browser smoke"
            cancel = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Cancel")
            QTest.mouseClick(cancel, Qt.LeftButton)
            settle()
            connected.assert_not_called()
            control._task.assert_not_called()
            cases.append(dict(provider=provider, browser="real QtWebEngine", persistent_cookies=False, cancel="passed", result="passed"))
    window.close()
    settle()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"games-browser-check.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print("PASS: all four real embedded sign-in browsers render, remain off the record and cancel without credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
