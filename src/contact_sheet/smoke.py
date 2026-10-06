"""Native bundle self-test: exercise the real GUI worker/export pipeline."""
from __future__ import annotations
import hashlib
import json
import time
import sys
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QSettings
from .gui import MainWindow


def run(app, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=False)
    inputs = destination / "inputs"; inputs.mkdir(exist_ok=True)
    outputs = destination / "outputs"; outputs.mkdir(exist_ok=True)
    paths = []
    for index in range(13):
        path = inputs / f"café-{index + 1:02d}.png"
        Image.new("RGB", (160, 100) if index % 2 else (100, 160), (40 + index * 12, 110, 160)).save(path)
        paths.append(path)
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    window = MainWindow(QSettings(str(destination / "smoke-settings.ini"), QSettings.IniFormat))
    window.show()
    errors = []
    window._operation_failed = lambda exc: errors.append(str(exc))
    def drain(condition):
        deadline = time.monotonic() + 30
        while not condition():
            app.processEvents(); time.sleep(.005)
            if time.monotonic() > deadline:
                raise RuntimeError("Bundle GUI operation timed out")
        app.processEvents()
        if errors:
            raise RuntimeError("Bundle smoke operation failed: " + "; ".join(errors))
    window.add_paths(paths)
    drain(lambda: not window.busy and not window.preview_pending and window.preview_task is None)
    assert len(window.model.photos) == 13 and window.export_button.isEnabled()
    assert not window.preview.pixmap.isNull()
    assert window.grab().save(str(destination / "ui.png"))
    window.start_export(outputs, "smoke", "PDF", overwrite=True)
    drain(lambda: not window.busy)
    assert (outputs / "smoke.pdf").read_bytes().startswith(b"%PDF")
    window.start_export(outputs, "smoke", "JPEG", overwrite=True)
    drain(lambda: not window.busy)
    pages = sorted(outputs.glob("smoke-*.jpg"))
    assert len(pages) == 2
    for page in pages:
        with Image.open(page) as image:
            assert image.size == (1654, 2339)
    assert before == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    window.close(); app.processEvents()
    result = {"ok": True, "photos": 13, "pages": 2, "originals_unchanged": True, "input_hashes_before": before, "pdf": "outputs/smoke.pdf", "jpeg_files": [p.name for p in pages]}
    (destination / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if sys.stdout is not None:
        print(json.dumps(result))
    return 0
