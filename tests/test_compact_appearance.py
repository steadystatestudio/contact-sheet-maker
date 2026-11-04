from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton

from contact_sheet.appearance import configure_appearance
from contact_sheet.choice_buttons import AccentCheckBox
from contact_sheet.gui import MainWindow, SettingsDialog
from contact_sheet.themes import apply_theme


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(settings)
    screen = SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 3440, 1392),
                             availableGeometryChanged=app.primaryScreen().availableGeometryChanged)
    monkeypatch.setattr(w, "screen", lambda: screen)
    w.show(); QTest.qWait(80)
    yield app, w
    w.close(); w.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def test_saved_font_and_accent_reach_everyday_surfaces_and_fitted_settings(window):
    app, w = window
    w.settings.setValue("appearance/font_mode", "custom")
    w.settings.setValue("appearance/font_family", app.font().family())
    w.settings.setValue("appearance/font_size_pt", 18)
    w.settings.setValue("appearance/accent_mode", "custom")
    w.settings.setValue("appearance/accent", "#d34f91")
    for theme in ("light", "dark", "system"):
        w.settings.setValue("theme", theme)
        configure_appearance(app, w.settings)
        apply_theme(app, theme)
        QTest.qWait(40)
        for widget in (w.add_files, w.export_button, w.status, w.table, w.captions, w.title_input):
            assert widget.font().pointSizeF() == 18
        assert app._studio_appearance_values["accent"] == "#d34f91"
    dialog = SettingsDialog(w.settings, w)
    dialog.show()
    app.processEvents()
    assert dialog.minimumSize() == dialog.maximumSize()
    assert dialog.controls.font_size.value() == 18
    assert not any("copy appearance" in button.text().lower() for button in dialog.findChildren(QPushButton))
    dialog.reject()


def test_captions_is_keyboard_checkbox_and_updates_export_options(window):
    app, w = window
    assert isinstance(w.captions, (AccentCheckBox, QCheckBox))
    assert w.sheet_settings().captions
    w.captions.setFocus(); QTest.keyClick(w.captions, Qt.Key_Space)
    assert not w.sheet_settings().captions
    QTest.keyClick(w.captions, Qt.Key_Space)
    assert w.sheet_settings().captions


def test_complete_export_row_stays_horizontal_at_measured_minimum(window):
    app, w = window
    w.resize(1800, 1000); QTest.qWait(60)
    wide_height = w.output_controls.height()
    wide_center = w.export_button.geometry().center().x()
    assert abs(wide_center - w.output_controls.width() / 2) < 3
    w.resize(1, 1); QTest.qWait(100)
    assert not w._compact_output and not w._compact_toolbar
    assert w.output_controls.height() == wide_height
    assert w.output_left.geometry().right() < w.export_button.geometry().left()
    assert w.export_button.geometry().right() < w.output_right.geometry().left()
    assert w.work_scroll.verticalScrollBar().maximum() == 0
    assert w.preview.height() >= 230


def test_short_work_area_reserves_vertical_bar_without_horizontal_form_overflow(window, monkeypatch):
    import time

    app, w = window
    w.settings.setValue("appearance/font_mode", "custom")
    w.settings.setValue("appearance/font_family", app.font().family())
    w.settings.setValue("appearance/font_size_pt", 14)
    configure_appearance(app, w.settings)
    apply_theme(app, "system")
    assert w.font().pointSizeF() == 14
    screen = SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 1920, 480),
                             availableGeometryChanged=app.primaryScreen().availableGeometryChanged)
    monkeypatch.setattr(w, "screen", lambda: screen)
    w.window_size_guard.update()
    w.resize(1, 1)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        app.processEvents()
        if (w.size() == w.minimumSize()
                and w.work_scroll.verticalScrollBar().maximum() > 0
                and w.work_scroll.horizontalScrollBar().maximum() == 0):
            break
        QTest.qWait(15)
    assert w.work_scroll.verticalScrollBar().maximum() > 0
    assert w.work_scroll.horizontalScrollBar().maximum() == 0, (
        w.size().toTuple(), w.minimumSize().toTuple(),
        w.work_scroll.viewport().size().toTuple(), w.work_scroll.widget().minimumSizeHint().toTuple())
    assert w.font().pointSizeF() == 14
    next_bounds = QRect(w.next_button.mapTo(w.work_scroll.viewport(), QPoint()), w.next_button.size())
    assert w.work_scroll.viewport().rect().contains(next_bounds)
