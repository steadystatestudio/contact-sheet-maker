"""Native bundle self-test: exercise the real GUI worker/export pipeline."""
from __future__ import annotations
import hashlib
import json
import time
import sys
from pathlib import Path
from PIL import Image, ImageCms
from PySide6.QtCore import QSettings
from .gui import MainWindow
from .themes import apply_theme
from .appearance import prepare_initial_appearance


def run(app, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=False)
    inputs = destination / "inputs"; inputs.mkdir(exist_ok=True)
    outputs = destination / "outputs"; outputs.mkdir(exist_ok=True)
    paths = []
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    for index in range(13):
        path = inputs / f"café-{index + 1:02d}.png"
        with Image.new("RGB", (160, 100) if index % 2 else (100, 160), (40 + index * 12, 110, 160)) as source:
            # Exercise the frozen ImageCms/LittleCMS path, not just an import.
            source.save(path, icc_profile=srgb)
        paths.append(path)
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    settings = QSettings(str(destination / "smoke-settings.ini"), QSettings.IniFormat)
    prepare_initial_appearance(app, settings, theme_key="theme")
    window = MainWindow(settings)
    from .app import _prepare_window
    _prepare_window(window)
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
    from .appearance_qa import capture_appearance
    capture_appearance(app, window, destination)
    for theme, size, name in (("light", (1, 1), "ui-compact"),
                              ("dark", (1280, 680), "ui-dark")):
        apply_theme(app, theme)
        window.resize(*size)
        app.processEvents(); app.processEvents()
        drain(lambda: window.output_controls.height() >= window.output_controls.minimumSizeHint().height())
        assert window.width() >= window.minimumWidth() and window.height() >= window.minimumHeight()
        assert window.export_button.isVisible() and window.status.isVisible()
        assert window.output_controls.height() >= window.output_controls.minimumSizeHint().height()
        assert window.grab().save(str(destination / f"{name}.png"))
        if size[1] == 480:
            window.work_scroll.ensureWidgetVisible(window.title_input)
            app.processEvents()
            assert window.grab().save(str(destination / "ui-compact-layout.png"))
            window.work_scroll.verticalScrollBar().setValue(0)
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
    # Exercise the data-dependent Letter PDF boundary in the frozen application,
    # not only in the source suite. Identical artwork keeps the oracle simple.
    strict_inputs = destination / "strict-inputs"
    strict_inputs.mkdir()
    strict_paths = []
    for index in range(13):
        path = strict_inputs / f"gold-{index + 1:02d}.png"
        with Image.new("RGB", (300, 180), (230, 180, 30)) as source:
            source.save(path)
        strict_paths.append(path)
    strict_before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in strict_paths}
    window.clear_photos()
    drain(lambda: window.preview_task is None)
    window.page_size.setCurrentText("Letter")
    window.rows.setValue(2); window.columns.setValue(3)
    window.margin.setValue(15); window.gap.setValue(6)
    window.captions.setChecked(False)
    window.title_input.clear()
    window.dpi_combo.setCurrentText("150 dpi")
    window.add_paths(strict_paths)
    drain(lambda: not window.busy and not window.preview_pending and window.preview_task is None)
    assert len(window.model.photos) == 13 and window.export_button.isEnabled()
    window.start_export(outputs, "strict-letter", "PDF")
    drain(lambda: not window.busy)
    assert strict_before == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in strict_paths}
    window.close(); app.processEvents()
    result = {"ok": True, "photos": 13, "pages": 2, "originals_unchanged": True, "input_hashes_before": before, "pdf": "outputs/smoke.pdf", "jpeg_files": [p.name for p in pages], "strict_pdf": "outputs/strict-letter.pdf", "strict_pages": 3, "strict_input_hashes_before": strict_before}
    (destination / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if sys.stdout is not None:
        print(json.dumps(result))
    return 0
