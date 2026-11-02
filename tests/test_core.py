from dataclasses import replace
import hashlib
import io
import os
from pathlib import Path
import threading

from PIL import Image
from pypdf import PdfReader
import pytest

import contact_sheet.core as core
from contact_sheet.core import (
    ExportCancelled, Photo, SheetSettings, collect_paths, export_sheets,
    inspect_photo, output_paths, render_page,
)


@pytest.fixture
def settings():
    return SheetSettings(rows=1, columns=2, dpi=72)


@pytest.fixture
def make_photo(tmp_path):
    def make(name="photo.png", size=(160, 100), color="red", **options):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new(options.pop("mode", "RGB"), size, color)
        image.save(path, **options)
        image.close()
        return inspect_photo(path)
    return make


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_settings_geometry_and_page_count():
    settings = SheetSettings()
    assert settings.per_page == 12
    assert settings.page_count(0) == 0
    assert settings.page_count(12) == 1
    assert settings.page_count(13) == 2
    assert settings.page_pixels() == (1654, 2339)
    assert replace(settings, orientation="Landscape").page_pixels(300) == (3508, 2480)
    assert replace(settings, page_size="Letter").page_pixels(200) == (1700, 2200)
    assert replace(settings, page_size="Legal").page_mm() == (215.9, 355.6)
    assert replace(settings, page_size="A3").page_mm() == (297.0, 420.0)


@pytest.mark.parametrize("changes", [
    {"rows": 0}, {"columns": 21}, {"rows": 2.5}, {"columns": True},
    {"margin_mm": -1}, {"gap_mm": float("nan")}, {"margin_mm": float("inf")},
    {"gap_mm": "4"}, {"rows": 20, "columns": 20, "gap_mm": 100},
    {"dpi": 71}, {"dpi": 301}, {"dpi": 200.0}, {"dpi": True},
    {"orientation": "sideways"}, {"page_size": "A0"}, {"title": "x" * 201},
    {"title": "new\nline"}, {"captions": "yes"},
])
def test_invalid_settings(changes):
    with pytest.raises(ValueError):
        replace(SheetSettings(), **changes).validate()


def test_bad_page_count_and_override():
    with pytest.raises(ValueError):
        SheetSettings().page_count(-1)
    with pytest.raises(ValueError):
        SheetSettings().page_count(1.5)
    with pytest.raises(ValueError):
        SheetSettings().page_pixels(1000)


def test_collect_natural_order_explicit_order_dedup(make_photo, tmp_path):
    photos = [make_photo(name) for name in ["folder/shot10.jpg", "folder/shot2.jpg", "folder/shot1.PNG"]]
    (tmp_path / "folder" / "ignore.txt").write_text("hello")
    result = collect_paths([photos[0].path, tmp_path / "folder", photos[1].path])
    assert [path.name for path in result] == ["shot10.jpg", "shot1.PNG", "shot2.jpg"]
    assert all(path.is_absolute() for path in result)


def test_collect_recursion_and_missing(make_photo, tmp_path):
    make_photo("root/one.jpg")
    make_photo("root/nested/two.png")
    assert len(collect_paths([tmp_path / "root"])) == 1
    assert len(collect_paths([tmp_path / "root"], recursive=True)) == 2
    with pytest.raises(ValueError, match="Not found"):
        collect_paths([tmp_path / "no.jpg"])


def test_collect_cancel_and_symlink_dedup(make_photo, tmp_path):
    photo = make_photo()
    link = tmp_path / "linked.png"
    try:
        link.symlink_to(photo.path)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    assert collect_paths([photo.path, link]) == [photo.path]
    event = threading.Event()
    event.set()
    with pytest.raises(ExportCancelled):
        collect_paths([photo.path], cancel=event)


def test_inspect_exif_rotates_pixels_and_dimensions(make_photo):
    exif = Image.Exif()
    exif[274] = 6
    photo = make_photo("rotation.jpg", size=(800, 400), exif=exif)
    assert (photo.width, photo.height) == (400, 800)
    with Image.open(io.BytesIO(photo.thumbnail)) as thumb:
        assert thumb.size == (64, 128)
        assert thumb.mode == "RGB"


def test_transparent_png_is_composited_on_white(make_photo):
    photo = make_photo("alpha.png", color=(255, 0, 0, 0), mode="RGBA")
    with Image.open(io.BytesIO(photo.thumbnail)) as thumb:
        assert thumb.getpixel((0, 0)) == (255, 255, 255)


def test_rejects_corruption_disguised_format_and_large(make_photo, tmp_path, monkeypatch):
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"This is not an image")
    with pytest.raises(ValueError, match="Cannot read"):
        inspect_photo(corrupt)
    fake = tmp_path / "fake.jpg"
    Image.new("RGB", (10, 10)).save(fake, format="BMP")
    with pytest.raises(ValueError, match="Only JPEG and PNG"):
        inspect_photo(fake)
    photo = make_photo(size=(100, 100))
    monkeypatch.setattr(core, "MAX_IMAGE_PIXELS", 9999)
    with pytest.raises(ValueError, match="safety limit"):
        inspect_photo(photo.path)


