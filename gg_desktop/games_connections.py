"""Games-owned connection UI and official-site sign-in windows."""
from __future__ import annotations

import json
import secrets
import time
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from gg_desktop.games_account_store import PROVIDERS, forget, load_secret, load_snapshots, save_secret
from gg_desktop.games_http import json_request, cookie_header
from gg_desktop.games_providers import EA_API, EPIC_CLIENT, exchange_epic_code

DARK = "QDialog {background:#020609;color:#edf1f7;} QLabel {color:#edf1f7;} QPushButton {background:#15202b;color:#edf1f7;border:1px solid #495563;padding:8px;border-radius:4px;} QPushButton:hover {border-color:#ff2848;}"
LOGIN_ROOTS = {"Steam": ("steampowered.com", "steamcommunity.com"), "Epic Games": ("epicgames.com",), "EA": ("ea.com",), "GOG": ("gog.com",)}


def parse_login_document(provider, url, text, state):
    """Accept tokens only from that sign-in window's exact official origin."""
    import re
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.port not in (443, None) or parsed.username or parsed.password
            or not isinstance(text, str) or len(text) > 100000):
        return None
    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            return None
        if provider == "Steam" and parsed.hostname == "store.steampowered.com" and "/login" not in parsed.path:
            user, config = result.get("user"), result.get("config")
            if not isinstance(user, dict) or not isinstance(config, dict):
                return None
            token = config.get("webapi_token")
            if user.get("logged_in") and re.fullmatch(r"[0-9]{17}", str(user.get("steamid", ""))) and isinstance(token, str) and 0 < len(token) < 16000:
                return dict(account_id=str(user["steamid"]), access_token=token, account_name=str(user.get("persona_name", "Steam account"))[:160])
        if provider == "Epic Games" and parsed.hostname == "www.epicgames.com" and parsed.path == "/id/api/redirect":
            query = parse_qs(parsed.query)
            code = result.get("authorizationCode")
            if query.get("clientId") == [EPIC_CLIENT] and query.get("state") == [state] and isinstance(code, str) and 0 < len(code) < 16000:
                return {"authorization_code": code}
        if provider == "EA" and parsed.hostname == "accounts.ea.com" and parsed.path == "/connect/auth":
            token = result.get("access_token")
            if isinstance(token, str) and 0 < len(token) < 16000:
                expires = result.get("expires_in", 3600)
                expires = expires if type(expires) in (int, float) and 0 < expires <= 86400 else 3600
                return dict(access_token=token, expires_at=time.time()+expires)
    except (ValueError, TypeError):
        pass
    return None


def login_url(provider, state):
    if provider == "Steam":
        return "https://store.steampowered.com/login/?redir=explore%2F"
    if provider == "Epic Games":
        callback = "https://www.epicgames.com/id/api/redirect?" + urlencode(dict(clientId=EPIC_CLIENT, responseType="code", state=state))
        return "https://www.epicgames.com/id/login?redirectUrl=" + quote(callback, safe="")
    if provider == "EA":
        return "https://www.ea.com/login"
    if provider == "GOG":
        return "https://www.gog.com/account"
    raise ValueError("Unsupported account provider.")


