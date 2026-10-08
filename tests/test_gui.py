import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/contact-sheet-test-cache")
import time
from pathlib import Path
from PySide6.QtCore import QSettings, QItemSelectionModel, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from PySide6.QtGui import QDesktopServices
from PIL import Image
import pytest
from contact_sheet.gui import MainWindow, SettingsDialog, DONATE_URL
from contact_sheet.core import inspect_photo, ExportCancelled

@pytest.fixture(scope="session")
def app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    return app


def wait(app, condition, timeout=12):
    until = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() > until:
            raise AssertionError("Timed out waiting for the UI worker")
        time.sleep(.005)
    app.processEvents()

@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)
    w = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    w.show(); app.processEvents()
    yield w
    if w.task:
        w.task.cancel.set()
    if w.preview_task:
        w.preview_task.cancel.set()
    wait(app, lambda: w.task is None and w.preview_task is None)
    w.close(); app.processEvents()


def sample_paths(tmp_path, count=3):
    result=[]
    for i in range(count):
        path=tmp_path/f"café-{i:02d}.png"
        Image.new("RGB",(180 + i*10,120),(30+i*15,110,150)).save(path)
        result.append(path)
    return result


def load(window, app, paths):
    window.add_paths(paths)
    wait(app, lambda: not window.busy)
    wait(app, lambda: not window.preview_pending and window.preview_task is None)


def select(window, rows):
    window.table.clearSelection()
    for row in rows:
        window.table.selectionModel().select(window.model.index(row,0), QItemSelectionModel.Select|QItemSelectionModel.Rows)


def test_import_preview_dedupe_reorder_remove_clear(window,app,tmp_path):
    paths=sample_paths(tmp_path,4)
    load(window,app,paths)
    assert len(window.model.photos)==4
    assert not window.preview.pixmap.isNull()
    assert window.export_button.isEnabled()
    load(window,app,paths)
    assert len(window.model.photos)==4
    select(window,[1,2]); window.move_selected(-1)
    assert [p.path.name for p in window.model.photos]==[paths[i].name for i in [1,2,0,3]]
    assert window.selected_rows()==[0,1]
    window.remove_selected()
    assert len(window.model.photos)==2
    window.clear_photos(); window.clear_photos()
    wait(app, lambda: window.preview_task is None)
    assert not window.export_button.isEnabled()
    assert window.page_label.text()=="Page 0 of 0"
    assert all(p.exists() for p in paths)


def test_pagination_and_rapid_options(window,app,tmp_path):
    load(window,app,sample_paths(tmp_path,14))
    assert window.page_label.text()=="Page 1 of 2"
    window.change_page(1)
    assert window.page_label.text()=="Page 2 of 2"
    for i in range(20):
        window.rows.setValue(1+i%6)
        window.orientation.setCurrentIndex(i%2)
    window.rows.setValue(2); window.columns.setValue(2)
    wait(app,lambda: window.preview_task is None and not window.preview_pending)
    assert window.page_label.text()=="Page 1 of 4"
    assert not window.preview.pixmap.isNull()
    window.rows.setValue(12); window.gap.setValue(30)
    assert not window.export_button.isEnabled()
    assert "layout does not fit" in window.preview.message
    window._apply_preset(0)
    wait(app,lambda: window.preview_task is None and not window.preview_pending)
    assert window.export_button.isEnabled()


def test_export_repeated_success_and_conflict(window,app,tmp_path):
    load(window,app,sample_paths(tmp_path,3))
    dest=tmp_path/"out"; dest.mkdir()
    window.start_export(dest,"contact","PDF")
    window.start_export(dest,"ignored","JPEG")
    wait(app,lambda: not window.busy)
    assert (dest/"contact.pdf").read_bytes().startswith(b"%PDF")
    assert not (dest/"ignored-001.jpg").exists()
    assert window.open_folder_button.isVisible()
    before=(dest/"contact.pdf").read_bytes()
    window.start_export(dest,"contact","PDF")
    wait(app,lambda: not window.busy)
    assert (dest/"contact.pdf").read_bytes()==before
    window.start_export(dest,"contact","JPEG")
    wait(app,lambda: not window.busy)
    assert (dest/"contact-001.jpg").exists()
    assert window.export_button.isEnabled()