def test_bomb_warning_is_an_error(make_photo, monkeypatch):
    photo = make_photo(size=(100, 100))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 6000)
    with pytest.raises(ValueError, match="decompression bomb"):
        inspect_photo(photo.path)


def test_corrupt_png_crc_rejected(make_photo):
    photo = make_photo()
    data = bytearray(photo.path.read_bytes())
    start = data.index(b"IDAT")
    data[start + 5] ^= 1
    photo.path.write_bytes(data)
    with pytest.raises(ValueError):
        inspect_photo(photo.path)


def test_unicode_and_long_names_render(make_photo, settings):
    photo = make_photo("長い名前-été-Δοκιμή-" + "abcdefghij" * 12 + ".png")
    settings = replace(settings, title="Sélection — 撮影", rows=2, columns=1)
    image = render_page([photo], settings, 0)
    assert image.mode == "RGB"
    assert image.size == settings.page_pixels()
    image.close()
    lines = core._caption_lines(photo.path.name, core._caption_width_mm(settings))
    assert "".join(lines) == photo.path.name
    assert len(lines) == 2


def test_render_preserves_full_aspect_without_cropping(make_photo, settings):
    photo = make_photo(size=(1200, 200), color="red")
    settings = replace(settings, rows=1, columns=1, captions=False)
    image = render_page([photo], settings, 0)
    pixels = image.load()
    # Locate the colored image, excluding monochrome captions and footer.
    reds = [(x, y) for y in range(image.height) for x in range(image.width)
            if pixels[x, y][0] > 200 and pixels[x, y][1] < 40]
    min_x = min(x for x, _ in reds)
    max_x = max(x for x, _ in reds)
    min_y = min(y for _, y in reds)
    max_y = max(y for _, y in reds)
    assert (max_x - min_x + 1) / (max_y - min_y + 1) == pytest.approx(6, abs=0.1)
    assert min_x > 0 and max_x < image.width - 1
    image.close()


def test_invalid_page_index(make_photo, settings):
    for index in [-1, 1, True, 0.5]:
        with pytest.raises(ValueError):
            render_page([make_photo()], settings, index)
    with pytest.raises(ValueError):
        render_page([], settings, 0)


def test_changed_deleted_and_corrupt_sources_fail(make_photo, settings):
    photo = make_photo()
    Image.new("RGB", (160, 100), "blue").save(photo.path)
    with pytest.raises(ValueError, match="changed"):
        render_page([photo], settings, 0)
    photo = inspect_photo(photo.path)
    photo.path.write_bytes(b"broken")
    with pytest.raises(ValueError, match="changed"):
        render_page([photo], settings, 0)
    photo.path.unlink()
    with pytest.raises(ValueError, match="Cannot read"):
        render_page([photo], settings, 0)


def test_manually_built_photo_detects_dimension_change(make_photo, settings):
    original = make_photo()
    manual = Photo(original.path, 1, 1, original.thumbnail)
    with pytest.raises(ValueError, match="changed dimensions"):
        render_page([manual], settings, 0)


def test_output_path_plan(tmp_path, settings):
    assert output_paths(5, settings, tmp_path, "my-sheet", "JPEG") == [
        tmp_path / "my-sheet-001.jpg", tmp_path / "my-sheet-002.jpg", tmp_path / "my-sheet-003.jpg"]
    assert output_paths(5, settings, tmp_path, "my-sheet", "PDF") == [tmp_path / "my-sheet.pdf"]


@pytest.mark.parametrize("stem", ["", "../out", "foo/bar", "foo\\bar", "a:b", "a?b", "name.", " name", "name ", "CON", "nul.txt", "COM1", "LPT9", "CONIN$", "a\n", "x" * 121])
def test_nonportable_stems_rejected(tmp_path, settings, stem):
    with pytest.raises(ValueError):
        output_paths(1, settings, tmp_path, stem)


def test_no_photos_and_bad_format_rejected(tmp_path, settings):
    with pytest.raises(ValueError):
        export_sheets([], settings, tmp_path)
    with pytest.raises(ValueError):
        output_paths(1, settings, tmp_path, format="GIF")


