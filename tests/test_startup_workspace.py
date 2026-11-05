"""Fresh startup fits the measured workspace and preserves restored geometry."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import (
    QByteArray,
    QCoreApplication,
    QEvent,
    QObject,
    QRect,
    QSettings,
    QSize,
    Signal,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMainWindow

from contact_sheet import app as entry, gui, window_size


@pytest.fixture
def startup(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    original_font = app.font()
    font = QFont(original_font)
    font.setPointSizeF(10)
    app.setFont(font)

    class Provider(QObject):
        changed = Signal()
        enabled = True
        last_details = {"source": "x11-ewmh"}

        def refresh(self):
            pass

    area = QRect(0, 0, 1280, 768)
    provider = Provider()
    monkeypatch.setattr(window_size, "workarea_provider", lambda instance: provider)
    monkeypatch.setattr(window_size, "available_geometry", lambda *_: area)
    monkeypatch.setattr(window_size, "observe_window_screen", lambda *a, **kw: None)
    monkeypatch.setattr(gui, "available_geometry", lambda *_: area)
    monkeypatch.setattr(gui, "configure_appearance", lambda *a, **kw: None)
    monkeypatch.setattr(gui, "apply_theme", lambda *a, **kw: None)
    settings = QSettings(str(tmp_path / "startup.ini"), QSettings.IniFormat)
    settings.setFallbacksEnabled(False)
    windows = []

    def create():
        window = gui.MainWindow(settings)
        windows.append(window)
        return window

    try:
        yield SimpleNamespace(app=app, settings=settings, create=create, area=area)
    finally:
        for window in windows:
            window.window_size_guard.timer.stop()
            window.window_size_guard._geometry_diagnostics_timer.stop()
            window.close()
            window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        app.setFont(original_font)


def test_fresh_default_reserves_the_decorated_normal_workspace(startup):
    window = startup.create()
    width = window.width()
    font = window.font()
    preview_floor = window.preview.minimumSize()
    entry._prepare_window(window)
    wanted = window.window_size_guard.preferredMinimum
    # This controlled native-frame fixture fits the measured useful floor.
    # A request for the whole undecorated work area would exceed it on mapping.
    frame_height = 60
    assert wanted.height() + frame_height <= startup.area.height()
    assert window.height() + frame_height <= startup.area.height()
    assert window.height() >= wanted.height()
    assert window.width() == width
    assert window.font() == font
    assert window.preview.minimumSize() == preview_floor
    assert preview_floor.height() >= 230
    assert not window.isVisible()


def test_saved_usable_geometry_is_preserved_instead_of_refitted_to_default(startup):
    seed = QMainWindow()
    try:
        seed.resize(1080, 700)
        geometry = seed.saveGeometry()
    finally:
        seed.close()
        seed.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    startup.settings.setValue("geometry", geometry)
    window = startup.create()
    before = QSize(window.size())
    font = window.font()
    entry._prepare_window(window)
    assert window.size() == before
    assert before.height() == 700
    assert window.height() > window.window_size_guard.preferredMinimum.height()
    assert startup.settings.value("geometry") == geometry
    assert window.font() == font
    assert window.preview.minimumHeight() >= 230
    assert window.height() >= window.window_size_guard.preferredMinimum.height()
    assert not window.isVisible()


@pytest.mark.parametrize("invalid_geometry", [QByteArray(b"not-geometry"), "not-geometry"])
def test_malformed_saved_geometry_uses_the_fitted_default(startup, invalid_geometry):
    startup.settings.setValue("geometry", invalid_geometry)
    window = startup.create()
    width = window.width()
    font = window.font()
    entry._prepare_window(window)
    assert window.height() + 60 <= startup.area.height()
    assert window.height() >= window.window_size_guard.preferredMinimum.height()
    assert window.width() == width and window.font() == font
    assert window.preview.minimumHeight() >= 230
    assert startup.settings.value("geometry") == invalid_geometry
    assert not window.isVisible()