def test_cancel_operation_does_not_commit(window,app,tmp_path,monkeypatch):
    load(window,app,sample_paths(tmp_path))
    def slow(photos,settings,destination,**kwargs):
        cancel=kwargs['cancel']
        while not cancel.is_set():
            time.sleep(.005)
        raise ExportCancelled()
    monkeypatch.setattr("contact_sheet.gui.export_sheets",slow)
    window.start_export(tmp_path,"cancelled","PDF")
    assert not window.add_files.isEnabled()
    window.cancel_operation(); window.cancel_operation()
    wait(app,lambda: not window.busy)
    assert not (tmp_path/"cancelled.pdf").exists()
    assert window.add_files.isEnabled()
    assert "Cancelled" in window.status.text()


def test_settings_cancel_and_apply(window,app,monkeypatch):
    def reject(dialog):
        dialog.theme.setCurrentText("Dark")
        return QDialog.Rejected
    monkeypatch.setattr(SettingsDialog,"exec",reject)
    window._settings_dialog()
    assert window.settings.value("theme","system")=="system"
    monkeypatch.setattr(SettingsDialog,"exec",lambda d:(d.theme.setCurrentText("Dark") or QDialog.Accepted))
    window._settings_dialog()
    assert window.settings.value("theme")=="dark"
    assert app.property("dark")
    window.rows.setValue(5); window.title_input.setText("My sheets")
    saved=MainWindow(window.settings)
    assert saved.rows.value()==5 and saved.title_input.text()=="My sheets"
    saved.close()


def test_donate_only_explicit_click(window,monkeypatch):
    urls=[]
    monkeypatch.setattr(QDesktopServices,"openUrl",lambda url:urls.append(url.toString()) or True)
    assert urls==[]
    window.donate_button.click()
    assert urls==[DONATE_URL]


def test_busy_close_no_then_yes(window,app,tmp_path,monkeypatch):
    load(window,app,sample_paths(tmp_path))
    def slow(cancel,progress):
        while not cancel.is_set():
            time.sleep(.005)
        raise ExportCancelled()
    window._start_operation(slow,lambda _:None,"Test")
    monkeypatch.setattr(QMessageBox,"question",lambda *a,**kw: QMessageBox.No)
    window.close(); assert window.isVisible() and not window.closing
    monkeypatch.setattr(QMessageBox,"question",lambda *a,**kw: QMessageBox.Yes)
    window.close()
    wait(app,lambda: not window.isVisible())
    assert window.task is None and window.preview_task is None


def test_corrupt_settings_do_not_block_start(app,tmp_path):
    settings=QSettings(str(tmp_path/"corrupt.ini"),QSettings.IniFormat)
    settings.setValue("layout",'{not json')
    w=MainWindow(settings)
    assert w.rows.value()==4
    w.close()


def test_small_window_controls_visible(window,app):
    window.resize(890,700); app.processEvents()
    assert window.export_button.geometry().right()<=window.output_controls.width()
    assert window.controls.height()>100
    assert window.splitter.height()>=230


def test_output_replace_requires_explicit_choice(window,app,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    load(window,app,sample_paths(tmp_path))
    (tmp_path/'contact-sheet.pdf').write_bytes(b'original')
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**kw:str(tmp_path))
    calls=[]
    monkeypatch.setattr(window,'start_export',lambda *args:calls.append(args))
    monkeypatch.setattr(QMessageBox,'exec',lambda self: QMessageBox.No)
    window._choose_export()
    assert calls==[]
    assert (tmp_path/'contact-sheet.pdf').read_bytes()==b'original'
    monkeypatch.setattr(QMessageBox,'exec',lambda self: QMessageBox.Yes)
    window._choose_export()
    assert len(calls)==1 and calls[0][-1] is True


def test_browse_cancel_is_noop(window,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog,'getOpenFileNames',lambda *a,**kw:([],''))
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**kw:'')
    window._browse_files(); window._browse_folder(); window._choose_export()
    assert window.model.photos==[] and not window.busy


def test_preview_gates_export(window,app,tmp_path):
    load(window,app,sample_paths(tmp_path))
    assert window.export_button.isEnabled()
    window.rows.setValue(5)
    assert not window.export_button.isEnabled()
    assert 'preview' in window.export_button.toolTip()
    wait(app,lambda:window.preview_task is None and not window.preview_pending)
    assert window.export_button.isEnabled()


def test_zoom_is_dismissible_and_preserves_page(window,app,tmp_path):
    load(window,app,sample_paths(tmp_path,14))
    before=window.page_index
    def close_dialog():
        dialog=app.activeModalWidget()
        assert dialog and '100%' in dialog.windowTitle()
        dialog.reject()
    QTimer.singleShot(20,close_dialog)
    window._zoom_preview()
    assert window.page_index==before and window.export_button.isEnabled()


