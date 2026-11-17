"""Pictures the Gravekeeper can put in a chat answer: a bar chart drawn from the scanned figures, or a game's card.

Display only. Every bar and number comes from what the scans reported (the same figures the tabs show), never from the
model's words, so a picture can't say something the data doesn't. Sizes are "reported", never "freed".
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core import human_size

COLORS = ("#ff3b57", "#13bcf5", "#32d67a", "#f6be24", "#b07cff", "#ff8a3d", "#5be3c9", "#e8eef5")


def chart_rows(facts, kind):
    """(title, [(label, value bytes, caption)]) for a chart, from the facts. Pure, so it can be tested."""
    rows = []
    if kind == "games":
        games = sorted((g for g in getattr(facts, "games", ()) if g.size_bytes), key=lambda g: -g.size_bytes)[:8]
        rows = [(g.name, float(g.size_bytes), human_size(g.size_bytes)) for g in games]
        return "Your biggest games (as the launchers report them)", rows
    if kind == "drives":
        specs = getattr(facts, "hardware", None)
        for d in getattr(specs, "drives", ()) or ():
            used = max(0, d.total - d.free)
            rows.append((f"Drive {d.letter}", float(used), f"{human_size(d.free)} free of {human_size(d.total)}",
                         float(d.total)))
        return "Drives: used and free", rows
    games = sum(float(g.size_bytes) for g in getattr(facts, "games", ()) if g.size_bytes)
    if games:
        rows.append(("Games", games, human_size(games)))
    groups = (("Caches and other data", "storage", "size"), ("Old files", "old_files", "size"))
    for title, attr, field in groups:
        total = sum(max(0, getattr(i, field, 0) or 0) for i in getattr(facts, attr, ()) or ())
        if total:
            rows.append((title, float(total), human_size(total)))
    captures = sum(max(0, getattr(getattr(c, "record", None), "size", 0) or 0) for c in getattr(facts, "captures", ()) or ())
    if captures:
        rows.append(("Screenshots and recordings", float(captures), human_size(captures)))
    mods = sum(max(0, getattr(m, "apparent_bytes", 0) or 0) for m in getattr(facts, "mods", ()) or ())
    if mods:
        rows.append(("Mods", float(mods), human_size(mods)))
    rows.sort(key=lambda r: -r[1])
    return "Where your space goes (reported sizes)", rows


class Bars(QWidget):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.setMinimumHeight(26 * max(1, len(rows)) + 6)
        self.setMinimumWidth(260)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        label_w = min(190, int(width * 0.38))
        top = max([r[3] if len(r) > 3 else r[1] for r in self.rows] or [1]) or 1
        font = QFont(self.font())
        font.setPointSizeF(max(8.0, font.pointSizeF() - 0.5))
        p.setFont(font)
        for i, r in enumerate(self.rows):
            y = 4 + i * 26
            p.setPen(QColor("#cfd9e2"))
            p.drawText(QRectF(0, y, label_w - 8, 20), Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(r[0], Qt.ElideRight, label_w - 10))
            track = QRectF(label_w, y + 5, max(40, width - label_w - 130), 10)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#17212b"))
            p.drawRoundedRect(track, 5, 5)
            whole = r[3] if len(r) > 3 else top
            share = max(0.02, min(1.0, r[1] / whole if whole else 0))
            p.setBrush(QColor(COLORS[i % len(COLORS)]))
            p.drawRoundedRect(QRectF(track.x(), track.y(), track.width() * share, track.height()), 5, 5)
            p.setPen(QColor("#8a96a8"))
            p.drawText(QRectF(track.right() + 8, y, 124, 20), Qt.AlignVCenter | Qt.AlignLeft, r[2])
        p.end()


def _frame(title):
    box = QFrame()
    box.setObjectName("assistantVisual")
    box.setStyleSheet("QFrame#assistantVisual{background:#0b121a;border:1px solid #1b2633;border-radius:10px;}")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(6)
    head = QLabel(title)
    head.setStyleSheet("color:#ffffff;font-weight:700;font-size:12px;border:0;")
    lay.addWidget(head)
    return box, lay


def chart(window, kind):
    from gg_desktop import assistant_page
    title, rows = chart_rows(assistant_page.make_facts(window), kind)
    if not rows:
        return None
    box, lay = _frame(title)
    lay.addWidget(Bars(rows))
    box.setAccessibleName(title + ": " + "; ".join(f"{r[0]} {r[2]}" for r in rows))
    return box


def game_card(window, name):
    games = getattr(getattr(window, "inventory", None), "games", []) or []
    game = next((g for g in games if g.name == name), None)
    if game is None:
        return None
    from datetime import datetime
    from gg_desktop.ready_room import ArtThumb
    box, lay = _frame(game.name)
    line = QHBoxLayout()
    line.setSpacing(12)
    line.addWidget(ArtThumb(getattr(window, "artwork", None), game.key, "", "portrait", 120, 56))
    played = "never or unknown"
    if game.last_played_at:
        days = max(0, int((datetime.now().timestamp() - float(game.last_played_at)) // 86400))
        played = "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"
    facts = QLabel(f"{game.launcher} · {human_size(game.size_bytes) if game.size_bytes else 'size unknown'}\n"
                   f"Last played: {played}\n{game.install_path}")
    facts.setTextFormat(Qt.PlainText)
    facts.setWordWrap(True)
    facts.setStyleSheet("color:#cfd9e2;font-size:12px;border:0;")
    line.addWidget(facts, 1)
    lay.addLayout(line)
    return box


def widget_for(window, visual):
    try:
        if visual.get("chart"):
            return chart(window, visual["chart"])
        if visual.get("game"):
            return game_card(window, visual["game"])
    except Exception:          # a picture must never break the chat
        return None
    return None
