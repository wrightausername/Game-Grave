"""Compact filename/path rows; native selection and checkboxes stay authoritative."""
from PySide6.QtCore import Qt, QRect, QObject, QEvent, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication

PATH_ROLE = Qt.UserRole + 1


class _EvidenceColumnFit(QObject):
    def __init__(self, table, weights):
        super().__init__(table)
        self.table = table
        self.weights = weights
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fit)
        table.horizontalHeader().setStretchLastSection(False)
        table.viewport().installEventFilter(self)
        self.schedule()

    def schedule(self):
        if not self.timer.isActive():
            self.timer.start(0)

    def fit(self):
        width = self.table.viewport().width()
        total = sum(self.weights)
        remaining = width
        for index, weight in enumerate(self.weights):
            size = max(50, round(width * weight / total))
            if index == len(self.weights) - 1:
                size = max(50, remaining)
            self.table.setColumnWidth(index, size)
            remaining -= size

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            self.schedule()
        return False


def fit_evidence_columns(table, weights):
    """Keep status and size visible beside paths as a workspace resizes."""
    table._evidence_column_fit = _EvidenceColumnFit(table, weights)


class EvidenceNameDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        path = index.data(PATH_ROLE)
        if not path:
            return super().paint(painter, option, index)
        view = QStyleOptionViewItem(option)
        self.initStyleOption(view, index)
        title = view.text
        view.text = ""
        style = view.widget.style() if view.widget else QApplication.style()
        painter.save()
        style.drawControl(QStyle.CE_ItemViewItem, view, painter, view.widget)
        area = style.subElementRect(QStyle.SE_ItemViewItemText, view, view.widget).adjusted(3, 1, -3, -1)
        selected = bool(view.state & QStyle.State_Selected)
        font = QFont(view.font)
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF" if selected else "#DFE6F0"))
        painter.drawText(QRect(area.x(), area.y()+1, area.width(), 14),
                         Qt.AlignVCenter, painter.fontMetrics().elidedText(title, Qt.ElideRight, area.width()))
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QColor("#D5B7C2" if selected else "#8394A8"))
        painter.drawText(QRect(area.x(), area.y()+16, area.width(), 12),
                         Qt.AlignVCenter, painter.fontMetrics().elidedText(str(path), Qt.ElideMiddle, area.width()))
        painter.restore()
