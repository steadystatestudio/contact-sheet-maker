"""MIT © 2026 Steady State Studio. Adapted from File Renamer gui.py.
See THIRD_PARTY_NOTICES.md for exact provenance.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen, QFontMetrics
from PySide6.QtWidgets import QProgressBar

class FileProgressBar(QProgressBar):
    """Padder-style rounded segments and a single centered status message."""

    GAP = 2.0
    MIN_SEGMENT_WIDTH = 5.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_count = 0
        self._message = ""

    def set_message(self, text):
        self._message = text
        self.setToolTip(self.text())
        self.setAccessibleDescription(self.text())
        self.update()

    def setFormat(self, text):
        self._message = ""
        super().setFormat(text)
        self.setToolTip(self.text())
        self.setAccessibleDescription(self.text())
        self.update()

    def text(self):
        return self._message or (self.format() if self.maximum() == 0 else super().text())

    def preview(self, count=0, text="Ready"):
        self.file_count = count
        self.setRange(0, max(count, 1))
        self.setValue(0)
        self.setFormat(text)

    def segments(self):
        inner = QRectF(self.rect()).adjusted(4.5, 4.5, -4.5, -4.5)
        if not self.file_count or inner.width() <= 0:
            return []
        count = min(self.file_count, max(1, int((inner.width() + self.GAP) // (self.MIN_SEGMENT_WIDTH + self.GAP))))
        width = (inner.width() - self.GAP * (count - 1)) / count
        files_per_segment = self.file_count / count
        return [
            (
                QRectF(inner.left() + i * (width + self.GAP), inner.top(), width, inner.height()),
                max(0.0, min(1.0, (self.value() - i * files_per_segment) / files_per_segment)),
            )
            for i in range(count)
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        font = self.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setRenderHint(QPainter.Antialiasing)
        area = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(self.palette().mid().color()))
        painter.setBrush(self.palette().base())
        painter.drawRoundedRect(area, 6, 6)
        filled = QPainterPath()
        painter.setPen(Qt.NoPen)
        for rect, fraction in self.segments():
            painter.setBrush(self.palette().alternateBase())
            painter.drawRoundedRect(rect, 2, 2)
            if fraction:
                rect.setWidth(rect.width() * fraction)
                painter.setBrush(self.palette().highlight())
                painter.drawRoundedRect(rect, 2, 2)
                filled.addRoundedRect(rect, 2, 2)
        text_area = area.adjusted(10, 0, -10, 0)
        display_text = " ".join(self.text().splitlines())
        text = QFontMetrics(font).elidedText(display_text, Qt.ElideRight, max(0, int(text_area.width())))
        painter.setPen(self.palette().text().color())
        painter.drawText(text_area, Qt.AlignCenter, text)
        painter.setClipPath(filled)
        painter.setPen(self.palette().highlightedText().color())
        painter.drawText(text_area, Qt.AlignCenter, text)


