"""Compact filename/path rows; native selection and checkboxes stay authoritative."""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication

PATH_ROLE = Qt.UserRole + 1


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
