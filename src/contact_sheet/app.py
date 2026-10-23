from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from . import __version__
from .gui import MainWindow

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Contact Sheet Maker")
    app.setOrganizationName("Steady State Studio")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    if "--smoke-test" in sys.argv:
        from pathlib import Path
        from .smoke import run
        index = sys.argv.index("--smoke-test")
        if len(sys.argv) <= index + 1:
            raise SystemExit("--smoke-test requires a new output folder")
        return run(app, Path(sys.argv[index + 1]))
    window = MainWindow()
    window.show()
    return app.exec()
