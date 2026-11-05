from __future__ import annotations
import os
from pathlib import Path
import sys
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication
from . import __version__
from .gui import MainWindow
from .appearance import prepare_initial_appearance, prepare_window_for_show


def _prepare_window(window):
    def arrange():
        window._arrange_toolbar()
        window._arrange_output()
        window._fit_splitter_contents()
    prepare_window_for_show(window, arrange)
    # Fit the fresh default to the measured useful workspace before mapping.
    # Restored user geometry retains its existing monitor-fitting behavior.
    if not window._geometry_restored:
        guard = window.window_size_guard
        height = max(window.minimumHeight(), min(
            guard.preferredMinimum.height(), guard.geometry_constraint["client_capacity"][1]))
        if window.height() > height:
            window.resize(window.width(), height)
            prepare_window_for_show(window, arrange)


def _qa_settings(argument: str) -> QSettings:
    """Isolate interactive package checks without touching ordinary preferences."""
    directory = Path(argument).expanduser()
    if ".." in directory.parts:
        raise ValueError("The QA folder cannot contain parent-directory traversal")
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    for component in (directory, *directory.parents):
        if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
            raise ValueError("The QA folder cannot use symbolic links or junctions")
        # Also recognize redirected ancestors on Python versions before is_junction.
        if component.exists() and os.path.normcase(str(component.resolve())) != os.path.normcase(str(component.absolute())):
            raise ValueError("The QA folder cannot use redirected ancestors")
    directory.mkdir(exist_ok=False)  # Parent must already exist; never replace data.
    settings = QSettings(str(directory / "settings.ini"), QSettings.IniFormat)
    settings.setFallbacksEnabled(False)
    return settings


def main() -> int:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    app = QApplication(sys.argv)
    from .system_fonts import capture_system_appearance
    capture_system_appearance(app)
    app.setApplicationName("Contact Sheet Maker")
    app.setOrganizationName("Steady State Studio")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    if "--qa-ui" in sys.argv:
        index = sys.argv.index("--qa-ui")
        if (sys.argv.count("--qa-ui") != 1 or len(sys.argv) <= index + 1
                or sys.argv[index + 1].startswith("--") or "--smoke-test" in sys.argv):
            raise SystemExit("--qa-ui requires one fresh folder and cannot be combined with --smoke-test")
        try:
            settings = _qa_settings(sys.argv[index + 1])
        except (OSError, ValueError) as exc:
            raise SystemExit(f"Cannot start isolated QA: {exc}") from exc
        prepare_initial_appearance(app, settings, theme_key="theme")
        window = MainWindow(settings)
        _prepare_window(window)
        window.show()
        return app.exec()
    if "--smoke-test" in sys.argv:
        from .smoke import run
        index = sys.argv.index("--smoke-test")
        if len(sys.argv) <= index + 1:
            raise SystemExit("--smoke-test requires a new output folder")
        return run(app, Path(sys.argv[index + 1]))
    settings = QSettings("Steady State Studio", "Contact Sheet Maker")
    prepare_initial_appearance(app, settings, theme_key="theme")
    window = MainWindow(settings)
    _prepare_window(window)
    window.show()
    return app.exec()