def test_import_result_survives_preview_and_explains_duplicates(window, app, tmp_path):
    paths = sample_paths(tmp_path, 3)
    load(window, app, paths)
    assert window.status.text() == "Added 3 photos."
    select(window, [1])
    window.table.selectionModel().setCurrentIndex(window.model.index(1, 0), QItemSelectionModel.NoUpdate)
    preview_key = window.preview.pixmap.cacheKey()
    load(window, app, paths)
    assert window.status.text() == "No photos added. 3 already in the list."
    assert window.selected_rows() == [1]
    assert window.table.currentIndex().row() == 1
    assert window.preview.pixmap.cacheKey() == preview_key
    assert window.export_button.isEnabled()
    extra = tmp_path / "new.png"
    Image.new("RGB", (40, 30), "green").save(extra)
    load(window, app, [paths[0], extra])
    assert window.status.text() == "Added 1 photo. 1 already in the list."
    assert len(window.model.photos) == 4
    window.rows.setValue(5)
    wait(app, lambda: not window.preview_pending and window.preview_task is None)
    assert "Originals stay untouched" in window.status.text()


@pytest.mark.parametrize("with_existing", [False, True])
def test_empty_import_explains_supported_files(window, app, tmp_path, with_existing):
    if with_existing:
        load(window, app, sample_paths(tmp_path, 1))
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "notes.txt").write_text("not a photo")
    load(window, app, [empty])
    assert window.status.text() == "No photos added. No JPEG or PNG photos found in this selection."
    assert len(window.model.photos) == int(with_existing)
    assert window.export_button.isEnabled() == with_existing


@pytest.mark.parametrize("valid_count", [0, 1])
def test_failed_import_has_truthful_counts_and_details(window, app, tmp_path, monkeypatch, valid_count):
    paths = sample_paths(tmp_path, valid_count)
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    boxes = []
    def dismiss(box):
        boxes.append((box.windowTitle(), box.text(), box.detailedText()))
        return QMessageBox.Ok
    monkeypatch.setattr(QMessageBox, "exec", dismiss)
    load(window, app, paths + [broken])
    assert len(boxes) == 1
    assert "1 could not be loaded." in window.status.text()
    assert "The rest are ready" not in boxes[0][1]
    assert "broken.png" in boxes[0][2]
    assert window.export_button.isEnabled() == bool(valid_count)
    assert ("Added 1 photo." if valid_count else "No photos added.") in boxes[0][1]
    assert boxes[0][0] == ("Some photos could not be added" if valid_count else "Photos could not be added")


def test_cancel_import_preserves_list_and_keeps_cancelling_status(window, app, tmp_path, monkeypatch):
    import threading
    load(window, app, sample_paths(tmp_path, 1))
    before = list(window.model.photos)
    started, release = threading.Event(), threading.Event()
    def slow_collect(paths, cancel):
        started.set()
        assert release.wait(5)
        raise ExportCancelled()
    monkeypatch.setattr("contact_sheet.gui.collect_paths", slow_collect)
    window.add_paths([tmp_path])
    wait(app, started.is_set)
    try:
        window.cancel_operation()
        window._operation_progress(1, 2)
        assert window.status.text() == "Cancelling safely…"
        assert not window.cancel_button.isEnabled()
    finally:
        release.set()
    wait(app, lambda: not window.busy)
    assert window.model.photos == before
    assert window.status.text() == "Import cancelled. The photo list is unchanged."
    assert window.status.maximum() > 0
    assert window.export_button.isEnabled()


def test_remove_keeps_next_row_and_repeated_delete_respects_text_focus(window, app, tmp_path):
    from PySide6.QtTest import QTest
    paths = sample_paths(tmp_path, 4)
    load(window, app, paths)
    window.activateWindow()
    select(window, [1, 2])
    window.remove_button.click()
    assert [p.path for p in window.model.photos] == [paths[0], paths[3]]
    assert window.selected_rows() == [1]
    assert window.model.photos[window.table.currentIndex().row()].path == paths[3]
    assert window.table.currentIndex().row() == 1
    assert window.table.hasFocus()
    QTest.keyClick(window.table, Qt.Key_Delete)
    assert [p.path for p in window.model.photos] == [paths[0]]
    assert window.selected_rows() == [0]
    window.title_input.setText("A title")
    window.title_input.setFocus()
    window.title_input.selectAll()
    QTest.keyClick(window.title_input, Qt.Key_Delete)
    assert window.title_input.text() == ""
    assert len(window.model.photos) == 1
    window.table.setFocus()
    QTest.keyClick(window.table, Qt.Key_Delete)
    assert window.model.photos == []
    assert not window.table.currentIndex().isValid()
    QTest.keyClick(window.table, Qt.Key_Delete)
    assert window.model.photos == []


