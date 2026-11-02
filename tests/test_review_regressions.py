"""Independent regression coverage for races found in the safety review."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/contact-sheet-test-cache")
import threading
import time

from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
import pytest

from contact_sheet import core, gui


@pytest.fixture(scope="session")
def review_app():
    return QApplication.instance() or QApplication([])


def drain_until(app, condition, timeout=12):
    deadline = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("UI worker did not settle")
        time.sleep(.005)
    app.processEvents()


@pytest.fixture
def review_window(review_app, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.Ok)
    window = gui.MainWindow(QSettings(str(tmp_path / "review-settings.ini"), QSettings.IniFormat))
    window.show()
    review_app.processEvents()
    yield window
    window.debounce.stop()
    window.preview_pending = False
    if window.task:
        window.task.cancel.set()
    if window.preview_task:
        window.preview_task.cancel.set()
    drain_until(review_app, lambda: window.task is None and window.preview_task is None)
    window.close()
    review_app.processEvents()


def prepare_pending_preview(window, tmp_path):
    path = tmp_path / "café 你好.png"
    Image.new("RGB", (30, 20), "navy").save(path)
    window.model.reset([core.inspect_photo(path)])
    window._schedule_preview()


def settled(window):
    return (not window.busy and window.preview_task is None
            and not window.preview_pending and not window.debounce.isActive())


def test_export_result_survives_automatic_preview(review_window, review_app, tmp_path):
    prepare_pending_preview(review_window, tmp_path)
    review_window.start_export(tmp_path, "review-output", "JPEG")
    drain_until(review_app, lambda: settled(review_window))
    assert (tmp_path / "review-output-001.jpg").exists()
    assert review_window.status.text().startswith("Saved 1 file")
    assert not review_window.preview.pixmap.isNull()


@pytest.mark.parametrize("cancelled", [False, True])
def test_operation_error_survives_automatic_preview(review_window, review_app, tmp_path, monkeypatch, cancelled):
    prepare_pending_preview(review_window, tmp_path)
    def fail(*args, **kwargs):
        if cancelled:
            raise core.ExportCancelled()
        raise ValueError("Deliberate export failure")
    monkeypatch.setattr(gui, "export_sheets", fail)
    review_window.start_export(tmp_path, "will-not-exist", "JPEG")
    drain_until(review_app, lambda: settled(review_window))
    assert not (tmp_path / "will-not-exist-001.jpg").exists()
    assert ("Cancelled" if cancelled else "Deliberate export failure") in review_window.status.text()
    assert not review_window.preview.pixmap.isNull()


def test_close_after_work_finishes_inside_confirmation(review_window, review_app, monkeypatch):
    release = threading.Event()
    def work(cancel, progress):
        assert release.wait(5)
        return None
    review_window._start_operation(work, lambda result: None, "Working")
    def finish_then_confirm(*args, **kwargs):
        # QMessageBox.exec has a nested event loop in the real app.
        release.set()
        drain_until(review_app, lambda: review_window.task is None)
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, "question", finish_then_confirm)
    review_window.close()
    drain_until(review_app, lambda: not review_window.isVisible())
    assert review_window.task is None
    assert review_window.preview_task is None


def test_stale_preview_cannot_reappear_after_clear(review_window, review_app, tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def delayed_page(*args, **kwargs):
        started.set()
        assert release.wait(5)
        # Deliberately ignore cancellation to exercise stale-result protection.
        return Image.new("RGB", (25, 30), "red")
    monkeypatch.setattr(gui, "render_page", delayed_page)
    prepare_pending_preview(review_window, tmp_path)
    review_window._launch_preview()
    drain_until(review_app, started.is_set)
    review_window.clear_photos()
    release.set()
    drain_until(review_app, lambda: review_window.preview_task is None)
    assert review_window.preview.pixmap.isNull()
    assert review_window.model.rowCount() == 0
    assert not review_window.export_button.isEnabled()


def test_unicode_numeric_prefix_folder_sort(tmp_path):
    names = ["①1.jpg", "²1.jpg", "photo2.jpg", "photo10.jpg"]
    for name in names:
        Image.new("RGB", (5, 5), "white").save(tmp_path / name)
    found = core.collect_paths([tmp_path])
    assert {path.name for path in found} == set(names)
    assert [path.name for path in found if path.name.startswith("photo")] == ["photo2.jpg", "photo10.jpg"]


def test_cancel_reports_new_output_changed_by_another_writer(tmp_path, monkeypatch):
    stage = tmp_path / "stage"
    stage.mkdir()
    staged = [stage / "one.jpg", stage / "two.jpg"]
    outputs = [tmp_path / "one.jpg", tmp_path / "two.jpg"]
    for path in staged:
        path.write_bytes(b"new export")
    original_install = core._install_exclusive
    def interfere(source, target, cancel=None):
        if target == outputs[1]:
            outputs[0].write_bytes(b"modified by another writer")
            raise core.ExportCancelled("cancelled")
        return original_install(source, target, cancel)
    monkeypatch.setattr(core, "_install_exclusive", interfere)
    with pytest.raises(RuntimeError) as error:
        core._commit_outputs(staged, outputs, [None, None], [], None)
    assert outputs[0].read_bytes() == b"modified by another writer"
    assert outputs[0].name in str(error.value)


def test_copy_cleanup_failure_identifies_remaining_output(tmp_path, monkeypatch):
    import errno
    source, target = tmp_path / "staged", tmp_path / "partial-output"
    source.write_bytes(b"new export")
    monkeypatch.setattr(core, "_WINDOWS", False)
    def unsupported_link(*args, **kwargs):
        raise OSError(errno.EOPNOTSUPP, "hardlinks unavailable")
    def failed_sync(*args, **kwargs):
        raise OSError("sync failed")
    real_unlink = type(target).unlink
    def locked_target(path, *args, **kwargs):
        if path == target:
            raise PermissionError("another app locked the output")
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(core.os, "link", unsupported_link)
    monkeypatch.setattr(core.os, "fsync", failed_sync)
    monkeypatch.setattr(type(target), "unlink", locked_target)
    with pytest.raises(RuntimeError) as error:
        core._install_exclusive(source, target)
    assert target.exists()
    assert target.name in str(error.value)
