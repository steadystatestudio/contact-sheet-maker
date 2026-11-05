"""Native Qt/X11 floors preserve complete fitting dimensions and useful workspace."""
import importlib
import time
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QRect,
    QSettings,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

PACKAGE = next((Path(__file__).parents[1] / "src").glob("*/window_size.py")).parent.name
GUARD = importlib.import_module(PACKAGE + ".window_size")

@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def case(app, monkeypatch, tmp_path):
    appearance = importlib.import_module(PACKAGE + ".appearance")
    fonts = importlib.import_module(PACKAGE + ".system_fonts")
    previous_font, previous_style = app.font(), app.styleSheet()
    previous_settings = getattr(app, "_studio_pilot_settings", None)
    previous_key = getattr(app, "_studio_appearance_theme_key", "theme")
    monkeypatch.setattr(fonts.QStandardPaths, "writableLocation", lambda *_: str(tmp_path / "diagnostics"))
    monkeypatch.setattr(app, "_studio_refresh_appearance", None, raising=False)
    for name, function in (("gtk", "_start_native"), ("portal", "_start_portal")):
        monkeypatch.setattr(appearance, function,
                            lambda instance, generation, provider=name: appearance._provider_finished(
                                instance, generation, provider, {"reason": "fixture-unavailable"}))
    settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.IniFormat)
    settings.setValue("appearance/font_mode", "custom")
    settings.setValue("appearance/font_family", previous_font.family())
    settings.setValue("appearance/font_size_pt", 12)
    # Plain geometry fixtures must not inherit a previous app text stylesheet.
    app.setStyleSheet("")
    appearance.configure_appearance(app, settings, refresh=True, theme_key=previous_key)
    assert app.font().pointSizeF() == 12
    class NativeQtArea(QObject):
        changed = Signal()
        enabled = False
        last_details: ClassVar[dict[str, str]] = {"source": "captured-qt", "reason": "native-qt-platform"}

        def refresh(self):
            pass

    provider = NativeQtArea()
    area = [QRect(0, 0, 1080, 672)]
    monkeypatch.setattr(GUARD, "workarea_provider", lambda _: provider)
    monkeypatch.setattr(GUARD, "available_geometry", lambda *_: area[0])
    monkeypatch.setattr(GUARD.QGuiApplication, "platformName", lambda: "xcb")
    window = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    body = QWidget()
    body_layout = QVBoxLayout(body)
    content = QLabel("Configuration and working preview")
    content.setMinimumSize(700, 900)
    body_layout.addWidget(content)
    scroll.setWidget(body)
    layout.addWidget(scroll, 1)
    status = QLabel("Persistent actions and status")
    status.setMinimumSize(700, 40)
    layout.addWidget(status)
    window.setCentralWidget(central)
    window.resize(960, 1200)
    guard = GUARD.WindowSizeGuard(window, (800, 900), scroll)
    automatic_maximize = []
    monkeypatch.setattr(window, "showMaximized", lambda: automatic_maximize.append(True))

    def wait(predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(.005)
        assert predicate()

    try:
        yield SimpleNamespace(app=app, window=window, guard=guard, provider=provider, area=area,
                              layout=layout, scroll=scroll, status=status, wait=wait,
                              automatic_maximize=automatic_maximize)
    finally:
        guard.timer.stop()
        guard._geometry_diagnostics_timer.stop()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        appearance.configure_appearance(app, previous_settings, refresh=True, theme_key=previous_key)
        if app.styleSheet() != previous_style:
            app.setStyleSheet(previous_style)
        app.setFont(previous_font)
        app.processEvents()


def test_x11_height_overflow_releases_only_height_before_map_and_restores_room(case):
    c = case
    font = c.window.font()
    c.guard.update()
    wanted = c.guard.preferredMinimum
    assert not c.window.isVisible() and wanted.height() > c.area[0].height()
    assert c.window.minimumHeight() < c.area[0].height()
    assert c.window.minimumWidth() == wanted.width()
    assert c.window.minimumWidth() >= c.status.minimumWidth()
    assert not c.guard.constrained_native_maximum and c.automatic_maximize == []
    assert c.guard.geometry_constraint["source"] == "captured-qt"
    assert c.guard.geometry_constraint["reason"] == "native-qt-platform"
    c.window.show()
    c.window.resize(1, 1)
    c.wait(lambda: not c.guard.timer.isActive())
    assert c.window.rect().contains(c.status.geometry())
    assert c.scroll.height() >= 120
    assert c.scroll.viewport().height() >= 2 * c.window.fontMetrics().height()
    assert c.scroll.verticalScrollBar().maximum() > 0
    assert c.scroll.horizontalScrollBar().maximum() == 0
    assert c.window.font() == font and not c.window.isMaximized() and c.automatic_maximize == []
    c.area[0] = QRect(0, 0, 1600, 1600)
    c.provider.changed.emit()
    c.wait(lambda: c.window.minimumSize() == c.guard.preferredMinimum and not c.guard.timer.isActive())
    assert c.window.font() == font


def test_x11_width_only_overflow_keeps_full_height(case):
    c = case
    c.area[0] = QRect(0, 0, 760, 1600)
    c.guard.update()
    assert c.guard.preferredMinimum.width() > c.area[0].width()
    assert c.window.minimumWidth() < c.area[0].width()
    assert c.window.minimumHeight() == c.guard.preferredMinimum.height()
    assert c.window.minimumWidth() >= c.layout.minimumSize().width()
    assert not c.guard.constrained_native_maximum and c.automatic_maximize == []


def test_x11_that_fits_keeps_the_complete_floor(case):
    c = case
    c.area[0] = QRect(0, 0, 1600, 1600)
    c.guard.update()
    assert c.window.minimumSize() == c.guard.preferredMinimum
    assert c.automatic_maximize == []


def test_explicit_geometry_bypasses_native_x11_relaxation(case):
    c = case
    c.guard.update(c.area[0])
    assert c.window.minimumSize() == c.guard.preferredMinimum.boundedTo(c.area[0].size())
    assert not c.guard.constrained_native_maximum and c.automatic_maximize == []


@pytest.mark.parametrize("platform", ["offscreen", "windows", "wayland"])
def test_non_x11_disabled_provider_keeps_existing_normal_floor(case, monkeypatch, platform):
    c = case
    monkeypatch.setattr(GUARD.QGuiApplication, "platformName", lambda: platform)
    c.guard.update()
    assert c.window.minimumSize() == c.guard.preferredMinimum.boundedTo(c.area[0].size())
    assert not c.guard.constrained_native_maximum and c.automatic_maximize == []


def test_enabled_mapper_is_outside_native_x11_branch(case):
    c = case
    c.provider.enabled = True
    # Isolate the native-X11 branch after the independent first-map negotiation.
    c.window.showNormal()

    def normal_frame_ready():
        handle = GUARD.observe_window_screen(c.window, c.guard._screen_changed, owner=c.guard)
        return (handle is not None and handle.isExposed() and not c.window.isMaximized()
                and not handle.windowState() & (Qt.WindowMaximized | Qt.WindowMinimized | Qt.WindowFullScreen))

    c.wait(normal_frame_ready)
    c.guard.update()
    frame = c.window.frameGeometry()
    capacity = QSize(max(1, c.area[0].width() - max(0, frame.width() - c.window.width())),
                     max(1, c.area[0].height() - max(0, frame.height() - c.window.height())))
    assert c.window.minimumSize() == c.guard.preferredMinimum.boundedTo(capacity)
    assert not c.guard.constrained_native_maximum and c.automatic_maximize == []
