"""My Mods: the simple Mods screen. One game at a time, one plain sentence, three cards, and your mods with switches.

* Mod Organizer 2 games: real mod names in MO2's order, an on/off switch per mod, drag to reorder, Undo, and Mod Doctor's
  problems with a fix button. Every change goes through mymods_core (snapshot first, refused while MO2 is open).
* Steam Workshop games: every item by its real name and picture from Steam, size, when Steam last updated it, whether Steam
  has a newer version waiting, and Open in Steam (subscribing and unsubscribing stay in Steam).
* Advanced shows the previous detailed Mods view (Library, Mod Radar, Load Order, Profiles, Conflicts, Cleanup, Bisect).
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import threading
import urllib.request

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QSizePolicy, QWidget)

import core
from core import human_size, log_event
from gg_desktop import mymods_core as mc
from gg_desktop import mymods_doctor as doctor
from gg_desktop import workshop_core as ws
from gg_desktop.widgets import button, column, label, row

TONES = {"good": ("#32d67a", "#0b2215", "#1f6a3f"), "warn": ("#f6be24", "#241c06", "#6d5512"),
         "bad": ("#ff5a6e", "#26080d", "#7a1d2b"), "info": ("#13bcf5", "#071a22", "#1b5f78")}
TILE_COLORS = ("#7f5af0", "#2cb67d", "#e45858", "#f2b84b", "#3da9fc", "#ef4565", "#00b8a9", "#c084fc")
CARD_STYLE = ("QFrame#mmCard{background:#0c121a;border:1px solid #1e2b3a;border-radius:10px;}"
              "QFrame#mmCard:hover{border-color:#3b5470;}")


def mode(window):
    if getattr(window, "reference_preview", False):
        return "advanced"
    return "advanced" if window.settings.get("mods_view") == "advanced" else "simple"


# ------------------------------------------------------------------ small pieces
def tile(name: str, size=40, picture: QPixmap | None = None) -> QLabel:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if picture is not None and not picture.isNull():
        scaled = picture.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        p.drawPixmap(0, 0, scaled, (scaled.width() - size) // 2, (scaled.height() - size) // 2, size, size)
    else:
        color = QColor(TILE_COLORS[int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % len(TILE_COLORS)])
        color.setAlpha(170)
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, size, size, 7, 7)
        words = [w for w in name.replace("_", " ").split() if w[:1].isalnum()]
        initials = "".join(w[0] for w in words[:2]).upper() or "?"
        p.setPen(QColor("#ffffff"))
        font = p.font()
        font.setBold(True)
        font.setPixelSize(int(size * 0.38))
        p.setFont(font)
        p.drawText(pix.rect(), Qt.AlignCenter, initials)
    p.end()
    pic = QLabel()
    pic.setPixmap(pix)
    pic.setFixedSize(size, size)
    return pic


def note(text, tone="muted"):
    color = {"muted": "#8b98aa", "good": "#32d67a", "warn": "#f6be24", "bad": "#ff5a6e", "info": "#13bcf5"}[tone]
    tag = QLabel(text)
    tag.setStyleSheet(f"color:{color};font-size:12px;")
    return tag


def when(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%b %d, %Y")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


class Card(QFrame):
    def __init__(self, symbol_text, on_click):
        super().__init__()
        self.setObjectName("mmCard")
        self.setStyleSheet(CARD_STYLE)
        self.setCursor(Qt.PointingHandCursor)
        self.on_click = on_click
        lay = column(spacing=3, margins=(12, 10, 12, 10))
        self.setLayout(lay)
        self.head = label(symbol_text, "caption")
        self.big = label("", "readyDetail", wrap=True)
        self.big.setStyleSheet("color:#f2f5f8;font-size:14px;font-weight:700;")
        self.small = label("", "caption", wrap=True)
        for w in (self.head, self.big, self.small):
            lay.addWidget(w)
        self.setMinimumHeight(86)

    def set(self, big, small):
        self.big.setText(big)
        self.small.setText(small)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.on_click:
            self.on_click()
        super().mousePressEvent(event)


# ------------------------------------------------------------------ the view
class MyModsView(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_owner = window
        self.sources = []              # (label, kind, payload)
        self.instance = None
        self.profile = None
        self.report = None
        self.workshop = []
        self.filter_kind = ""
        self.busy = False
        self._previews = {}
        lay = column(spacing=10)
        self.setLayout(lay)

        head = row(spacing=10)
        self.game_tile = QLabel()
        self.game_tile.setFixedSize(48, 48)
        head.addWidget(self.game_tile)
        names = column(spacing=2)
        self.title = label("Your mods", "referenceTitle")
        self.title.setStyleSheet("font-size:22px;font-weight:800;")
        self.subtitle = label("", "caption")
        names.addWidget(self.title)
        names.addWidget(self.subtitle)
        head.addLayout(names, 1)
        self.game_pick = QComboBox()
        self.game_pick.setAccessibleName("Pick a game")
        self.game_pick.setMinimumWidth(220)
        self.game_pick.currentIndexChanged.connect(self.pick_game)
        head.addWidget(self.game_pick)
        self.profile_pick = QComboBox()
        self.profile_pick.setAccessibleName("Mod Organizer 2 profile")
        self.profile_pick.setMinimumWidth(140)
        self.profile_pick.currentIndexChanged.connect(self.pick_profile)
        head.addWidget(self.profile_pick)
        self.advanced_button = button("Advanced", lambda: set_mode(window, "advanced"),
                                      tip="The detailed view: load order, profiles, conflicts, cleanup and the "
                                          "crashing-mod finder (Mod Bisect).")
        head.addWidget(self.advanced_button)
        lay.addLayout(head)

        self.banner = QFrame()
        self.banner.setObjectName("mmBanner")
        banner_lay = row(spacing=10, margins=(12, 8, 12, 8))
        self.banner.setLayout(banner_lay)
        self.banner_text = label("", "readyDetail", wrap=True)
        banner_lay.addWidget(self.banner_text, 1)
        self.fix_button = button("Show what needs you", self.show_problems, kind="primary")
        banner_lay.addWidget(self.fix_button)
        lay.addWidget(self.banner)

        cards = row(spacing=10)
        self.health = Card("HEALTH", self.show_problems)
        self.updates = Card("UPDATES", lambda: self.set_filter("update"))
        self.clashes = Card("CLASHES", lambda: self.set_filter("clash"))
        for c in (self.health, self.updates, self.clashes):
            cards.addWidget(c, 1)
        lay.addLayout(cards)

        self.problem_box = QFrame()
        self.problem_box.setObjectName("mmProblems")
        self.problem_box.setStyleSheet("QFrame#mmProblems{background:#0b1016;border:1px solid #2a3442;border-radius:10px;}")
        self.problem_lay = column(spacing=6, margins=(12, 10, 12, 10))
        self.problem_box.setLayout(self.problem_lay)
        self.problem_box.hide()
        lay.addWidget(self.problem_box)

        tools = row(spacing=8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your mods")
        self.search.setAccessibleName("Search your mods")
        self.search.textChanged.connect(lambda *_: self.fill())
        tools.addWidget(self.search, 1)
        self.filter_label = label("", "caption")
        tools.addWidget(self.filter_label)
        self.clear_filter = button("Show all", lambda: self.set_filter(""), kind="actionLink")
        self.clear_filter.hide()
        tools.addWidget(self.clear_filter)
        self.undo_button = button("Undo", self.undo, tip="Puts back your mod list from before Game Grave's last change.")
        tools.addWidget(self.undo_button)
        self.refresh_button = button("Refresh", self.reload, tip="Reads your mods again. Changes nothing.")
        tools.addWidget(self.refresh_button)
        lay.addLayout(tools)

        self.list = QListWidget()
        self.list.setObjectName("mmList")
        self.list.setAccessibleName("Your mods")
        self.list.setStyleSheet("QListWidget#mmList{background:#080c11;border:1px solid #1e2b3a;border-radius:10px;}"
                                "QListWidget#mmList::item{border-bottom:1px solid #141c26;}"
                                "QListWidget#mmList::item:selected{background:#122030;}")
        self.list.setSpacing(0)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.model().rowsMoved.connect(self.dropped)
        lay.addWidget(self.list, 1)
        self.hint = label("", "caption", wrap=True)
        lay.addWidget(self.hint)
        self.load_sources()

    # -------------------------------------------------------------- sources
    def load_sources(self):
        window = self.window_owner
        from manager_profiles import _mo2_roots
        sources = []
        for ini in _mo2_roots(getattr(window.inventory, "mods", [])):
            try:
                inst = mc.read_instance(ini)
            except (mc.ModsError, OSError, ValueError):
                continue
            sources.append((f"{inst.game} · Mod Organizer 2", "mo2", inst))
        try:
            libraries = core.steam_libraries(core._steam_roots(list(window.settings.get("steam_extra_roots", []))))
        except Exception:
            libraries = []
        names = {str(getattr(g, "app_id", "")): g.name for g in getattr(window.inventory, "games", [])}
        for app_id in ws.workshop_games(libraries):
            sources.append((f"{names.get(app_id, 'Steam app ' + app_id)} · Steam Workshop", "workshop", (app_id, libraries)))
        self.sources = sources
        self.game_pick.blockSignals(True)
        self.game_pick.clear()
        for text, _k, _p in sources:
            self.game_pick.addItem(text)
        saved = window.settings.get("mymods_game", "")
        index = next((i for i, (t, _k, _p) in enumerate(sources) if t == saved), 0)
        self.game_pick.setCurrentIndex(index)
        self.game_pick.blockSignals(False)
        if sources:
            self.pick_game(index)
        else:
            self.show_empty()

    def show_empty(self):
        self.title.setText("Your mods")
        self.subtitle.setText("No Mod Organizer 2 setup or Steam Workshop items found yet.")
        self.profile_pick.hide()
        self.set_banner("Run Scan PC to find your mods. Mod Organizer 2 and Steam Workshop games show up here; other "
                        "mod folders are in Advanced.", "info")
        self.fix_button.hide()
        for c, big in ((self.health, "Nothing to check yet"), (self.updates, "No updates known"),
                       (self.clashes, "No clashes known")):
            c.set(big, "")
        self.list.clear()
        self.undo_button.hide()

    def pick_game(self, index):
        if not (0 <= index < len(self.sources)):
            return
        text, kind, payload = self.sources[index]
        window = self.window_owner
        window.settings = dict(window.settings, mymods_game=text)
        self.filter_kind = ""
        self.problem_box.hide()
        if kind == "mo2":
            self.instance = payload
            self.workshop = []
            self.profile_pick.blockSignals(True)
            self.profile_pick.clear()
            for name in payload.profiles:
                self.profile_pick.addItem(name)
            self.profile_pick.setCurrentIndex(max(0, self.profile_pick.findText(payload.selected)))
            self.profile_pick.blockSignals(False)
            self.profile_pick.setVisible(len(payload.profiles) > 1)
            self.reload()
        else:
            self.instance = None
            self.profile = None
            self.profile_pick.hide()
            self.load_workshop(*payload, text)

    def pick_profile(self, _index):
        if self.instance is not None:
            self.reload()

    # -------------------------------------------------------------- Mod Organizer 2
    def reload(self):
        if self.instance is None:
            if self.sources and self.sources[self.game_pick.currentIndex()][1] == "workshop":
                self.pick_game(self.game_pick.currentIndex())
            return
        inst = self.instance
        name = self.profile_pick.currentText() or inst.selected or (inst.profiles[0] if inst.profiles else "")
        self.set_banner("Reading your mods and checking them…", "info")
        self.fix_button.hide()

        def work(_progress):
            profile = mc.read_profile(inst, name)
            return profile, doctor.diagnose(inst, profile)

        def done(result):
            self.profile, self.report = result
            self.show_mo2()

        def failed(message):
            self.set_banner("Couldn't read this profile: " + message.split(":", 1)[-1].strip(), "bad")
        _job(self.window_owner, work, done, failed)

    def show_mo2(self):
        inst, prof, rep = self.instance, self.profile, self.report
        mods = [m for m in prof.mods if m.kind == "mod"]
        on = sum(m.enabled for m in mods)
        self.title.setText(inst.game)
        self.game_tile.setPixmap(tile(inst.game, 48).pixmap())
        self.subtitle.setText(f"{len(mods)} mods, {on} turned on · Mod Organizer 2 · profile \"{prof.name}\"")
        sentence, tone = doctor.status_line(rep)
        self.set_banner(sentence, tone)
        self.fix_button.setVisible(bool(rep.problems))
        problems = rep.problems
        self.health.set(("Everything looks good" if not problems else
                         f"{len(problems)} problem{'s' if len(problems) != 1 else ''} to fix"),
                        problems[0].title if problems else f"Checked {rep.checked_plugins} plugins and every mod folder.")
        ups = rep.updates
        self.updates.set((f"{len(ups)} update{'s' if len(ups) != 1 else ''} ready" if ups else "Nothing to update"),
                         "Click to see them" if ups else "Mod Organizer 2 checks Nexus for these.")
        cl = rep.clashes
        self.clashes.set((f"{len(cl)} pair{'s' if len(cl) != 1 else ''} change the same files" if cl else "No clashes"),
                         (f"{cl[0][0]} wins over {cl[0][1]}" if cl else "No two switched-on mods change the same file.")
                         + (" (big setup: checked the first 400,000 files)" if rep.clash_limited else ""))
        self.undo_button.setVisible(True)
        self.undo_button.setEnabled(bool(mc.snapshots(prof.folder)))
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        if self.problem_box.isVisible() or self.filter_kind == "problem":
            self.show_problems()       # keep "What needs you" current after a fix or an undo
            if not self.problem_box.isVisible() and self.filter_kind == "problem":
                self.filter_kind = ""
        self.hint.setText("Drag a mod to change its order: the lower one wins when two mods change the same file. "
                          "Close Mod Organizer 2 before changing anything here; every change can be undone.")
        self.fill()

    def mo2_row(self, mod):
        rep = self.report
        frame = QWidget()
        lay = row(spacing=10, margins=(10, 6, 10, 6))
        frame.setLayout(lay)
        if mod.kind == "separator":
            text = label(mod.label.upper(), "caption")
            text.setStyleSheet("color:#8fa6c0;font-weight:800;letter-spacing:1px;")
            lay.addWidget(text, 1)
            return frame
        lay.addWidget(tile(mod.name, 34))
        words = column(spacing=1)
        name = label(mod.name, "readyDetail")
        name.setStyleSheet("color:#f2f5f8;font-size:13px;font-weight:700;")
        words.addWidget(name)
        bits = []
        if mod.kind == "base":
            bits.append("Part of the game (managed outside MO2)")
        else:
            if mod.version:
                bits.append(f"version {mod.version}")
            if mod.plugins:
                bits.append(f"{len(mod.plugins)} plugin{'s' if len(mod.plugins) != 1 else ''}")
            if mod.nexus_id:
                bits.append("from Nexus")
        words.addWidget(label(" · ".join(bits), "caption"))
        lay.addLayout(words, 1)
        problem = next((f for f in rep.problems if mod.name in f.mods), None) if rep else None
        if problem is not None:
            lay.addWidget(note(_short(problem), "bad"))
        elif mod.update:
            lay.addWidget(note(f"Update: {mod.version} → {mod.newest}", "warn"))
        elif mod.kind == "mod" and not mod.enabled:
            lay.addWidget(note("Off"))
        if mod.kind == "mod":
            from gg_desktop.settings_page import Switch
            switch = Switch(mod.enabled, name=f"{mod.name} on")
            switch.setToolTip("Turn this mod on or off in Mod Organizer 2 (can be undone).")
            switch.toggled.connect(lambda on, n=mod.name, s=switch: self.toggle([n], on, s))
            lay.addWidget(switch)
        return frame

    # -------------------------------------------------------------- Steam Workshop
    def load_workshop(self, app_id, libraries, text):
        game = text.split(" · ")[0]
        self.title.setText(game)
        self.game_tile.setPixmap(tile(game, 48).pixmap())
        self.undo_button.hide()
        self.list.setDragDropMode(QAbstractItemView.NoDragDrop)
        items = ws.local_items(libraries, app_id)
        cache = ws.load_cache()
        self.workshop = ws.with_names(items, cache)
        self.show_workshop()
        tracker = getattr(self.window_owner, "_games_tracker", None)
        playing = bool(tracker is not None and getattr(getattr(tracker, "ledger", None), "active", None))
        if playing or not items:
            return

        def work(_progress):
            fresh = ws.refresh_names(items, cache)
            if fresh is not cache:
                ws.save_cache(fresh)
            return ws.with_names(items, fresh)

        def done(named):
            if self.instance is None and self.game_pick.currentText() == text:
                self.workshop = named
                self.show_workshop()
                self.fetch_previews()

        def failed(message):
            self.set_banner(f"{len(items)} Workshop items. Steam didn't answer, so some show their number instead of a "
                            "name; Refresh tries again.", "warn")
        _job(self.window_owner, work, done, failed)

    def show_workshop(self):
        items = self.workshop
        waiting = [i for i in items if i.update_waiting]
        removed = [i for i in items if i.removed]
        unnamed = [i for i in items if not i.title and not i.removed]
        total = sum(i.size for i in items)
        self.subtitle.setText(f"{len(items)} Workshop items · {human_size(total)} · names and pictures from Steam")
        if removed:
            self.set_banner(f"{len(removed)} item{'s you have are' if len(removed) != 1 else ' you have is'} no longer on the Workshop. "
                            "Open them in Steam to unsubscribe.", "warn")
        elif waiting:
            self.set_banner(f"{len(waiting)} item{'s have' if len(waiting) != 1 else ' has'} a newer version on Steam. Steam "
                            "downloads it by itself, usually when you start the game.", "info")
        elif unnamed:
            self.set_banner("Getting names and pictures from Steam…", "info")
        else:
            self.set_banner(f"All {len(items)} Workshop items are up to date with Steam.", "good")
        self.fix_button.hide()
        self.health.set(f"{len(removed)} removed from the Workshop" if removed else "All still on the Workshop",
                        "Steam can't update items that were taken down." if removed else "Every item is still listed.")
        self.updates.set(f"{len(waiting)} newer on Steam" if waiting else "Up to date",
                         "Click to see them" if waiting else "Steam updates items when it can.")
        biggest = max(items, key=lambda i: i.size, default=None)
        self.clashes.set(f"Biggest: {biggest.name}" if biggest else "No items", human_size(biggest.size) if biggest else "")
        self.clashes.head.setText("SPACE")
        self.hint.setText("Subscribe and unsubscribe on each item's Steam page (Open in Steam). Game Grave doesn't delete "
                          "Workshop folders: Steam would just download them again.")
        self.fill()

    def ws_row(self, item):
        frame = QWidget()
        lay = row(spacing=10, margins=(10, 6, 10, 6))
        frame.setLayout(lay)
        lay.addWidget(tile(item.name, 44, self._previews.get(item.item_id)))
        words = column(spacing=1)
        name = label(item.name, "readyDetail")
        name.setStyleSheet("color:#f2f5f8;font-size:13px;font-weight:700;")
        name.setToolTip(item.description or item.name)
        words.addWidget(name)
        bits = [human_size(item.size) if item.size else ""]
        if item.steam_updated:
            bits.append("updated " + when(item.steam_updated))
        if item.tags:
            bits.append(", ".join(item.tags[:3]))
        bits.append(f"#{item.item_id}")
        words.addWidget(label(" · ".join(b for b in bits if b), "caption"))
        lay.addLayout(words, 1)
        if item.removed:
            lay.addWidget(note("No longer on the Workshop", "bad"))
        elif item.update_waiting:
            lay.addWidget(note("Newer version on Steam", "warn"))
        open_it = button("Open in Steam", lambda _=False, u=item.page: QDesktopServices.openUrl(QUrl(u)), kind="actionLink",
                         tip="Opens this item's page in Steam, where you can unsubscribe or rate it.")
        lay.addWidget(open_it)
        return frame

    def fetch_previews(self):
        wanted = [i for i in self.workshop if i.preview and ws.preview_allowed(i.preview) and i.item_id not in self._previews][:120]
        if not wanted:
            return
        folder = core.config_dir() / "workshop_previews"

        def work(_progress):
            folder.mkdir(parents=True, exist_ok=True)
            got = {}
            for item in wanted:
                path = folder / f"{item.item_id}.img"
                if not path.is_file():
                    try:
                        request = urllib.request.Request(item.preview, headers={"User-Agent": "GameGrave"})
                        with urllib.request.urlopen(request, timeout=15) as response:
                            data = response.read(3_000_000)
                        path.write_bytes(data)
                    except OSError:
                        continue
                got[item.item_id] = str(path)
            return got

        def done(got):
            for item_id, path in got.items():
                pix = QPixmap(path)
                if not pix.isNull():
                    self._previews[item_id] = pix.scaled(88, 88, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            if self.instance is None:
                self.fill()
        _job(self.window_owner, work, done, lambda _m: None)

    # -------------------------------------------------------------- list
    def set_filter(self, kind):
        self.filter_kind = kind
        self.fill()

    def visible_mods(self):
        text = self.search.text().strip().casefold()
        if self.instance is not None and self.profile is not None:
            rows = list(self.profile.mods)
            if self.filter_kind == "update":
                rows = [m for m in rows if m.update]
            elif self.filter_kind == "clash" and self.report:
                names = {n for w, l, _c in self.report.clashes for n in (w, l)}
                rows = [m for m in rows if m.name in names]
            elif self.filter_kind == "problem" and self.report:
                names = {n for f in self.report.problems for n in f.mods + f.fix_mods}
                rows = [m for m in rows if m.name in names]
            return [m for m in rows if not text or text in m.name.casefold()]
        rows = list(self.workshop)
        if self.filter_kind == "update":
            rows = [i for i in rows if i.update_waiting]
        elif self.filter_kind == "problem":
            rows = [i for i in rows if i.removed]
        return [i for i in rows if not text or text in i.name.casefold() or text in i.item_id]

    def fill(self):
        self.list.clear()
        rows = self.visible_mods()
        whole = not self.filter_kind and not self.search.text().strip()
        self.list.setDragDropMode(QAbstractItemView.InternalMove if (self.instance is not None and whole)
                                  else QAbstractItemView.NoDragDrop)
        words = {"update": "Showing updates", "clash": "Showing mods that clash", "problem": "Showing what needs you"}
        self.filter_label.setText(words.get(self.filter_kind, ""))
        self.clear_filter.setVisible(bool(self.filter_kind))
        for entry in rows[:3000]:
            item = QListWidgetItem()
            widget = self.mo2_row(entry) if self.instance is not None else self.ws_row(entry)
            item.setSizeHint(QSize(10, 34 if getattr(entry, "kind", "") == "separator" else 56))
            item.setData(Qt.UserRole, getattr(entry, "name", ""))
            self.list.addItem(item)
            self.list.setItemWidget(item, widget)
        if not rows:
            self.list.addItem(QListWidgetItem("Nothing matches." if not whole else "No mods here yet."))

    # -------------------------------------------------------------- problems
    def show_problems(self):
        while self.problem_lay.count():
            it = self.problem_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if self.report is None:
            return
        problems = self.report.problems
        if not problems:
            self.problem_box.hide()
            if self.filter_kind == "problem":
                self.filter_kind = ""
                self.fill()
            return
        head = row(spacing=8)
        head.addWidget(label("What needs you", "readyGameTitle"), 1)
        head.addWidget(button("Hide", self.problem_box.hide, kind="actionLink"))
        holder = QWidget()
        holder.setLayout(head)
        self.problem_lay.addWidget(holder)
        for f in problems[:20]:
            line = QWidget()
            lay = row(spacing=8)
            line.setLayout(lay)
            words = column(spacing=1)
            t = label(f.title, "readyDetail", wrap=True)
            t.setStyleSheet("color:#f2f5f8;font-weight:700;")
            words.addWidget(t)
            if f.detail:
                words.addWidget(label(f.detail, "caption", wrap=True))
            lay.addLayout(words, 1)
            if f.fix == "turn_on":
                lay.addWidget(button(f.fix_label, lambda _=False, m=f.fix_mods: self.toggle(list(m), True), kind="primary"))
            self.problem_lay.addWidget(line)
        self.problem_box.show()
        self.filter_kind = "problem"
        self.fill()

    # -------------------------------------------------------------- writes
    def toggle(self, names, on, switch=None):
        if self.busy or self.profile is None:
            if switch is not None:
                switch.blockSignals(True)
                switch.setChecked(not on)
                switch.blockSignals(False)
            return
        from gg_desktop.bisect_apply import mo2_running
        folder = self.profile.folder
        self.busy = True

        def work(_progress):
            mc.set_enabled(folder, names, on, running=mo2_running)
            return ""

        def done(_r):
            self.busy = False
            log_event("mod_toggle", f"Turned {'on' if on else 'off'} in Mod Organizer 2 profile {self.profile.name}: "
                      + ", ".join(names)[:300], result="on" if on else "off", source="mods")
            self.window_owner.status.setText(f"{', '.join(names)[:80]} turned {'on' if on else 'off'}. Undo puts it back.")
            self.reload()

        def failed(message):
            self.busy = False
            if switch is not None:
                switch.blockSignals(True)
                switch.setChecked(not on)
                switch.blockSignals(False)
            self.window_owner.error("Mod not changed", message.split(":", 1)[-1].strip())
        _job(self.window_owner, work, done, failed)

    def dropped(self, *_):
        if self.profile is None or self.busy:
            return
        names = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        if names == [m.name for m in self.profile.mods]:
            return
        from gg_desktop.bisect_apply import mo2_running
        folder = self.profile.folder
        self.busy = True

        def work(_progress):
            mc.reorder(folder, names, running=mo2_running)
            return ""

        def done(_r):
            self.busy = False
            log_event("mod_order", f"Changed the mod order in Mod Organizer 2 profile {self.profile.name}",
                      result="moved", source="mods")
            self.window_owner.status.setText("Mod order changed. Undo puts it back.")
            self.reload()

        def failed(message):
            self.busy = False
            self.window_owner.error("Order not changed", message.split(":", 1)[-1].strip())
            self.fill()
        _job(self.window_owner, work, done, failed)

    def undo(self):
        if self.profile is None or self.busy:
            return
        from gg_desktop.bisect_apply import mo2_running
        folder = self.profile.folder
        try:
            what = mc.undo(folder, running=mo2_running)
        except mc.ModsError as problem:
            self.window_owner.error("Nothing undone", str(problem))
            return
        log_event("mod_undo", f"Undid the last mod change ({what}) in profile {self.profile.name}", result="restored",
                  source="mods")
        self.window_owner.status.setText(f"Undone: {what}.")
        self.reload()

    # -------------------------------------------------------------- banner
    def set_banner(self, text, tone):
        color, back, edge = TONES[tone]
        self.banner.setStyleSheet(f"QFrame#mmBanner{{background:{back};border:1px solid {edge};border-radius:8px;}}")
        self.banner_text.setText(text)
        self.banner_text.setStyleSheet(f"color:{color};font-size:13px;font-weight:700;")


def _short(finding):
    if finding.kind == "needs_mod_on":
        return finding.fix_label.replace("Turn on", "Needs") + " on"
    if finding.kind == "missing_master":
        return "Missing a required file"
    if finding.kind == "folder_missing":
        return "Folder missing"
    if finding.kind == "duplicate":
        return "On twice"
    return "Needs attention"


def _job(window, fn, done, failed):
    from gg_desktop.app import Job
    job = Job(fn)
    key = id(job)
    window.workers[key] = job

    def ok(result):
        window.workers.pop(key, None)
        try:
            done(result)
        except RuntimeError:
            pass

    def bad(message):
        window.workers.pop(key, None)
        try:
            failed(message)
        except RuntimeError:
            pass
    job.signals.done.connect(ok)
    job.signals.failed.connect(bad)
    window.pool.start(job)


# ------------------------------------------------------------------ switching views
def install(window):
    """Adds My Mods to the Mods page and shows it unless the owner picked Advanced."""
    content = window.page.content
    advanced = [content.itemAt(i).widget() for i in range(1, content.count()) if content.itemAt(i).widget() is not None]
    back = QFrame()
    back.setObjectName("mmBack")
    back.setStyleSheet("QFrame#mmBack{background:#0b1016;border:1px solid #233142;border-radius:8px;}")
    back_lay = row(spacing=8, margins=(10, 4, 10, 4))
    back.setLayout(back_lay)
    back_lay.addWidget(label("Advanced view: every detail Game Grave reads about your mods.", "caption"), 1)
    back_lay.addWidget(button("Back to My Mods", lambda: set_mode(window, "simple"), kind="primary"))
    view = MyModsView(window)
    content.insertWidget(1, back)
    content.insertWidget(2, view, 1)
    window.mymods_view, window.mymods_back, window.mymods_advanced = view, back, advanced
    apply_mode(window)
    return view


def apply_mode(window):
    simple = mode(window) == "simple"
    window.mymods_view.setVisible(simple)
    window.mymods_back.setVisible(not simple and not getattr(window, "reference_preview", False))
    for w in window.mymods_advanced:
        w.setVisible(not simple)


def set_mode(window, which):
    window.settings = dict(window.settings, mods_view=which)
    try:
        core.save_settings(window.settings)
    except (OSError, ValueError):
        pass
    apply_mode(window)
