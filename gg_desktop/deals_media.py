"""Deals: screenshots and trailers while you look at a game (owner, 2026-11-27: "if you can browse photos and videos even
better while checking out the games"). A strip of Steam's own store media under the game's prices, and a viewer window:
pictures with Back / Next (arrow keys too), trailers played inside Game Grave with sound, pause and a seek bar. If this PC
can't play a trailer, it opens on Steam's page in the browser instead. Only Steam's app number is sent; links are only https
on Steam's own hosts (deals_core.parse_media)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider, QVBoxLayout,
                               QWidget)
from shiboken6 import isValid

from gg_desktop import deals_core as dc

THUMB = QSize(168, 94)
STYLE = """
QDialog#mediaViewer { background:#05080b; }
QLabel#mediaCaption { color:#c9d4e0; font-size:12px; }
QPushButton#mediaNav { background:#141c25; color:#e8eef5; border:1px solid #26313d; border-radius:8px; padding:6px 14px;
                       font-size:13px; }
QPushButton#mediaNav:hover { background:#1c2732; }
QPushButton#mediaThumb { border:1px solid #1f2933; border-radius:6px; background:#0d141b; padding:0; }
QPushButton#mediaThumb:hover { border:1px solid #ff4357; }
"""


def strip(page_window):
    """The empty strip; `fill` puts a game's media in it."""
    frame = QFrame()
    frame.setObjectName("dealsMedia")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(0, 2, 0, 2)
    lay.setSpacing(4)
    frame.caption = QLabel("")
    frame.caption.setObjectName("dealsNote")
    frame.caption.setWordWrap(True)
    lay.addWidget(frame.caption)
    frame.scroll = QScrollArea()
    frame.scroll.setWidgetResizable(True)
    frame.scroll.setFrameShape(QFrame.NoFrame)
    frame.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    frame.scroll.setFixedHeight(THUMB.height() + 18)
    frame.scroll.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
    holder = QWidget()
    frame.row = QHBoxLayout(holder)
    frame.row.setContentsMargins(0, 0, 0, 0)
    frame.row.setSpacing(8)
    frame.row.addStretch(1)
    frame.scroll.setWidget(holder)
    lay.addWidget(frame.scroll)
    frame.setStyleSheet(STYLE)
    frame.hide()
    return frame


def _clear(row):
    while row.count():
        item = row.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()


def _play_mark(pix):
    """A thumbnail with a round play mark, so trailers read as videos."""
    out = QPixmap(pix)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    r = min(out.width(), out.height()) // 4
    cx, cy = out.width() // 2, out.height() // 2
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(0, 0, 0, 150))
    painter.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
    painter.setBrush(QColor("#ffffff"))
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF
    painter.drawPolygon(QPolygonF([QPointF(cx - r * .35, cy - r * .5), QPointF(cx - r * .35, cy + r * .5),
                                   QPointF(cx + r * .55, cy)]))
    painter.end()
    return out


