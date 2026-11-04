"""Button presentation with native checkbox and radio-button semantics."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QCheckBox, QRadioButton, QSizePolicy


def _luminance(color):
    values = (color.redF(), color.greenF(), color.blueF())
    values = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in values]
    return sum(value * weight for value, weight in zip(values, (.2126, .7152, .0722)))


def _contrast(first, second):
    dark, light = sorted((_luminance(first), _luminance(second)))
    return (light + .05) / (dark + .05)


def _foreground(background, preferred):
    if _contrast(background, preferred) >= 4.5:
        return preferred
    return max((QColor("black"), QColor("white")), key=lambda value: _contrast(background, value))


def paint_choice_button(painter, rect, text, palette, *, checked=False, mixed=False,
                        enabled=True, hovered=False, pressed=False, focused=False):
    """Paint a labelled choice; delegates keep their original model/accessibility.

    Text is used as supplied, allowing item delegates to use On/Mixed/Off while
    checkbox subclasses retain their original descriptive label.
    """
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    accent = palette.color(QPalette.Highlight)
    active = checked or mixed
    background = QColor(accent if active else palette.color(QPalette.Button))
    foreground = palette.color(QPalette.HighlightedText if active else QPalette.ButtonText)
    border = QColor(accent if active else palette.color(QPalette.Mid))
    if enabled:
        if active and (hovered or pressed):
            white = _contrast(background, QColor("white")) >= _contrast(background, QColor("black"))
            factor = 120 if pressed else 110
            background = background.darker(factor) if white else background.lighter(factor)
        elif hovered or pressed:
            background = palette.color(QPalette.Base)
            border = accent
        foreground = _foreground(background, foreground)
    else:
        background = palette.color(QPalette.Mid if active else QPalette.Button)
        foreground = QColor(palette.color(QPalette.ButtonText))
        foreground.setAlphaF(.5)
        border = palette.color(QPalette.Mid)
    box = QRectF(rect).adjusted(1, 1, -1, -1)
    painter.setPen(QPen(border, 1))
    painter.setBrush(background)
    painter.drawRoundedRect(box, 6, 6)
    if focused and enabled:
        painter.setBrush(Qt.NoBrush)
        focus = _foreground(background, foreground if active else accent)
        painter.setPen(QPen(focus, 2))
        painter.drawRoundedRect(box.adjusted(3, 3, -3, -3), 3, 3)
    painter.setPen(foreground)
    flags = Qt.AlignCenter | Qt.TextWordWrap | Qt.TextShowMnemonic
    painter.drawText(box.adjusted(10, 5, -10, -5), flags, text)
    painter.restore()


class _ButtonPresentation:
    def _initialize_presentation(self):
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMouseTracking(True)

    def _label(self):
        return self.text() + (" (Mixed)" if self._mixed() else "")

    def _mixed(self):
        return isinstance(self, QCheckBox) and self.checkState() == Qt.PartiallyChecked

    def _reserved_label(self):
        return self.text() + (" (Mixed)" if isinstance(self, QCheckBox) and self.isTristate() else "")

    def minimumSizeHint(self):
        return QSize(max(90, self.fontMetrics().horizontalAdvance("Mixed") + 24), self.fontMetrics().height() + 14)

    def sizeHint(self):
        metrics = self.fontMetrics()
        width = min(metrics.horizontalAdvance(self._reserved_label()) + 24, metrics.horizontalAdvance("M" * 32) + 24)
        width = max(self.minimumSizeHint().width(), width)
        return QSize(width, self.heightForWidth(width))

    def heightForWidth(self, width):
        from PySide6.QtCore import QRect

        return self.fontMetrics().boundingRect(
            QRect(0, 0, max(1, width - 24), 10000), Qt.TextWordWrap, self._reserved_label()
        ).height() + 14

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_choice_button(painter, self.rect(), self._label(), self.palette(),
                            checked=self.isChecked(), mixed=self._mixed(), enabled=self.isEnabled(),
                            hovered=self.underMouse(), pressed=self.isDown(), focused=self.hasFocus())


class AccentCheckBox(_ButtonPresentation, QCheckBox):
    """Native boolean/tristate checkbox, rendered as an accent choice button."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._initialize_presentation()


class AccentRadioButton(_ButtonPresentation, QRadioButton):
    """Native exclusive radio button, rendered without a radio bullet."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._initialize_presentation()