def test_jpeg_export_dimensions_metadata_pagination_and_order(make_photo, settings, tmp_path):
    photos = [make_photo(f"source{i}.png", color=color) for i, color in enumerate(["red", "green", "blue"])]
    originals = {photo.path: digest(photo.path) for photo in photos}
    progress = []
    outputs = export_sheets(photos, settings, tmp_path, "sélection", "JPEG", progress=lambda done, total: progress.append((done, total)))
    assert [p.name for p in outputs] == ["sélection-001.jpg", "sélection-002.jpg"]
    assert progress == [(1, 2), (2, 2)]
    with Image.open(outputs[0]) as page:
        assert page.size == settings.page_pixels()
        assert page.info["dpi"] == (72, 72)
        # Each original is centered in its cell. Confirm the page's left-to-right order.
        left = page.getpixel((page.width // 4, page.height // 2 - 20))
        right = page.getpixel((3 * page.width // 4, page.height // 2 - 20))
        assert left[0] > 180 and left[1] < 40
        assert right[1] > 80 and right[0] < 40
    with Image.open(outputs[1]) as page:
        left = page.getpixel((page.width // 4, page.height // 2 - 20))
        assert left[2] > 180 and left[0] < 40
    assert originals == {photo.path: digest(photo.path) for photo in photos}
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_pdf_multiple_pages_and_physical_size(make_photo, settings, tmp_path):
    photos = [make_photo(f"source{i}.png") for i in range(5)]
    settings = replace(settings, page_size="Letter", orientation="Landscape", title="A private test")
    output = export_sheets(photos, settings, tmp_path)[0]
    pdf = PdfReader(output)
    assert len(pdf.pages) == 3
    assert float(pdf.pages[0].mediabox.width) == pytest.approx(792)
    assert float(pdf.pages[0].mediabox.height) == pytest.approx(612)
    assert pdf.metadata.title == "A private test"
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_existing_outputs_never_overwritten_without_permission(make_photo, settings, tmp_path):
    target = tmp_path / "contact-sheet.pdf"
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        export_sheets([make_photo()], settings, tmp_path)
    assert target.read_bytes() == b"existing"
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_authorized_overwrite_succeeds(make_photo, settings, tmp_path):
    target = tmp_path / "contact-sheet.pdf"
    target.write_bytes(b"existing")
    export_sheets([make_photo()], settings, tmp_path, overwrite=True)
    assert target.read_bytes().startswith(b"%PDF")
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_original_output_collision_never_overwritten(make_photo, settings, tmp_path):
    photo = make_photo("contact-sheet-001.jpg")
    original = digest(photo.path)
    with pytest.raises(ValueError, match="original"):
        export_sheets([photo], settings, tmp_path, format="JPEG", overwrite=True)
    assert digest(photo.path) == original


def test_hardlink_source_collision_never_overwritten(make_photo, settings, tmp_path):
    photo = make_photo()
    target = tmp_path / "contact-sheet-001.jpg"
    try:
        os.link(photo.path, target)
    except OSError:
        pytest.skip("Hardlinks unavailable")
    original = digest(photo.path)
    with pytest.raises(ValueError, match="original"):
        export_sheets([photo], settings, tmp_path, format="JPEG", overwrite=True)
    assert digest(photo.path) == original
    assert digest(target) == original


def test_symlink_output_and_folder_output_rejected(make_photo, settings, tmp_path):
    photo = make_photo()
    target = tmp_path / "contact-sheet.pdf"
    target.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        export_sheets([photo], settings, tmp_path, overwrite=True)
    target.rmdir()
    external = tmp_path / "external.pdf"
    external.write_bytes(b"external")
    try:
        target.symlink_to(external)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError, match="regular file"):
        export_sheets([photo], settings, tmp_path, overwrite=True)
    assert external.read_bytes() == b"external"


def test_cancel_before_start_and_during_render_cleans_up(make_photo, settings, tmp_path):
    photo = make_photo()
    event = threading.Event()
    event.set()
    with pytest.raises(ExportCancelled):
        export_sheets([photo], settings, tmp_path, cancel=event)
    event.clear()
    with pytest.raises(ExportCancelled):
        export_sheets([photo] * 5, settings, tmp_path, format="JPEG", cancel=event,
                      progress=lambda done, total: event.set())
    assert not list(tmp_path.glob("contact-sheet*"))
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_cancel_pdf_before_commit_preserves_existing(make_photo, settings, tmp_path):
    photo = make_photo()
    target = tmp_path / "contact-sheet.pdf"
    target.write_bytes(b"old export")
    event = threading.Event()
    with pytest.raises(ExportCancelled):
        export_sheets([photo], settings, tmp_path, overwrite=True, cancel=event,
                      progress=lambda done, total: event.set())
    assert target.read_bytes() == b"old export"
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_progress_failure_cleans_staging(make_photo, settings, tmp_path):
    def fail(*_):
        raise RuntimeError("callback failed")
    with pytest.raises(RuntimeError, match="callback"):
        export_sheets([make_photo()], settings, tmp_path, progress=fail)
    assert not list(tmp_path.glob("contact-sheet*"))
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_racing_new_output_is_not_overwritten(make_photo, settings, tmp_path):
    target = tmp_path / "contact-sheet.pdf"
    def race(*_):
        target.write_bytes(b"someone else's work")
    with pytest.raises(FileExistsError, match="changed"):
        export_sheets([make_photo()], settings, tmp_path, overwrite=True, progress=race)
    assert target.read_bytes() == b"someone else's work"
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_racing_modified_output_is_not_overwritten(make_photo, settings, tmp_path):
    target = tmp_path / "contact-sheet.pdf"
    target.write_bytes(b"old")
    def race(*_):
        target.write_bytes(b"new unrelated export")
    with pytest.raises(FileExistsError, match="changed"):
        export_sheets([make_photo()], settings, tmp_path, overwrite=True, progress=race)
    assert target.read_bytes() == b"new unrelated export"


def test_partial_commit_rolls_back_new_files(make_photo, settings, tmp_path, monkeypatch):
    original_link = os.link
    def fail_second(source, target, *args, **kwargs):
        if Path(target).name == "contact-sheet-002.jpg":
            raise OSError("simulated disk failure")
        return original_link(source, target, *args, **kwargs)
    monkeypatch.setattr(core, "_WINDOWS", False)
    monkeypatch.setattr(os, "link", fail_second)
    with pytest.raises(OSError, match="simulated"):
        export_sheets([make_photo()] * 3, settings, tmp_path, format="JPEG")
    assert not list(tmp_path.glob("contact-sheet-*.jpg"))
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_partial_overwrite_restores_old_files(make_photo, settings, tmp_path, monkeypatch):
    targets = [tmp_path / f"contact-sheet-{index:03d}.jpg" for index in [1, 2]]
    for index, target in enumerate(targets):
        target.write_bytes(f"old {index}".encode())
    original_link = os.link
    def fail_second(source, target, *args, **kwargs):
        if Path(source).name == "contact-sheet-002.jpg":
            raise OSError("simulated disk failure")
        return original_link(source, target, *args, **kwargs)
    monkeypatch.setattr(core, "_WINDOWS", False)
    monkeypatch.setattr(os, "link", fail_second)
    with pytest.raises(OSError, match="simulated"):
        export_sheets([make_photo()] * 3, settings, tmp_path, format="JPEG", overwrite=True)
    assert [target.read_bytes() for target in targets] == [b"old 0", b"old 1"]
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_cancel_mid_commit_rolls_back(make_photo, settings, tmp_path, monkeypatch):
    event = threading.Event()
    original_link = os.link
    def cancel_after_link(source, target, *args, **kwargs):
        result = original_link(source, target, *args, **kwargs)
        event.set()
        return result
    monkeypatch.setattr(core, "_WINDOWS", False)
    monkeypatch.setattr(os, "link", cancel_after_link)
    with pytest.raises(ExportCancelled):
        export_sheets([make_photo()] * 3, settings, tmp_path, format="JPEG", cancel=event)
    assert not list(tmp_path.glob("contact-sheet-*.jpg"))
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_late_invalid_source_does_not_commit_earlier_pages(make_photo, settings, tmp_path):
    first = make_photo("first.png")
    last = make_photo("last.png")
    last.path.write_bytes(b"bad image")
    with pytest.raises(ValueError):
        export_sheets([first, first, last], settings, tmp_path, format="JPEG")
    assert not list(tmp_path.glob("contact-sheet-*.jpg"))
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_source_changed_after_render_still_blocks_commit(make_photo, settings, tmp_path):
    photo = make_photo()
    def edit_after_render(*_):
        Image.new("RGB", (160, 100), "blue").save(photo.path)
    with pytest.raises(ValueError, match="changed during export"):
        export_sheets([photo], settings, tmp_path, progress=edit_after_render)
    assert not list(tmp_path.glob("contact-sheet*"))
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_source_replaced_after_render_blocks_commit(make_photo, settings, tmp_path):
    photo = make_photo()
    second = make_photo("second.png", color="blue")
    def replace_after_render(*_):
        os.replace(second.path, photo.path)
    with pytest.raises(ValueError, match="changed during export"):
        export_sheets([photo], settings, tmp_path, progress=replace_after_render)
    assert not list(tmp_path.glob("contact-sheet*"))
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_natural_sort_accepts_nondecimal_unicode_digits(make_photo, tmp_path):
    for name in ["①1.jpg", "²1.jpg", "photo2.jpg", "photo10.jpg"]:
        make_photo(name)
    paths = collect_paths([tmp_path])
    assert len(paths) == 4
    assert [p.name for p in paths if p.name.startswith("photo")] == ["photo2.jpg", "photo10.jpg"]


def test_inspect_can_be_cancelled(make_photo):
    photo = make_photo()
    event = threading.Event()
    event.set()
    with pytest.raises(ExportCancelled):
        inspect_photo(photo.path, cancel=event)


@pytest.fixture
def unsupported_hardlinks(monkeypatch):
    import errno
    def unsupported(*args, **kwargs):
        raise OSError(errno.EOPNOTSUPP, "hardlinks unavailable")
    monkeypatch.setattr(core, "_WINDOWS", False)
    monkeypatch.setattr(os, "link", unsupported)


def test_exclusive_copy_fallback_exports(make_photo, settings, tmp_path, unsupported_hardlinks):
    output = export_sheets([make_photo()], settings, tmp_path)[0]
    assert len(PdfReader(output).pages) == 1
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_exclusive_copy_fallback_still_refuses_existing(tmp_path, unsupported_hardlinks):
    source, target = tmp_path / "staged", tmp_path / "target"
    source.write_bytes(b"new")
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        core._install_exclusive(source, target)
    assert target.read_bytes() == b"existing"


def test_exclusive_copy_fallback_protects_original(make_photo, settings, tmp_path, unsupported_hardlinks):
    photo = make_photo("contact-sheet-001.jpg")
    old = digest(photo.path)
    with pytest.raises(ValueError, match="original"):
        export_sheets([photo], settings, tmp_path, format="JPEG", overwrite=True)
    assert digest(photo.path) == old


def test_exclusive_copy_cancel_removes_partial(tmp_path, unsupported_hardlinks, monkeypatch):
    source, target = tmp_path / "staged", tmp_path / "target"
    source.write_bytes(b"data" * 500_000)
    event = threading.Event()
    real_check = core._check_cancel
    count = 0
    def cancel_during_copy(cancel):
        nonlocal count
        count += 1
        if count == 3:
            event.set()
        real_check(cancel)
    monkeypatch.setattr(core, "_check_cancel", cancel_during_copy)
    with pytest.raises(ExportCancelled):
        core._install_exclusive(source, target, event)
    assert not target.exists()
    assert source.exists()


def test_exclusive_copy_error_removes_partial(tmp_path, unsupported_hardlinks, monkeypatch):
    source, target = tmp_path / "staged", tmp_path / "target"
    source.write_bytes(b"new")
    def fail_sync(*args):
        raise OSError("write failure")
    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(OSError, match="write failure"):
        core._install_exclusive(source, target)
    assert not target.exists()


def test_exclusive_copy_overwrite_error_restores_old_export(make_photo, settings, tmp_path, unsupported_hardlinks, monkeypatch):
    target = tmp_path / "contact-sheet.pdf"
    target.write_bytes(b"old export")
    real_sync = os.fsync
    count = 0
    def fail_once(*args):
        nonlocal count
        count += 1
        if count == 1:
            raise OSError("write failure")
        return real_sync(*args)
    monkeypatch.setattr(os, "fsync", fail_once)
    with pytest.raises(OSError, match="write failure"):
        export_sheets([make_photo()], settings, tmp_path, overwrite=True)
    assert target.read_bytes() == b"old export"
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_reject_nonboolean_overwrite(make_photo, settings, tmp_path):
    target = tmp_path / "contact-sheet.pdf"
    target.write_bytes(b"old export")
    with pytest.raises(ValueError, match="Overwrite"):
        export_sheets([make_photo()], settings, tmp_path, overwrite="false")
    assert target.read_bytes() == b"old export"


def test_exclusive_copy_cancel_restores_previous_export(make_photo, settings, tmp_path, unsupported_hardlinks, monkeypatch):
    target = tmp_path / "contact-sheet.pdf"
    target.write_bytes(b"previous export")
    event = threading.Event()
    real_sync = os.fsync
    def cancel_after_flush(*args):
        result = real_sync(*args)
        event.set()
        return result
    monkeypatch.setattr(os, "fsync", cancel_after_flush)
    with pytest.raises(ExportCancelled):
        export_sheets([make_photo()], settings, tmp_path, overwrite=True, cancel=event)
    assert target.read_bytes() == b"previous export"
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_exclusive_copy_late_arriving_target_preserved(tmp_path, monkeypatch):
    import errno
    source, target = tmp_path / "staged", tmp_path / "target"
    source.write_bytes(b"new")
    def race(*args):
        target.write_bytes(b"another app's file")
        raise OSError(errno.EOPNOTSUPP, "hardlinks unavailable")
    monkeypatch.setattr(core, "_WINDOWS", False)
    monkeypatch.setattr(os, "link", race)
    with pytest.raises(FileExistsError):
        core._install_exclusive(source, target)
    assert target.read_bytes() == b"another app's file"


def test_permissions_error_does_not_trigger_copy_fallback(tmp_path, monkeypatch):
    import errno
    source, target = tmp_path / "staged", tmp_path / "target"
    source.write_bytes(b"new")
    def denied(*args):
        raise PermissionError(errno.EACCES, "permission denied")
    monkeypatch.setattr(core, "_WINDOWS", False)
    monkeypatch.setattr(os, "link", denied)
    with pytest.raises(PermissionError):
        core._install_exclusive(source, target)
    assert not target.exists()


def test_external_change_during_rollback_is_preserved_and_reported(make_photo, settings, tmp_path, monkeypatch):
    install = core._install_exclusive
    def inject_change(source, target, cancel=None):
        if target.name.endswith("002.jpg"):
            raise ExportCancelled("Cancelled")
        signature = install(source, target, cancel)
        target.write_bytes(b"an external writer's update")
        return signature
    monkeypatch.setattr(core, "_install_exclusive", inject_change)
    with pytest.raises(RuntimeError, match="could not be safely rolled back"):
        export_sheets([make_photo()] * 3, settings, tmp_path, format="JPEG")
    assert (tmp_path / "contact-sheet-001.jpg").read_bytes() == b"an external writer's update"
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_partial_copy_cleanup_failure_is_reported(tmp_path, unsupported_hardlinks, monkeypatch):
    source, target = tmp_path / "staged", tmp_path / "target"
    source.write_bytes(b"new")
    def fail_sync(*args):
        raise OSError("write failed")
    real_unlink = Path.unlink
    def locked_unlink(path, *args, **kwargs):
        if path == target:
            raise PermissionError("file locked")
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(os, "fsync", fail_sync)
    monkeypatch.setattr(Path, "unlink", locked_unlink)
    with pytest.raises(RuntimeError, match="file remains at"):
        core._install_exclusive(source, target)
    assert target.exists()


def test_windows_rename_branch_rolls_back_moves(make_photo, settings, tmp_path, monkeypatch):
    """Exercise consumed staging paths; native Windows behavior needs its own smoke test."""
    targets = [tmp_path / f"contact-sheet-{index:03d}.jpg" for index in [1, 2]]
    for index, target in enumerate(targets):
        target.write_bytes(f"old {index}".encode())
    real_rename = os.rename
    def windows_rename(source, target):
        if Path(source).name == "contact-sheet-002.jpg":
            raise ExportCancelled("simulated cancel")
        if Path(target).exists():
            raise FileExistsError(str(target))
        return real_rename(source, target)
    monkeypatch.setattr(core, "_WINDOWS", True)
    monkeypatch.setattr(os, "rename", windows_rename)
    with pytest.raises(ExportCancelled):
        export_sheets([make_photo()] * 3, settings, tmp_path, format="JPEG", overwrite=True)
    assert [target.read_bytes() for target in targets] == [b"old 0", b"old 1"]
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_small_sources_have_same_physical_fit_at_preview_and_export_dpi(make_photo):
    photo = make_photo('tiny.png', size=(30, 20), color='red')
    settings = SheetSettings(rows=4, columns=3, captions=False)
    from PIL import ImageChops
    bounds = []
    for dpi in (90, 200, 300):
        with render_page([photo], settings, 0, dpi=dpi) as image:
            # Red source pixels are distinct from black/grey footer and white page.
            red, green, blue = image.split()
            mask = ImageChops.subtract(red, green).point(lambda v: 255 if v > 180 else 0)
            box = mask.getbbox()
            bounds.append(tuple(v / dpi for v in box))
            assert (box[2] - box[0]) > 30  # This source is intentionally upscaled.
    for other in bounds[1:]:
        assert other == pytest.approx(bounds[0], abs=0.025)


def test_keep_both_uses_one_available_stem_for_whole_batch(tmp_path):
    from contact_sheet.core import available_output_stem
    settings = SheetSettings(rows=1, columns=1)
    (tmp_path / 'sheet-002.jpg').write_bytes(b'old')
    (tmp_path / 'sheet (2)-001.jpg').mkdir()
    occupied = tmp_path / 'sheet (3)-003.jpg'
    try:
        occupied.symlink_to(tmp_path / 'missing')
    except OSError:  # Windows without permission to create symlinks.
        occupied.write_bytes(b'occupied')
    assert available_output_stem(3, settings, tmp_path, 'sheet', 'JPEG') == 'sheet (4)'
    assert available_output_stem(1, settings, tmp_path, 'fresh', 'PDF') == 'fresh'


def test_keep_both_long_stem_stays_valid(tmp_path):
    from contact_sheet.core import available_output_stem, output_paths
    stem = 'a' * 120
    (tmp_path / f'{stem}.pdf').write_bytes(b'old')
    chosen = available_output_stem(1, SheetSettings(), tmp_path, stem, 'PDF')
    assert len(chosen) == 120
    assert chosen.endswith(' (2)')
    assert output_paths(1, SheetSettings(), tmp_path, chosen)


def test_committed_export_reports_retained_backup_as_success(make_photo, settings, tmp_path, monkeypatch):
    photo = make_photo('input.png')
    target = tmp_path / 'sheet.pdf'
    target.write_bytes(b'previous sheets')
    real_unlink = Path.unlink
    def locked_backup(path, *args, **kwargs):
        if path.name.startswith('backup-'):
            raise PermissionError('backup temporarily locked')
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', locked_backup)
    outputs = export_sheets([photo], settings, tmp_path, 'sheet', overwrite=True)
    assert outputs == [target]
    assert target.read_bytes().startswith(b'%PDF')
    assert len(outputs.retained_backups) == 1
    assert outputs.retained_backups[0].read_bytes() == b'previous sheets'


def test_keep_both_search_is_bounded(tmp_path, monkeypatch):
    from contact_sheet.core import available_output_stem
    monkeypatch.setattr(Path, 'exists', lambda path: True)
    with pytest.raises(ValueError, match='Choose another filename'):
        available_output_stem(1, SheetSettings(), tmp_path, 'sheet')


def test_keep_both_name_race_still_refuses_overwrite(make_photo, settings, tmp_path):
    from contact_sheet.core import available_output_stem
    photo = make_photo('input.png')
    (tmp_path / 'sheet.pdf').write_bytes(b'old')
    chosen = available_output_stem(1, settings, tmp_path, 'sheet')
    raced = tmp_path / f'{chosen}.pdf'
    raced.write_bytes(b'other writer')
    with pytest.raises(FileExistsError):
        export_sheets([photo], settings, tmp_path, chosen)
    assert raced.read_bytes() == b'other writer'
    assert (tmp_path / 'sheet.pdf').read_bytes() == b'old'
    assert not list(tmp_path.glob('.contact-sheet-*'))


@pytest.mark.parametrize('format', ['PDF', 'JPEG'])
def test_cancel_keep_both_batch_preserves_old_outputs(make_photo, tmp_path, format):
    from contact_sheet.core import available_output_stem, output_paths
    photo = make_photo('input.png')
    settings = SheetSettings(rows=1, columns=1, dpi=150)
    old_paths = output_paths(2, settings, tmp_path, 'sheet', format)
    for path in old_paths:
        path.write_bytes(b'old sheet')
    chosen = available_output_stem(2, settings, tmp_path, 'sheet', format)
    cancel = threading.Event()
    with pytest.raises(ExportCancelled):
        export_sheets([photo, photo], settings, tmp_path, chosen, format,
                      cancel=cancel, progress=lambda done, total: cancel.set())
    assert all(path.read_bytes() == b'old sheet' for path in old_paths)
    assert not any(path.exists() for path in output_paths(2, settings, tmp_path, chosen, format))
    assert not list(tmp_path.glob('.contact-sheet-*'))


def test_keep_both_avoids_leftover_pages_of_an_older_longer_batch(tmp_path):
    from contact_sheet.core import available_output_stem
    settings = SheetSettings(rows=1, columns=1)
    (tmp_path / 'sheet-001.jpg').write_bytes(b'old first batch')
    (tmp_path / 'sheet (2)-009.jpg').write_bytes(b'old longer second batch')
    assert available_output_stem(1, settings, tmp_path, 'sheet', 'JPEG') == 'sheet (3)'


def test_collection_reports_unique_unsupported_without_changing_order(make_photo, tmp_path):
    photos = [make_photo(name) for name in ["folder/shot10.jpg", "folder/shot2.PNG"]]
    folder = tmp_path / "folder"
    unsupported = folder / "notes.txt"
    unsupported.write_text("not an image")
    (folder / "nested").mkdir()
    (folder / "nested" / "ignored.txt").write_text("not traversed")
    found = collect_paths([photos[0].path, unsupported, folder, unsupported])
    assert found == [photo.path for photo in photos]
    assert found.unsupported_paths == (unsupported,)


def test_unsupported_alias_does_not_hide_supported_source(make_photo, tmp_path):
    photo = make_photo()
    alias = tmp_path / "alias.txt"
    try:
        alias.symlink_to(photo.path)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    found = collect_paths([alias, photo.path])
    assert found == [photo.path]
    assert found.unsupported_paths == (photo.path,)


@pytest.mark.parametrize("format", ["PDF", "JPEG"])
def test_export_phase_order_keeps_render_count_separate_from_commit(make_photo, tmp_path, monkeypatch, format):
    events = []
    original_verify = core._verify_sources
    original_commit = core._commit_outputs

    def verify(*args):
        assert events[-1] == "checking"
        assert not list(tmp_path.glob("phases.*"))
        assert not list(tmp_path.glob("phases-*.jpg"))
        return original_verify(*args)

    def commit(*args):
        assert events[-1] == "committing"
        return original_commit(*args)

    monkeypatch.setattr(core, "_verify_sources", verify)
    monkeypatch.setattr(core, "_commit_outputs", commit)
    results = export_sheets([make_photo()], SheetSettings(dpi=72), tmp_path,
                            "phases", format, phase=events.append,
                            progress=lambda done, total: events.append((done, total)))
    assert events == ["rendering", (1, 1), "checking", "committing"]
    assert all(path.is_file() for path in results)


@pytest.mark.parametrize("phase", ["checking", "committing"])
def test_cancellation_at_export_phase_preserves_existing_output(make_photo, tmp_path, phase):
    cancel = threading.Event()
    old = tmp_path / "phases.pdf"
    old.write_bytes(b"previous sheet")
    def change_phase(value):
        if value == phase:
            cancel.set()
    with pytest.raises(ExportCancelled):
        export_sheets([make_photo()], SheetSettings(dpi=72), tmp_path, "phases", "PDF",
                      overwrite=True, cancel=cancel, phase=change_phase)
    assert old.read_bytes() == b"previous sheet"
    assert not list(tmp_path.glob(".contact-sheet-*"))


def test_vanished_unsupported_sibling_does_not_discard_supported_photos(make_photo, tmp_path, monkeypatch):
    photo = make_photo("folder/photo.png")
    sidecar = photo.path.parent / "vanishing.txt"
    sidecar.write_text("unrelated sidecar")
    original_key = core._natural_key
    def remove_after_enumeration(path):
        if path.name == sidecar.name:
            sidecar.unlink()
        return original_key(path)
    monkeypatch.setattr(core, "_natural_key", remove_after_enumeration)
    found = collect_paths([photo.path.parent])
    assert found == [photo.path]
    assert found.unsupported_paths == (sidecar,)


def test_unresolvable_unsupported_sibling_does_not_discard_supported_photos(make_photo, tmp_path, monkeypatch):
    photo = make_photo("folder/photo.png")
    sidecar = photo.path.parent / "unreadable.txt"
    sidecar.write_text("unrelated sidecar")
    original_resolve = Path.resolve
    def denied_sidecar(path, *args, **kwargs):
        if path.name == sidecar.name:
            raise OSError("sidecar became unreadable")
        return original_resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", denied_sidecar)
    found = collect_paths([photo.path.parent])
    assert found == [photo.path]
    assert found.unsupported_paths == (sidecar,)


@pytest.mark.parametrize("dpi", [90, 150, 200, 300])
def test_two_line_captions_preserve_names_and_physical_metrics(make_photo, monkeypatch, dpi):
    from PIL import ImageDraw
    filename = "portrait-study-session-2026-October-selected-01.png"
    photo = make_photo(filename)
    settings = SheetSettings(dpi=200)
    drawn = []
    original = ImageDraw.ImageDraw.text
    def record(draw, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        if font is not None and font.size == core.CAPTION_SIZE:
            box = draw.textbbox(xy, text, font=font)
            drawn.append((text, box, draw._image.size))
        return original(draw, xy, text, *args, **kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    page = render_page([photo], settings, 0, dpi=dpi)
    try:
        assert [text for text, _, _ in drawn] == [
            "portrait-study-session-", "2026-October-selected-01.png"]
        assert "".join(text for text, _, _ in drawn) == filename
        for _, box, (width, height) in drawn:
            assert 0 <= box[0] < box[2] <= width
            assert 0 <= box[1] < box[3] <= height
            assert height / core.CAPTION_DPI * 25.4 == pytest.approx(9, abs=.02)
        assert core.CAPTION_SIZE / core.CAPTION_DPI * 72 == 8
    finally:
        page.close()


@pytest.mark.parametrize("format", ["PDF", "JPEG"])
def test_later_page_caption_overflow_rejects_before_any_output_mutation(make_photo, tmp_path, monkeypatch, format):
    photos = [make_photo(f"photo-{i}.png") for i in range(12)]
    photos.append(make_photo("W" * 115 + ".png"))
    settings = SheetSettings()
    output = tmp_path / "sheets"
    output.mkdir()
    previous = output / ("contact-sheet.pdf" if format == "PDF" else "contact-sheet-001.jpg")
    previous.write_bytes(b"previous export")
    source_hashes = {photo.path: digest(photo.path) for photo in photos}
    def no_stage(*args, **kwargs):
        raise AssertionError("Caption preflight must finish before creating output staging")
    monkeypatch.setattr(core.tempfile, "mkdtemp", no_stage)
    with pytest.raises(core.CaptionLayoutError, match="page 2") as error:
        export_sheets(photos, settings, output, format=format, overwrite=True)
    assert "fewer columns" in str(error.value)
    assert "Filename captions" in str(error.value)
    assert previous.read_bytes() == b"previous export"
    assert list(output.iterdir()) == [previous]
    assert source_hashes == {photo.path: digest(photo.path) for photo in photos}
    core.validate_captions(photos, replace(settings, columns=1))
    core.validate_captions(photos, replace(settings, captions=False))


def test_caption_wrap_preserves_combining_characters_and_extension():
    name = ("e\u0301tude-" * 8) + "final.png"
    lines = core._caption_lines(name, 60)
    assert len(lines) == 2
    assert "".join(lines) == name
    assert not lines[1].startswith("\u0301")
    assert lines[-1].endswith(".png")


def test_caption_preflight_can_be_cancelled(make_photo):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ExportCancelled):
        core.validate_captions([make_photo()], SheetSettings(), cancel)