class SignIn(QDialog):
    connected = Signal(str, object)

    def __init__(self, control, provider):
        super().__init__(control.window)
        # WebEngine remains a lazy dependency: drawing the library never starts
        # a browser process. The user's password stays on the official website.
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self.control, self.provider = control, provider
        self.state = secrets.token_hex(20)
        self.cookies, self.finishing, self.phase = {}, False, "login"
        self.cancelled, self.popups = False, []
        self.setWindowTitle("Connect " + provider)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowModality(Qt.ApplicationModal)
        self.setStyleSheet(DARK)
        self.resize(1024, 760)
        layout = QVBoxLayout(self)
        self.message = QLabel("Sign in on the official " + provider + " website. Closing this window cancels the connection.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.address = QLabel()
        self.address.setTextFormat(Qt.PlainText)
        layout.addWidget(self.address)
        self.view = QWebEngineView(self)
        # The profile outlives this dialog's pages, avoiding Chromium lifetime
        # errors. It is off the record; persisted credentials use Windows DPAPI.
        self.profile = QWebEngineProfile(control.window)
        owner = self
        class Page(QWebEnginePage):
            def javaScriptConsoleMessage(page, *_args):
                pass  # Official sites' console output may contain session data.
            def acceptNavigationRequest(page, url, kind, main_frame):
                if url.scheme() == "nucleus" and owner.provider == "EA" and owner.phase == "ea-auth" and urlsplit(page.url().toString()).hostname == "accounts.ea.com":
                    values = parse_qs(url.fragment())
                    token = values.get("access_token", [""])[0]
                    if token:
                        owner.finish({"access_token": token, "expires_at": time.time()+3600})
                    return False
                return url.scheme() in ("https", "about")
        self.browser_page = Page(self.profile, self.view)
        self.view.setPage(self.browser_page)
        self.browser_page.newWindowRequested.connect(self.open_popup)
        self.browser_page.windowCloseRequested.connect(self.check)
        self.profile.cookieStore().cookieAdded.connect(self.cookie_added)
        self.view.loadFinished.connect(lambda _ok: self.check())
        self.view.urlChanged.connect(lambda url: self.address.setText(url.host()+url.path()))
        layout.addWidget(self.view, 1)
        bar = QHBoxLayout()
        check = QPushButton("Finish sign-in")
        check.clicked.connect(self.check)
        bar.addWidget(check)
        retry = QPushButton("Restart sign-in")
        retry.clicked.connect(self.restart)
        bar.addWidget(retry)
        bar.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bar.addWidget(cancel)
        layout.addLayout(bar)
        self.view.setUrl(QUrl(login_url(provider, self.state)))

    def restart(self):
        self.finishing, self.phase = False, "login"
        self.state = secrets.token_hex(20)
        self.view.setUrl(QUrl(login_url(self.provider, self.state)))

    def open_popup(self, request):
        if request.requestedUrl().scheme() not in ("", "https", "about"):
            return
        from PySide6.QtWebEngineWidgets import QWebEngineView
        popup = QDialog(self)
        popup.resize(850, 650)
        popup.setWindowTitle("Official " + self.provider + " sign-in")
        view = QWebEngineView(popup)
        page = type(self.browser_page)(self.profile, view)
        view.setPage(page)
        QVBoxLayout(popup).addWidget(view)
        page.newWindowRequested.connect(self.open_popup)
        page.windowCloseRequested.connect(popup.accept)
        view.loadFinished.connect(lambda _ok: self.check(page))
        popup.finished.connect(lambda _result: self.check())
        self.popups.append((popup, view, page))
        request.openIn(page)
        popup.show()

    def cookie_added(self, cookie):
        domain = cookie.domain().lstrip(".").casefold()
        if not any(domain == root or domain.endswith("."+root) for root in LOGIN_ROOTS[self.provider]):
            return
        try:
            name, value = bytes(cookie.name()).decode("ascii"), bytes(cookie.value()).decode("utf-8")
        except UnicodeError:
            return
        if len(name) > 200 or len(value) > 16000 or len(self.cookies) >= 150:
            return
        self.cookies[(name, domain, cookie.path())] = dict(name=name, value=value, domain=cookie.domain(), path=cookie.path(),
                                                        secure=cookie.isSecure(), http_only=cookie.isHttpOnly())

    def check(self, page=None):
        if self.cancelled or self.finishing or not self.isVisible():
            return
        page = page if page is not None and not isinstance(page, bool) else self.browser_page
        url = urlsplit(page.url().toString())
        if url.scheme != "https":
            return
        if self.provider == "Steam" and url.hostname == "store.steampowered.com" and "/login" not in url.path:
            script = """(()=>{let e=document.getElementById('application_config');if(!e)return null;
                return JSON.stringify({user:JSON.parse(e.getAttribute('data-userinfo')||'{}'),
                config:JSON.parse(e.getAttribute('data-store_user_config')||'{}')});})()"""
            page.runJavaScript(script, lambda value: self.document_result(value, page))
        elif self.provider == "Epic Games" and url.hostname == "www.epicgames.com" and url.path == "/id/api/redirect":
            query = parse_qs(url.query)
            if query.get("clientId") == [EPIC_CLIENT] and query.get("state") == [self.state]:
                page.runJavaScript("document.body.innerText", lambda value: self.document_result(value, page))
        elif self.provider == "EA":
            if url.hostname == "www.ea.com" and "/login" not in url.path and self.phase == "login":
                self.phase = "ea-auth"
                auth_url = "https://accounts.ea.com/connect/auth?" + urlencode(dict(client_id="ORIGIN_JS_SDK", response_type="token", redirect_uri="nucleus:rest", prompt="none"))
                self.view.setUrl(QUrl(auth_url))
            elif url.hostname == "accounts.ea.com" and self.phase == "ea-auth":
                page.runJavaScript("document.body.innerText", lambda value: self.document_result(value, page))
        elif self.provider == "GOG" and url.hostname in ("www.gog.com", "menu.gog.com") and "/account" in url.path:
            self.finish({})

    def document_result(self, value, page):
        from shiboken6 import isValid
        if not self.cancelled and isValid(page):
            result = parse_login_document(self.provider, page.url().toString(), value, self.state)
            if result:
                self.finish(result)




    def finish(self, value):
        if self.cancelled or self.finishing:
            return
        self.finishing = True
        self.message.setText("Completing the account connection…")
        provider = self.provider
        cookie_values = list(self.cookies.values())
        connection_id = self.state
        user_agent = self.profile.httpUserAgent()
        def work(_progress):
            value_copy = dict(value, cookies=cookie_values, connection_id=connection_id, user_agent=user_agent)
            if provider == "Epic Games":
                code = value_copy.pop("authorization_code")
                value_copy.update(exchange_epic_code(code))
            elif provider == "EA":
                reply = json_request(f"https://{EA_API}/graphql", hosts={EA_API},
                    headers={"Authorization": "Bearer " + value_copy["access_token"], "User-Agent": user_agent}, data={"query": "query{me{player{pd displayName}}}"})
                player = reply.get("data", {}).get("me", {}).get("player", {})
                if not player.get("pd"):
                    raise ValueError("Finish signing in to EA, then try again.")
                value_copy.update(account_id=str(player["pd"]), account_name=str(player.get("displayName", "EA account")))
            elif provider == "GOG":
                reply = json_request("https://menu.gog.com/v1/account/basic", hosts={"menu.gog.com"},
                    headers={"Cookie": cookie_header(cookie_values, "menu.gog.com")})
                if not reply.get("isLoggedIn") or not reply.get("userId"):
                    raise ValueError("Finish signing in to GOG, then try again.")
                value_copy.update(account_id=str(reply["userId"]), account_name=str(reply.get("username", "GOG account")))
            return value_copy
        def done(secret, error):
            from shiboken6 import isValid
            if not isValid(self) or self.cancelled:
                return
            self.finishing = False
            if error:
                self.message.setText("The connection could not finish. Check your connection or use Restart sign-in to try again.")
                return
            self.connected.emit(provider, secret)
            self.accept()
        self.control._task(work, done)

    def done(self, result):
        self.cancelled = True
        for popup, view, page in self.popups:
            view.stop()
            page.deleteLater()
            popup.close()
            popup.deleteLater()
        self.view.stop()
        self.browser_page.deleteLater()
        self.profile.deleteLater()
        super().done(result)


class Connections(QDialog):
    def __init__(self, control):
        super().__init__(control.window)
        self.control = control
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModal)
        self.setWindowTitle("Game libraries and launcher connections")
        self.setStyleSheet(DARK)
        self.resize(690, 480)
        layout = QVBoxLayout(self)
        intro = QLabel("Connect your accounts to include owned games that are not installed, their artwork and available playtime. Local installations remain available without signing in.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.status = {}
        for provider in PROVIDERS:
            row = QHBoxLayout()
            title = QLabel(provider)
            title.setFixedWidth(90)
            row.addWidget(title)
            state = QLabel()
            state.setWordWrap(True)
            self.status[provider] = state
            row.addWidget(state, 1)
            sign_in = QPushButton("Sign in")
            sign_in.setAccessibleName("Connect " + provider)
            sign_in.clicked.connect(lambda _=False, provider=provider: self.connect_provider(provider))
            row.addWidget(sign_in)
            sync = QPushButton("Refresh")
            sync.clicked.connect(lambda _=False, provider=provider: control.sync_libraries([provider]))
            row.addWidget(sync)
            disconnect = QPushButton("Disconnect")
            disconnect.clicked.connect(lambda _=False, provider=provider: self.disconnect(provider))
            row.addWidget(disconnect)
            layout.addLayout(row)
        layout.addStretch()
        self.refresh_status()
        native = QPushButton("Choose a launcher executable…")
        native.clicked.connect(control.choose_launcher)
        layout.addWidget(native)
        sync_all = QPushButton("Refresh connected libraries")
        sync_all.clicked.connect(lambda: control.sync_libraries())
        layout.addWidget(sync_all)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def refresh_status(self):
        snapshots = load_snapshots()
        for provider, label in self.status.items():
            secret = load_secret(provider)
            snapshot = snapshots.get(provider, {})
            if secret:
                name = secret.get("account_name", provider)
                count = len(snapshot.get("items", []))
                label.setText(f"{name} · {count} owned games" if snapshot else f"{name} · ready to refresh")
            else:
                label.setText("Not connected")

    def connect_provider(self, provider):
        dialog = SignIn(self.control, provider)
        dialog.connected.connect(self.save_connection)
        dialog.show()

    def save_connection(self, provider, secret):
        try:
            save_secret(provider, secret)
        except (ValueError, OSError):
            self.control.window.error("Connection not saved", "Windows could not save the account connection. Try connecting again.")
            return
        self.refresh_status()
        self.control.reload_libraries()
        self.control.sync_libraries([provider])

    def disconnect(self, provider):
        self.control.sync_cancel.set()
        forget(provider)
        self.control.reload_libraries()
        self.refresh_status()
