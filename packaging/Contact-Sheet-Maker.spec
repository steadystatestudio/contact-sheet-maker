"""One-folder native package with OS-owned Linux libraries left on the host."""
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
sys.path.insert(0, str(root / "scripts"))
from linux_dependencies import omit_system_libraries

a = Analysis(
    [str(root / "scripts/launcher.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=collect_data_files("contact_sheet"),
    hiddenimports=[],
    hookspath=[str(root / "packaging/hooks")],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
              "PySide6.QtNetwork", "PySide6.QtPdf", "PySide6.QtQml", "PySide6.QtQuick",
              "readline", "tkinter", "pytest"],
    noarchive=False,
    optimize=0,
)
if sys.platform == "linux":
    omit_system_libraries(a, root / "build/LINUX-SYSTEM-DEPENDENCIES.json")

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Contact-Sheet-Maker",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=[str(root / "build/icon.png")] if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Contact-Sheet-Maker")
