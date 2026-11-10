"""Replacing a JPEG set must not leave sheets from an earlier, longer export."""
from pathlib import Path

import pytest
from PIL import Image

from contact_sheet import core
from contact_sheet.core import SheetSettings, export_sheets, inspect_photo, stale_jpeg_sheets


def photos(folder: Path, count: int):
    folder.mkdir(exist_ok=True)
    loaded = []
    for index in range(count):
        path = folder / f"photo-{index:02d}.jpg"
        Image.new("RGB", (60, 40), (index * 20 % 255, 80, 120)).save(path, "JPEG")
        loaded.append(path)
    return [inspect_photo(path) for path in loaded]


def settings():
    return SheetSettings(rows=1, columns=2, dpi=150)


def names(folder: Path):
    return sorted(path.name for path in folder.iterdir())


def test_replace_removes_older_trailing_sheets_and_reports_them(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    export_sheets(photos(tmp_path / "many", 6), settings(), out, stem="set", format="JPEG")
    assert names(out) == ["set-001.jpg", "set-002.jpg", "set-003.jpg"]
    fewer = photos(tmp_path / "few", 2)
    assert [path.name for path in stale_jpeg_sheets(2, settings(), out, "set", "JPEG")] == ["set-002.jpg", "set-003.jpg"]
    with pytest.raises(FileExistsError):
        export_sheets(fewer, settings(), out, stem="set", format="JPEG")
    assert names(out) == ["set-001.jpg", "set-002.jpg", "set-003.jpg"]
    result = export_sheets(fewer, settings(), out, stem="set", format="JPEG", overwrite=True)
    assert names(out) == ["set-001.jpg"]
    assert [path.name for path in result.removed_sheets] == ["set-002.jpg", "set-003.jpg"] and not result.stale_sheets


def test_other_names_pdf_exports_and_source_photos_are_never_removed(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for name in ("set-extra.jpg", "set-2.jpg", "other-005.jpg", "set-005.png"):
        (out / name).write_bytes(b"keep")
    assert stale_jpeg_sheets(2, settings(), out, "set", "JPEG") == []
    assert stale_jpeg_sheets(2, settings(), out, "set", "PDF") == []
    # A source photo that happens to look like a trailing sheet blocks the export instead.
    source_folder = tmp_path / "src"
    loaded = photos(source_folder, 2)
    clash = source_folder / "photo-005.jpg"
    Image.new("RGB", (60, 40), "white").save(clash, "JPEG")
    loaded = photos(source_folder, 2)
    extra = [inspect_photo(clash)]
    before = clash.read_bytes()
    with pytest.raises(Exception):
        export_sheets(loaded + extra, settings(), source_folder, stem="photo", format="JPEG", overwrite=True)
    assert clash.read_bytes() == before


def test_staged_files_are_flushed_before_they_are_installed(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    events = []
    sync, commit = core._sync_file, core._commit_outputs
    monkeypatch.setattr(core, "_sync_file", lambda path: (events.append("sync"), sync(path))[1])
    monkeypatch.setattr(core, "_commit_outputs", lambda *args: (events.append("commit"), commit(*args))[1])
    export_sheets(photos(tmp_path / "in", 4), settings(), out, stem="set", format="JPEG")
    assert events == ["sync", "sync", "commit"]
