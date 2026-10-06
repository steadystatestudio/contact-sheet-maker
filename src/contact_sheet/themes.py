"""Studio theme adapted from file-renamer, MIT © 2026 Steady State Studio.
See THIRD_PARTY_NOTICES.md for exact source provenance.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication, preference: str = "system") -> None:
    dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    if preference == "system" and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                dark = winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        except OSError:
            pass
    if preference != "system":
        dark = preference == "dark"
    background, panel, field = ("#2c2c2c", "#252525", "#303030") if dark else ("#f3f3f3", "#ffffff", "#fafafa")
    text, muted, border = ("#f1f1f1", "#b5b5b5", "#555555") if dark else ("#222222", "#626262", "#cccccc")
    selection = "#508fdb"
    app.setProperty("dark", dark)
    preferred = ("Segoe UI", "Noto Sans", "DejaVu Sans", "Liberation Sans")
    available = QFontDatabase.families()
    if not any(name in available for name in preferred):
        # Offscreen Qt and some bundled Linux setups do not enumerate system fonts.
        candidates = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"] if os.name == "nt" else [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        ]
        for path in candidates:
            if path.exists() and QFontDatabase.addApplicationFont(str(path)) >= 0:
                break
        available = QFontDatabase.families()
    font = QFont(next((name for name in preferred if name in available), app.font().family()))
    font.setPointSizeF(10.5)
    app.setFont(font)
    palette = QPalette()
    from PySide6.QtGui import QColor
    for role, color in [(QPalette.Window, background), (QPalette.WindowText, text),
                        (QPalette.Base, field), (QPalette.Text, text),
                        (QPalette.AlternateBase, "#4a4a4a" if dark else "#e2e2e2"),
                        (QPalette.Mid, border), (QPalette.Button, panel),
                        (QPalette.ButtonText, text), (QPalette.Highlight, selection),
                        (QPalette.HighlightedText, "#ffffff"), (QPalette.ToolTipBase, panel),
                        (QPalette.ToolTipText, text)]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    arrow_dir = Path(__file__).parent / "assets"
    up_arrow = (arrow_dir / ("up-dark.svg" if dark else "up-light.svg")).as_posix()
    down_arrow = (arrow_dir / ("down-dark.svg" if dark else "down-light.svg")).as_posix()
    app.setStyleSheet(f"""
        QWidget {{ color: {text}; }}
        QMainWindow, QDialog {{ background: {background}; }}
        QPushButton {{ background: transparent; border: 1px solid {border}; border-radius: 6px;
                       padding: 9px 13px; min-height: 19px; }}
        QPushButton:hover {{ background: {field}; border-color: {selection}; }}
        QPushButton:pressed, QPushButton:checked {{ background: {selection}; color: white; }}
        QPushButton:disabled {{ color: {muted}; border-color: {border}; }}
        QPushButton:focus, QComboBox:focus, QLineEdit:focus {{ border: 2px solid {selection}; }}
        QPushButton#primary {{ background: {selection}; color: white; font-weight: 600;
                               border: 1px solid {selection}; }}
        QPushButton#primary:disabled {{ background: {border}; color: {muted}; }}
        QPushButton#primary[filesLoaded="true"]:disabled {{ background: {selection}; color: #d5e3f5; }}
        QFrame#panel {{ background: {panel}; border: 1px solid {border}; border-radius: 10px; }}
        QTableView, QListWidget {{ background: {panel}; border: 1px solid {border}; border-radius: 8px;
                                 selection-background-color: {selection}; gridline-color: {border}; }}
        QTableView::item, QListWidget::item {{ padding: 7px; }}
        QTableView#fileTable::item {{ padding: 3px 8px; }}
        QHeaderView::section {{ background: {field}; color: {muted}; padding: 9px 8px;
                               border: none; border-bottom: 1px solid {border}; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {field}; border: 1px solid {border};
                                       border-radius: 6px; padding: 7px; min-height: 21px; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox::down-arrow {{ image: url("{down_arrow}"); width: 10px; height: 6px; }}
        QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none; }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none; }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{up_arrow}"); width: 10px; height: 6px; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{down_arrow}"); width: 10px; height: 6px; }}
        QComboBox QAbstractItemView {{ background: {panel}; selection-background-color: {selection}; }}

        QComboBox QAbstractItemView::item, QMenu::item {{ min-height: 26px; padding: 6px 10px; }}
        QWidget#actionRow QPushButton {{ padding: 7px 9px; }}
        QDialog#ruleDialog QPushButton {{ padding: 4px 9px; min-height: 19px; }}
        QDialog#ruleDialog QLineEdit, QDialog#ruleDialog QSpinBox {{ padding: 3px; min-height: 21px; }}
        QDialog#ruleDialog QRadioButton, QDialog#ruleDialog QCheckBox {{ spacing: 6px; }}
        QDialog#ruleDialog QListWidget::item {{ padding: 2px 6px; }}
        QDialog#ruleDialog QLabel#sectionHeading {{ padding-top: 3px; }}
        QLabel#muted {{ color: {muted}; }}
        QLabel#heading {{ font-size: 15pt; font-weight: 600; }}
        QLabel#sectionHeading {{ font-weight: 600; padding-top: 8px; }}
        QProgressBar {{ border: none; border-radius: 6px; background: {panel};
                       text-align: center; min-height: 36px; padding: 10px 32px;
                       font-size: 11.6pt; font-weight: 600; }}
        QProgressBar::chunk {{ background: {selection}; border-radius: 4px; }}
        QToolTip {{ background: {panel}; color: {text}; border: 1px solid {border}; padding: 6px; }}
    """)