def fill(window, frame, title, shots, movies, picture, on_pick=None):
    """Show trailers first, then screenshots, as clickable thumbnails. `picture(url, size, label, after)` loads images.
    `on_pick(index)` shows the picked one (the game page's big area); without it the viewer window opens."""
    _clear(frame.row)
    items = [("video", name, thumb, url) for name, thumb, url in movies] + \
            [("shot", f"Screenshot {n + 1}", thumb, full) for n, (thumb, full) in enumerate(shots)]
    frame.items = items
    if not items:
        frame.hide()
        return
    words = []
    if movies:
        words.append(f"{len(movies)} trailer{'s' if len(movies) != 1 else ''}")
    if shots:
        words.append(f"{len(shots)} screenshot{'s' if len(shots) != 1 else ''}")
    frame.caption.setText(" and ".join(words) + " from Steam's store page. Pick one to show it above.")
    for index, (kind, name, thumb, _url) in enumerate(items):
        control = QPushButton()
        control.setObjectName("mediaThumb")
        control.setFixedSize(THUMB.width() + 2, THUMB.height() + 2)
        control.setIconSize(THUMB)
        control.setCursor(Qt.PointingHandCursor)
        control.setToolTip(f"Play: {name}" if kind == "video" else name)
        control.setAccessibleName(f"{'Play trailer' if kind == 'video' else 'View'} {name} for {title}")
        control.clicked.connect(lambda _=False, i=index: on_pick(i) if on_pick else open_viewer(window, frame, title, i,
                                                                                              picture))
        label = QLabel(control)
        label.setGeometry(1, 1, THUMB.width(), THUMB.height())
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        if kind == "video":
            picture(thumb, THUMB, label, lambda lab: isValid(lab) and lab.pixmap() is not None and
                    not lab.pixmap().isNull() and lab.setPixmap(_play_mark(lab.pixmap())))
        else:
            picture(thumb, THUMB, label, None)
        frame.row.insertWidget(frame.row.count() - 1, control)
    frame.show()
    if on_pick:                               # the first screenshot shows in the big area; trailers play when picked
        first = next((i for i, item in enumerate(items) if item[0] == "shot"), None)
        if first is not None:
            on_pick(first)


def video_player():
    """(QMediaPlayer, QAudioOutput, FrameView) when this PC's Qt can play video, else None.

    Trailers are decoded on the processor and drawn by Game Grave itself (FrameView), not through the graphics card's
    video path: on some graphics cards and drivers Qt's hardware path shows only a black box (owner, 2026-11-28). The two
    settings only affect Game Grave's own video player and are set before Qt's video part first loads."""
    import os
    os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", ",")     # an empty list: no hardware decoders
    os.environ.setdefault("QT_DISABLE_HW_TEXTURES_CONVERSION", "1")
    try:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink  # noqa: F401
        return QMediaPlayer, QAudioOutput, FrameView
    except Exception:
        return None


