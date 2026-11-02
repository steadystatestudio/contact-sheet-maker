"""Exported sheets must also parse in strict PDF consumers."""
import gc
import weakref

from PIL import Image
from pypdf import PdfReader

from contact_sheet.core import SheetSettings, export_sheets, inspect_photo


def test_letter_pdf_every_page_has_readable_image_data(tmp_path):
    """This third-page raster split the inline ASCII85 EOD marker at 60 columns."""
    source = tmp_path / "gold.png"
    with Image.new("RGB", (300, 180), (230, 180, 30)) as image:
        image.save(source)
    before = source.read_bytes()
    photo = inspect_photo(source)
    settings = SheetSettings(page_size="Letter", rows=2, columns=3,
                             margin_mm=15, gap_mm=6, captions=False, dpi=150)
    output = export_sheets([photo] * 13, settings, tmp_path, stem="strict-reader")[0]
    reader = PdfReader(output, strict=True)
    assert len(reader.pages) == 3
    for page in reader.pages:
        assert page.get_contents().operations
        assert len(page.images) == 1
        with page.images[0].image as raster:
            assert raster.size == (1275, 1650)
            assert raster.getpixel((round(15 * 150 / 25.4 + (215.9 - 30 - 12) / 6 * 150 / 25.4),
                                    round(15 * 150 / 25.4 + (279.4 - 30 - 8 - 6) / 4 * 150 / 25.4))) == (230, 180, 30)
    assert source.read_bytes() == before


def test_pdf_does_not_retain_decoded_page_readers(tmp_path, monkeypatch):
    """Only compressed page data should accumulate while a long PDF is built."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    source = tmp_path / "photo.png"
    Image.new("RGB", (40, 30), (10, 80, 150)).save(source)
    photo = inspect_photo(source)
    references = []
    draw_image = canvas.Canvas.drawImage

    def draw_and_observe(self, image, *args, **kwargs):
        assert isinstance(image, ImageReader)
        gc.collect()
        assert all(reference() is None for reference in references)
        references.append(weakref.ref(image))
        return draw_image(self, image, *args, **kwargs)

    monkeypatch.setattr(canvas.Canvas, "drawImage", draw_and_observe)
    export_sheets([photo] * 5, SheetSettings(rows=1, columns=1, dpi=72), tmp_path)
    gc.collect()
    assert len(references) == 5
    assert all(reference() is None for reference in references)