def test_reorder_preserves_keyboard_anchor_for_repeated_moves(window, app, tmp_path):
    from PySide6.QtTest import QTest
    paths = sample_paths(tmp_path, 5)
    load(window, app, paths)
    window.activateWindow()
    select(window, [2, 3])
    window.table.selectionModel().setCurrentIndex(window.model.index(3, 0), QItemSelectionModel.NoUpdate)
    window.up_button.click()
    assert window.selected_rows() == [1, 2]
    assert window.table.currentIndex().row() == 2
    assert window.table.hasFocus()
    QTest.keyClick(window.table, Qt.Key_Up, Qt.AltModifier)
    assert window.selected_rows() == [0, 1]
    assert window.table.currentIndex().row() == 1
    assert [p.path for p in window.model.photos][:2] == paths[2:4]
    QTest.keyClick(window.table, Qt.Key_Up, Qt.AltModifier)
    assert window.selected_rows() == [0, 1]
    QTest.keyClick(window.table, Qt.Key_Down, Qt.AltModifier)
    assert window.selected_rows() == [1, 2]
    assert window.table.currentIndex().row() == 2


def test_full_paths_and_preview_resolution_are_visible(window, app, tmp_path):
    long_name = tmp_path / ("A very long photo filename " * 5 + "café.png")
    Image.new("RGB", (40, 30), "blue").save(long_name)
    load(window, app, [long_name])
    assert window.model.data(window.model.index(0, 1), Qt.ToolTipRole) == str(long_name)
    assert "90 dpi preview" in window.preview_note.text()
    assert window.preview_note.wordWrap()


def test_duplicate_import_after_export_keeps_result_and_folder_access(window, app, tmp_path, monkeypatch):
    paths = sample_paths(tmp_path, 1)
    load(window, app, paths)
    window.start_export(tmp_path, "completed", "PDF")
    wait(app, lambda: not window.busy)
    saved = (tmp_path / "completed.pdf").read_bytes()
    assert window.status.text().startswith("Saved 1 file")
    # Add during a queued preview, as well as after a settled one.
    window.rows.setValue(5)
    load(window, app, paths)
    assert window.status.text() == "No photos added. 1 already in the list."
    assert window.open_folder_button.isVisible()
    assert "last exported folder" in window.open_folder_button.toolTip()
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    window.open_folder_button.click()
    assert opened == [str(tmp_path)]
    assert (tmp_path / "completed.pdf").read_bytes() == saved


def test_cancel_partial_import_after_export_discards_new_photos(window, app, tmp_path, monkeypatch):
    import threading
    load(window, app, sample_paths(tmp_path, 1))
    before = list(window.model.photos)
    window.start_export(tmp_path, "completed", "PDF")
    wait(app, lambda: not window.busy)
    saved = (tmp_path / "completed.pdf").read_bytes()
    more = tmp_path / "more"
    more.mkdir()
    paths = sample_paths(more, 2)
    inspected = []
    started, release = threading.Event(), threading.Event()
    real_inspect = inspect_photo
    def slow_inspect(path, cancel):
        if inspected:
            started.set()
            assert release.wait(5)
        result = real_inspect(path, cancel=cancel)
        inspected.append(path)
        return result
    monkeypatch.setattr("contact_sheet.gui.inspect_photo", slow_inspect)
    window.add_paths(paths)
    try:
        wait(app, started.is_set)
        assert inspected == [paths[0]]
        window.cancel_operation()
    finally:
        release.set()
    wait(app, lambda: not window.busy)
    assert window.model.photos == before
    assert window.status.text() == "Import cancelled. The photo list is unchanged."
    assert window.open_folder_button.isVisible()
    assert window.last_outputs == [tmp_path / "completed.pdf"]
    assert (tmp_path / "completed.pdf").read_bytes() == saved
    # A retry starts cleanly and can add both photos.
    monkeypatch.setattr("contact_sheet.gui.inspect_photo", real_inspect)
    load(window, app, paths)
    assert len(window.model.photos) == 3
    assert window.status.text() == "Added 2 photos."