class FrameView(QWidget):
    """Draws each video frame itself, scaled to fit with black bars. Pass `view.sink` to QMediaPlayer.setVideoOutput.
    `frames` counts the frames that arrived, so a trailer that plays without any picture can be noticed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtMultimedia import QVideoSink
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._frame)
        self.image = None
        self.frames = 0
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMinimumSize(320, 180)

    def _frame(self, frame):
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self.image = image
        self.frames += 1
        self.update()

    def clear(self):
        self.image = None
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        if self.image is not None:
            size = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
            x = (self.width() - size.width()) // 2
            y = (self.height() - size.height()) // 2
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(QRectF(x, y, size.width(), size.height()), self.image)
        p.end()


class MediaViewer(QDialog):
    """Big picture or trailer, with Back and Next through everything in the strip."""

    def __init__(self, window, frame, title, index, picture, app_page=""):
        super().__init__(window)
        self.setObjectName("mediaViewer")
        self.setStyleSheet(STYLE)
        self.setWindowTitle(f"Game Grave · {title}")
        self.items, self.index, self.picture, self.title = list(frame.items), index, picture, title
        self.app_page = app_page
        self.resize(1100, 700)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(8)
        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(640, 360)
        self.view.setStyleSheet("background:#000;border-radius:8px;")
        lay.addWidget(self.view, 1)
        self.player = self.video = self.audio = None
        self.can_play = video_player() is not None   # the player itself is made only when a trailer is shown
        self.lay = lay
        self.setAttribute(Qt.WA_DeleteOnClose)        # closing frees the window and any player with it
        controls = QHBoxLayout()
        self.back = QPushButton("‹  Back")
        self.next = QPushButton("Next  ›")
        self.pause = QPushButton("Pause")
        for control in (self.back, self.pause, self.next):
            control.setObjectName("mediaNav")
            control.setCursor(Qt.PointingHandCursor)
        self.back.clicked.connect(lambda: self.show_item(self.index - 1))
        self.next.clicked.connect(lambda: self.show_item(self.index + 1))
        self.pause.clicked.connect(self.toggle_pause)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setAccessibleName("Trailer position")
        self.caption = QLabel("")
        self.caption.setObjectName("mediaCaption")
        controls.addWidget(self.back)
        controls.addWidget(self.pause)
        controls.addWidget(self.seek, 1)
        controls.addWidget(self.caption)
        controls.addWidget(self.next)
        lay.addLayout(controls)
        self.show_item(index)

    def _ensure_player(self):
        if self.player is not None:
            return True
        classes = video_player()
        if not classes:
            return False
        QMediaPlayer, QAudioOutput, FrameView = classes
        self.video = FrameView()
        self.video.setMinimumSize(640, 360)
        self.lay.insertWidget(1, self.video, 1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.6)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video.sink)
        self.player.errorOccurred.connect(self.video_failed)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, max(0, int(d))))
        self.player.positionChanged.connect(lambda p: self.seek.blockSignals(True) or self.seek.setValue(int(p))
                                            or self.seek.blockSignals(False))
        self.seek.sliderMoved.connect(lambda v: self.player.setPosition(int(v)))
        return True

    def show_item(self, index):
        if not self.items:
            return
        self.index = index % len(self.items)
        kind, name, thumb, url = self.items[self.index]
        self.caption.setText(f"{name} · {self.index + 1} of {len(self.items)}")
        is_video = kind == "video"
        self.pause.setVisible(is_video and self.can_play)
        self.seek.setVisible(is_video and self.can_play)
        if self.player is not None:
            self.player.stop()
        if is_video and self.can_play and self._ensure_player():
            self.view.hide()
            self.video.clear()
            self.video.frames = 0
            self.video.show()
            self.pause.setText("Pause")
            self.player.setSource(QUrl(url))
            self.player.play()
            self._watch(url, 0)
            return
        if self.video is not None:
            self.video.hide()
        self.view.show()
        if is_video:                       # this PC's Qt can't play video: the trailer opens on Steam instead
            self.view.setText("This PC can't play the trailer inside Game Grave.\nPress Open on Steam to watch it there.")
            self.offer_steam(url)
            return
        self.view.setText("Loading…")
        size = QSize(max(640, self.view.width()), max(360, self.view.height()))
        self.picture(url, size, self.view, None)

    def offer_steam(self, url):
        from gg_desktop.deals_page import open_url
        open_url(self.app_page or url)

    def _watch(self, url, ticks):
        """Time moving with no picture arriving counts as a trailer that can't play here (never a black box)."""
        from PySide6.QtCore import QTimer
        if self.player is None or self.player.source() != QUrl(url) or self.video.frames:
            return
        if self.player.position() > 3000:
            self.player.stop()
            self.video_failed()
            return
        if ticks < 60:
            QTimer.singleShot(500, lambda: isValid(self) and self._watch(url, ticks + 1))

    def video_failed(self, *_args):
        if self.items and self.items[self.index][0] == "video" and self.video is not None:
            self.video.hide()
            self.view.show()
            self.view.setText("The trailer couldn't play here, so it opened on Steam's page in your browser.")
            self.offer_steam(self.items[self.index][3])

    def toggle_pause(self):
        if self.player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.pause.setText("Play")
        else:
            self.player.play()
            self.pause.setText("Pause")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.show_item(self.index - 1)
        elif event.key() == Qt.Key_Right:
            self.show_item(self.index + 1)
        elif event.key() == Qt.Key_Space and self.items[self.index][0] == "video":
            self.toggle_pause()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.player is not None:
            self.player.stop()
        super().closeEvent(event)

    def reject(self):
        if self.player is not None:
            self.player.stop()
        super().reject()


def open_viewer(window, frame, title, index, picture):
    app = getattr(frame, "app_id", "")
    page = f"https://store.steampowered.com/app/{app}/" if str(app).isdigit() else ""
    viewer = MediaViewer(window, frame, title, index, picture, page)
    window.deals_media_viewer = viewer
    viewer.show()
    return viewer
