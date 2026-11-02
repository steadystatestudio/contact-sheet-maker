from __future__ import annotations
import os
from pathlib import Path
import sys
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from . import __version__
from .gui import MainWindow


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
    app = QApplication(sys.argv)
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
        window = MainWindow(settings)
        window.show()
        return app.exec()
    if "--smoke-test" in sys.argv:
        from .smoke import run
        index = sys.argv.index("--smoke-test")
        if len(sys.argv) <= index + 1:
            raise SystemExit("--smoke-test requires a new output folder")
        return run(app, Path(sys.argv[index + 1]))
    window = MainWindow()
    window.show()
    return app.exec()
