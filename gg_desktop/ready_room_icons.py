"""Small, local SVG line icons. No platform-dependent Unicode pictographs."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel


PATHS = {
    "home": '<path d="m3 10 9-8 9 8v11h-7v-7h-4v7H5V10"/>',
    "radio": '<path d="M8 5a10 10 0 0 0 0 14M4 2a15 15 0 0 0 0 20M16 5a10 10 0 0 1 0 14M20 2a15 15 0 0 1 0 20M12 11v10"/><circle cx="12" cy="8" r="2"/>',
    "gamepad": '<path d="M7 5h10c3 0 5 6 5 11 0 4-3 4-6-1H8c-3 5-6 5-6 1 0-5 2-11 5-11Z M7 8v6M4 11h6"/><circle cx="16" cy="10" r=".8"/><circle cx="19" cy="13" r=".8"/>',
    "puzzle": '<path d="M9 3H4v6a3 3 0 1 0 0 6v6h6a3 3 0 1 1 6 0h5v-6a3 3 0 1 0 0-6V3h-6a3 3 0 1 0-6 0Z"/>',
    "archive": '<path d="M4 7v14h16V7M3 3h18v4H3zM9 11h6"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 4 18 4 18 0V5M3 12c0 4 18 4 18 0M3 17c0 4 18 4 18 0"/>',
    "camera": '<path d="M3 7h4l2-3h6l2 3h4v14H3z"/><circle cx="12" cy="13" r="4"/>',
    "grave": '<path d="M5 21V9a7 7 0 0 1 14 0v12M2 21h20M12 6v9M9 9h6"/>',
    "dna": '<path d="M5 2c0 9 14 11 14 20M19 2C19 11 5 13 5 22M6 5h12M8 9h8M8 15h8M6 19h12"/>',
    "undo": '<path d="M3 10a9 9 0 1 1 1 8M3 3v7h7M12 7v6l4 2"/>',
    "sparkles": '<path d="m9 3 2 6 6 2-6 2-2 7-2-7-6-2 6-2zM19 2l1 3 3 1-3 1-1 3-1-3-3-1 3-1zM20 15v6M17 18h6"/>',
    "settings": '<path d="m10 2-1 3-3-1-2 3 2 3-3 1v4l3 1-1 3 3 2 3-2 1 3h4l1-3 3 1 2-3-2-3 2-1v-4l-3-1 1-3-3-2-3 2-1-3z"/><circle cx="12" cy="12" r="4"/>',
    "grid": '<rect x="3" y="3" width="6" height="7" rx="1"/><rect x="15" y="3" width="6" height="7" rx="1"/><rect x="3" y="14" width="6" height="7" rx="1"/><rect x="15" y="14" width="6" height="7" rx="1"/>',
    "search": '<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 6 6"/>',
    "bell": '<path d="M4 17h16l-2-4V9a6 6 0 0 0-12 0v4zM10 21h4M12 1v2"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 4 3c-1 1-1 1-1 3M12 18h.01"/>',
    "minus": '<path d="M5 12h14"/>',
    "square": '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    "close": '<path d="m5 5 14 14M19 5 5 19"/>',
    "arrow": '<path d="M4 12h16m-5-5 5 5-5 5"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "megaphone": '<path d="m3 10 16-6v16L3 14zM7 16l2 6h3l-2-7M22 9v6"/>',
    "cube": '<path d="m12 2 10 5v10l-10 5-10-5V7zM2 7l10 5 10-5M12 12v10M7 4l10 5"/>',
    "calendar": '<rect x="3" y="5" width="18" height="17" rx="1"/><path d="M3 10h18M7 2v6M17 2v6M7 14h2M13 14h2M7 18h2"/>',
    "download": '<path d="M12 2v14m-6-6 6 6 6-6M3 15v7h18v-7"/>',
    "star": '<path d="m12 2 3 7 8 1-6 5 2 8-7-4-7 4 2-8-6-5 8-1z"/>',
    "layers": '<path d="m2 6 10-5 10 5-10 5z" fill="currentColor" stroke="none"/><path d="m2 11 10 5 10-5M2 16l10 5 10-5" stroke-width="3.5"/>',
    "shield": '<path d="m12 2 9 4-1 10-8 6-8-6L3 6zM7 12l3 3 7-7"/>',
    "wrench": '<path d="m14 7 3 3 5-5a7 7 0 0 1-9 9L6 21a2 2 0 0 1-3-3l7-7a7 7 0 0 1 9-9z"/>',
    "sync": '<path d="M3 9a9 9 0 0 1 16-4l2 3M21 2v6h-6M21 15a9 9 0 0 1-16 4l-2-3M3 22v-6h6"/>',
    "wand": '<path d="m3 21 13-13 3 3L6 24zM14 3h6M17 0v6M4 6h6M7 3v6M20 16h4M22 14v4"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 5v7l4 3"/>',
    "cloud": '<path d="M6 20H5A5 5 0 0 1 5 10a7 7 0 0 1 13-2 6 6 0 0 1 1 12h-1M12 23V11m-4 4 4-4 4 4"/>',
    "pulse": '<path d="M1 13h6l3-10 4 20 3-13 2 3h4"/>',
    "save": '<path d="M3 2h15l4 4v16H2V2zM7 2v7h10V2M7 22V13h10v9"/>',
    "warning": '<path d="m12 2 11 20H1zM12 8v6M12 18h.01"/>',
    "scan": '<circle cx="12" cy="12" r="6"/><path d="M12 1v3M12 20v3M1 12h3M20 12h3M4 4l2 2M18 18l2 2M4 20l2-2M18 6l2-2"/>',
}


def icon(name: str, color="#D9DCE0", size=24) -> QIcon:
    body = PATHS.get(name, PATHS["grid"])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" color="{color}" '
           f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.65" '
           f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    # SVG-backed QIcon stays sharp under Windows display scaling.
    from PySide6.QtGui import QPainter
    pixmap = QPixmap(size * 3, size * 3)
    pixmap.fill("transparent")
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(3)
    result = QIcon(pixmap)
    return result


def icon_label(name: str, color="#D9DCE0", size=24) -> QLabel:
    result = QLabel()
    result.setFixedSize(size, size)
    result.setPixmap(icon(name, color, size).pixmap(QSize(size, size)))
    result.setAccessibleName(name.replace("_", " "))
    return result
