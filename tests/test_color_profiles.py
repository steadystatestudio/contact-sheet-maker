"""Color correctness through the same import/render path used by previews/exports."""
import hashlib
import io
from pathlib import Path

from PIL import Image, ImageCms
import pytest

from contact_sheet.core import SheetSettings, export_sheets, inspect_photo, render_page


PROFILES = Path(__file__).parent / "fixtures" / "icc"


@pytest.mark.parametrize("mode, color, filename, profile_name", [
    ("CMYK", (70, 40, 10, 0), "cmyk.jpg", "CGATS001Compat-v2-micro.icc"),
    ("RGB", (180, 100, 90), "wide-gamut.png", "DisplayP3-v4.icc"),
])
def test_embedded_profile_changes_pixels_before_sheet_export(tmp_path, mode, color, filename, profile_name):
    path = tmp_path / filename
    profile = (PROFILES / profile_name).read_bytes()
    with Image.new(mode, (200, 200), color) as source:
        source.save(path, icc_profile=profile)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with Image.open(path) as source:
        with ImageCms.profileToProfile(source, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                       ImageCms.createProfile("sRGB"), outputMode="RGB") as managed:
            expected = managed.getpixel((100, 100))
        with source.convert("RGB") as unmanaged:
            assert expected != unmanaged.getpixel((100, 100)), "Fixture must detect ignored profiles"
    photo = inspect_photo(path)
    with Image.open(io.BytesIO(photo.thumbnail)) as thumbnail:
        assert thumbnail.getpixel((thumbnail.width // 2, thumbnail.height // 2)) == expected
    settings = SheetSettings(rows=1, columns=1, captions=False, dpi=150)
    with render_page([photo], settings, 0) as page:
        assert page.getpixel((page.width // 2, page.height // 2)) == expected
    output = export_sheets([photo], settings, tmp_path, format="JPEG")[0]
    with Image.open(output) as page:
        actual = page.getpixel((page.width // 2, page.height // 2))
        assert max(abs(a - b) for a, b in zip(actual, expected)) <= 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("mode, color, profile_name", [
    ("RGBA", (180, 100, 90, 128), "DisplayP3-v4.icc"),
    ("LA", (80, 128), "sGrey-v4.icc"),
])
def test_profile_conversion_preserves_alpha_before_white_compositing(tmp_path, mode, color, profile_name):
    path = tmp_path / "transparent.png"
    profile = (PROFILES / profile_name).read_bytes()
    with Image.new(mode, (64, 64), color) as source:
        source.save(path, icc_profile=profile)
        with source.convert("L" if mode == "LA" else "RGB") as pixels:
            with ImageCms.profileToProfile(pixels, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                           ImageCms.createProfile("sRGB"), outputMode="RGB") as managed:
                expected = Image.new("RGB", managed.size, "white")
                with source.getchannel("A") as alpha:
                    expected.paste(managed, mask=alpha)
                expected_pixel = expected.getpixel((32, 32))
                expected.close()
    with Image.open(io.BytesIO(inspect_photo(path).thumbnail)) as thumbnail:
        assert thumbnail.getpixel((32, 32)) == expected_pixel


@pytest.mark.parametrize("profile", [b"not an ICC profile", (PROFILES / "CGATS001Compat-v2-micro.icc").read_bytes()])
def test_invalid_or_incompatible_profile_is_reported_without_modifying_photo(tmp_path, profile):
    path = tmp_path / "bad-profile.png"
    with Image.new("RGB", (40, 40), "red") as source:
        source.save(path, icc_profile=profile)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Invalid or unsupported color profile"):
        inspect_photo(path)
    assert path.read_bytes() == before


def test_profiled_palette_transparency_stays_white(tmp_path):
    path = tmp_path / "palette.png"
    profile = (PROFILES / "DisplayP3-v4.icc").read_bytes()
    with Image.new("P", (64, 64), 0) as source:
        source.putpalette([180, 100, 90, 20, 40, 60] + [0] * 762)
        source.save(path, transparency=0, icc_profile=profile)
    with Image.open(io.BytesIO(inspect_photo(path).thumbnail)) as thumbnail:
        assert thumbnail.getpixel((32, 32)) == (255, 255, 255)


def test_untagged_photo_keeps_existing_srgb_pixels(tmp_path):
    path = tmp_path / "untagged.png"
    with Image.new("RGB", (64, 64), (180, 100, 90)) as source:
        source.save(path)
    with Image.open(io.BytesIO(inspect_photo(path).thumbnail)) as thumbnail:
        assert thumbnail.getpixel((32, 32)) == (180, 100, 90)
