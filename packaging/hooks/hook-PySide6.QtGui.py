"""Use PyInstaller's Qt discovery, without unrelated PDF/keyboard/TUIO plugins.

Filtering before binary dependency analysis avoids collecting PDFium, QML,
Virtual Keyboard and networking libraries for this local QWidget application.
Native input-method plugins remain available for ordinary text entry.
"""
from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
_excluded = ("qpdf.", "qtvirtualkeyboardplugin.", "qtuiotouchplugin.")
binaries = [entry for entry in binaries
            if not Path(entry[0]).name.lower().removeprefix("lib").startswith(_excluded)]
