"""Contrast and rendered focus regressions for the scoped desktop theme pilot."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/contact-sheet-test-cache")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDoubleSpinBox, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout,
)

from contact_sheet.themes import apply_theme


def contrast(first, second):
    """WCAG relative-luminance contrast for opaque sRGB colors."""
    def luminance(color):
        color = QColor(color)
        linear = [
            value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
            for value in (color.redF(), color.greenF(), color.blueF())
        ]
        return sum(weight * value for weight, value in zip((.2126, .7152, .0722), linear))
    low, high = sorted((luminance(first), luminance(second)))
    return (high + .05) / (low + .05)


@pytest.fixture(scope="session")
def theme_app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    return app


@pytest.fixture(params=["light", "dark"])
def theme_window(theme_app, request):
    app = theme_app
    old_style, old_palette, old_font = app.styleSheet(), app.palette(), app.font()
    old_dark = app.property("dark")
    apply_theme(app, request.param)
    window = QDialog()
    layout = QVBoxLayout(window)
    primary = QPushButton("Export Sheets…")
    primary.setObjectName("primary")
    anchor = QPushButton("Other action")
    layout.addWidget(primary)
    layout.addWidget(anchor)
    window.resize(320, 240)
    window.show()
    anchor.setFocus(Qt.TabFocusReason)
    app.processEvents()
    yield app, window, primary, anchor
    window.close()
    window.deleteLater()
    app.processEvents()
    app.setStyleSheet(old_style)
    app.setPalette(old_palette)
    app.setFont(old_font)
    app.setProperty("dark", old_dark)


def colors(widget):
    image = widget.grab().toImage()
    middle = image.width() // 2
    # Away from rounded corners and glyphs: outer border and solid inner fill.
    return image.pixelColor(middle, 0), image.pixelColor(middle, 3)


def set_action_state(app, primary, anchor, state):
    primary.setDown(False)
    # Move away first so repeated test positions generate real enter/leave events.
    QTest.mouseMove(anchor, anchor.rect().center())
    if state != "normal":
        QTest.mouseMove(primary, primary.rect().center())
    primary.setDown(state == "pressed")
    app.processEvents()


@pytest.mark.parametrize("state, expected_fill", [
    ("normal", "#2768ad"),
    ("hover", "#2f6db1"),
    ("pressed", "#2463a6"),
])
def test_primary_text_and_focus_contrast(theme_window, state, expected_fill):
    app, window, primary, anchor = theme_window
    set_action_state(app, primary, anchor, state)
    border, fill = colors(primary)
    assert fill.name() == expected_fill
    assert border == fill
    foreground = primary.palette().color(QPalette.ButtonText)
    assert contrast(foreground, fill) >= 4.5

    geometry, hint, contents = primary.geometry(), primary.sizeHint(), primary.contentsRect()
    primary.setFocus(Qt.TabFocusReason)
    app.processEvents()
    assert primary.hasFocus()
    focus, focused_fill = colors(primary)
    assert focused_fill == fill
    assert focus.name() == ("#f4f8ff" if app.property("dark") else "#111111")
    for adjacent in (fill, app.palette().color(QPalette.Window),
                     app.palette().color(QPalette.Button), app.palette().color(QPalette.Base)):
        assert contrast(focus, adjacent) >= 3
    # Focus changes color, never border width, control size, or content placement.
    assert (primary.geometry(), primary.sizeHint(), primary.contentsRect()) == (geometry, hint, contents)


@pytest.mark.parametrize("widget_type", [QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox])
def test_keyboard_focus_is_visible_without_resizing(theme_window, widget_type):
    app, window, primary, anchor = theme_window
    control = widget_type()
    if isinstance(control, QComboBox):
        control.addItem("PDF")
    window.layout().addWidget(control)
    app.processEvents()
    anchor.setFocus(Qt.TabFocusReason)
    QTest.mouseMove(anchor, anchor.rect().center())
    app.processEvents()
    geometry, hint, contents = control.geometry(), control.sizeHint(), control.contentsRect()
    control.setFocus(Qt.TabFocusReason)
    app.processEvents()
    assert control.hasFocus()
    focus, _ = colors(control)
    assert focus.name() == ("#f4f8ff" if app.property("dark") else "#111111")
    for role in (QPalette.Window, QPalette.Button, QPalette.Base):
        assert contrast(focus, app.palette().color(role)) >= 3
    assert (control.geometry(), control.sizeHint(), control.contentsRect()) == (geometry, hint, contents)


def test_secondary_pressed_action_keeps_visible_focus(theme_window):
    app, window, primary, anchor = theme_window
    anchor.setFocus(Qt.TabFocusReason)
    anchor.setDown(True)
    app.processEvents()
    focus, fill = colors(anchor)
    assert contrast(focus, fill) >= 3
    # Qt's palette reports the normal text role even when a :pressed stylesheet
    # changes the painted glyphs, so inspect their rendered interior pixels.
    foreground = app.palette().color(QPalette.HighlightedText)
    image = anchor.grab().toImage()
    assert any(image.pixelColor(x, y) == foreground
               for y in range(10, image.height() - 10)
               for x in range(10, image.width() - 10))
    assert contrast(foreground, fill) >= 4.5


def test_selection_and_progress_text_have_readable_contrast(theme_window):
    app, window, primary, anchor = theme_window
    # Tables, combo selection, and FileProgressBar's filled overlay share these
    # palette roles; the action button uses its separate darker-blue role.
    for group in (QPalette.Active, QPalette.Inactive):
        assert contrast(app.palette().color(group, QPalette.HighlightedText),
                        app.palette().color(group, QPalette.Highlight)) >= 4.5


@pytest.mark.parametrize("files_loaded", [False, True])
def test_disabled_primary_is_neutral_in_every_pointer_state(theme_window, files_loaded):
    app, window, primary, anchor = theme_window
    primary.setProperty("filesLoaded", files_loaded)
    primary.setEnabled(False)
    for state in ("normal", "hover", "pressed"):
        set_action_state(app, primary, anchor, state)
        border, fill = colors(primary)
        assert fill.name() == ("#555555" if app.property("dark") else "#cccccc")
        assert fill.red() == fill.green() == fill.blue()
        assert border == fill
        assert primary.palette().color(QPalette.Disabled, QPalette.ButtonText).name() == (
            "#b5b5b5" if app.property("dark") else "#626262"
        )
