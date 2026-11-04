"""Regression coverage for system typography and readable compact controls."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from contact_sheet.gui import MainWindow
from contact_sheet.themes import apply_theme
from contact_sheet.system_fonts import desktop_font


def test_desktop_text_scaling_is_applied_once():
    native = QFont("Sans", 11)
    wayland = desktop_font(native, "Liberation Sans 14", 1.5, 96)
    x11 = desktop_font(native, "Liberation Sans 14", 1.5, 144)
    assert wayland.family() == x11.family() == "Liberation Sans"
    assert wayland.pointSizeF() * 96 == x11.pointSizeF() * 144
    assert wayland.pointSizeF() == 21


def test_large_system_font_survives_theme_and_compact_layout(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    old = app.font()
    old_style, old_palette = app.styleSheet(), app.palette()
    monkeypatch.setattr(app, "_studio_system_font_initialized", True, raising=False)
    font = QFont(old)
    font.setPointSizeF(18)
    from contact_sheet.appearance import configure_appearance
    previous_settings = getattr(app, "_studio_pilot_settings", None)
    settings = QSettings(str(tmp_path/"font.ini"), QSettings.IniFormat)
    settings.setValue("appearance/font_mode", "custom")
    settings.setValue("appearance/font_family", font.family())
    settings.setValue("appearance/font_size_pt", 18)
    configure_appearance(app, settings)
    window = None
    try:
        window = MainWindow(settings)
        window.resize(800, 650)
        window.show()
        for theme in ("light", "dark", "system"):
            apply_theme(app, theme)
            app.processEvents()
            window._arrange_toolbar()
            window._arrange_output()
            app.processEvents()
            assert app.font().family() == font.family()
            assert app.font().pointSizeF() == 18
            assert window.width() <= 800
            for widget in (window.add_files, window.add_folder, window.clear_button,
                           window.help_button, window.donate_button, window.settings_button,
                           window.export_button, window.status, window.table,
                           window.table.horizontalHeader()):
                assert widget.font().pointSizeF() >= 18
                bounds = QRect(widget.mapTo(window, QPoint()), widget.size())
                assert window.rect().contains(bounds), (widget, bounds)
                assert widget.height() >= widget.fontMetrics().height()
    finally:
        if window:
            window.close()
        configure_appearance(app, previous_settings)
        app.setFont(old)
        app.setPalette(old_palette)
        app.setStyleSheet(old_style)
