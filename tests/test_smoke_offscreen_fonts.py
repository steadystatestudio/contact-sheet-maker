"""Windows offscreen QA must use readable metrics, including its 18pt picker."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows offscreen font catalog needs explicit registration")
def test_installed_qa_font_resolves_actual_18pt_without_widening_screen():
    script = '''
import json
from PySide6.QtGui import QFont,QFontInfo
from PySide6.QtWidgets import QApplication
from contact_sheet.smoke import _register_offscreen_test_fonts
app=QApplication([])
before=app.primaryScreen().availableGeometry().getRect()
_register_offscreen_test_fonts(app)
actual=QFontInfo(QFont("Segoe UI",18))
print(json.dumps(dict(family=actual.family(),points=actual.pointSizeF(),pixels=actual.pixelSize(),
                     screen=app.primaryScreen().availableGeometry().getRect(),before=before)))
'''
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(root / "src"))
    result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env,
                            capture_output=True, text=True, check=True, timeout=10)
    observed = json.loads(result.stdout)
    assert observed["family"] and observed["points"] == 18 and observed["pixels"] == 24
    assert observed["screen"] == observed["before"] == [0, 0, 800, 800]
