"""Local, non-destructive JPEG/PNG contact-sheet rendering and atomic export."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import errno
import hashlib
import io
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import threading
from typing import Callable, Iterable
import unicodedata
import warnings

from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError


_WINDOWS = os.name == "nt"
MAX_IMAGE_PIXELS = 60_000_000
CAPTION_HEIGHT_MM = 9.0
CAPTION_DPI = 720
CAPTION_SIZE = 8 * CAPTION_DPI // 72
SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
PAGE_SIZES_MM = {"A4": (210.0, 297.0), "A3": (297.0, 420.0),
                 "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}


class ExportCancelled(RuntimeError):
    """The user cancelled; no partial export is intentionally retained."""


class CaptionLayoutError(ValueError):
    """A complete filename cannot fit the chosen sheet layout."""

    def __init__(self, filename: str, page: int):
        self.summary = (f"A filename on page {page} does not fit. Use fewer columns, "
                        "landscape, smaller margins/gaps, or turn off Filename captions.")
        super().__init__(f"{self.summary}\nFilename: {filename}")


CancelledError = ExportCancelled


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ExportCancelled("Cancelled.")


def _validate_dpi(dpi: int) -> None:
    if isinstance(dpi, bool) or not isinstance(dpi, int) or not 72 <= dpi <= 300:
        raise ValueError("DPI must be a whole number between 72 and 300.")


@dataclass(frozen=True)
class SheetSettings:
    page_size: str = "A4"
    orientation: str = "Portrait"
    rows: int = 4
    columns: int = 3
    margin_mm: float = 10.0
    gap_mm: float = 4.0
    captions: bool = True
    title: str = ""
    dpi: int = 200

    @property
    def per_page(self) -> int:
        return self.rows * self.columns

    def page_count(self, count: int) -> int:
        self.validate()
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("Photo count must be a non-negative whole number.")
        return (count + self.per_page - 1) // self.per_page

    def page_mm(self) -> tuple[float, float]:
        if self.page_size not in PAGE_SIZES_MM:
            raise ValueError("Choose A4, A3, Letter, or Legal paper.")
        size = PAGE_SIZES_MM[self.page_size]
        return size[::-1] if self.orientation == "Landscape" else size

    def page_pixels(self, dpi: int | None = None) -> tuple[int, int]:
        self.validate()
        resolution = self.dpi if dpi is None else dpi
        _validate_dpi(resolution)
        return tuple(round(mm * resolution / 25.4) for mm in self.page_mm())

    def validate(self) -> None:
        if self.page_size not in PAGE_SIZES_MM:
            raise ValueError("Choose A4, A3, Letter, or Legal paper.")
        if self.orientation not in {"Portrait", "Landscape"}:
            raise ValueError("Orientation must be Portrait or Landscape.")
        for name, number in (("Rows", self.rows), ("Columns", self.columns)):
            if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 20:
                raise ValueError(f"{name} must be a whole number between 1 and 20.")
        for name, number in (("Margin", self.margin_mm), ("Gap", self.gap_mm)):
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not 0 <= number <= 100:
                raise ValueError(f"{name} must be a finite number between 0 and 100 mm.")
        if not isinstance(self.captions, bool):
            raise ValueError("Captions must be enabled or disabled.")
        if not isinstance(self.title, str) or len(self.title) > 200:
            raise ValueError("Title must contain at most 200 characters.")
        if any(ord(char) < 32 for char in self.title):
            raise ValueError("Title must be a single line without control characters.")
        _validate_dpi(self.dpi)
        width, height = self.page_mm()
        header = 12.0 if self.title.strip() else 0.0
        footer = 8.0
        tile_w = (width - self.margin_mm * 2 - self.gap_mm * (self.columns - 1)) / self.columns
        tile_h = (height - self.margin_mm * 2 - header - footer - self.gap_mm * (self.rows - 1)) / self.rows
        image_h = tile_h - (CAPTION_HEIGHT_MM if self.captions else 0.0)
        if tile_w < 8 or image_h < 8:
            raise ValueError("This grid leaves too little room for photos. Reduce rows, columns, margins, or spacing.")


@dataclass(frozen=True)
class Photo:
    path: Path
    width: int
    height: int
    thumbnail: bytes
    _fingerprint: str | None = field(default=None, repr=False, compare=False)


def _natural_key(path: Path) -> tuple:
    return tuple((1, int(part)) if part.isdecimal() else (0, part.casefold())
                 for part in re.split(r"(\d+)", str(path)))


class CollectedPaths(list):
    """Supported paths plus unique unsupported files skipped during collection."""

    def __init__(self, paths, unsupported_paths=()):
        super().__init__(paths)
        self.unsupported_paths = tuple(unsupported_paths)


def collect_paths(paths: Iterable[Path], recursive: bool = False,
                  cancel: threading.Event | None = None) -> list[Path]:
    """Expand folders naturally, preserve explicitly selected order, deduplicate."""
    result: list[Path] = []
    unsupported: list[Path] = []
    seen: set[str] = set()
    unsupported_seen: set[str] = set()
    for item in paths:
        _check_cancel(cancel)
        path = Path(item).expanduser()
        if not path.exists():
            raise ValueError(f"Not found: {path}")
        if path.is_dir():
            candidates = path.rglob("*") if recursive else path.iterdir()
            found = []
            for child in candidates:
                _check_cancel(cancel)
                if child.is_file():
                    found.append(child)
            candidates = sorted(found, key=lambda p: (_natural_key(p.relative_to(path)), str(p)))
        elif path.is_file():
            candidates = [path]
        else:
            raise ValueError(f"Not a regular file or folder: {path}")
        for candidate in candidates:
            _check_cancel(cancel)
            if candidate.suffix.casefold() not in SUPPORTED_EXTENSIONS:
                # Unsupported sidecars may vanish or become unreadable while
                # enumerating a folder. Counting a skip must not discard photos.
                try:
                    resolved = candidate.resolve(strict=False)
                except (OSError, RuntimeError):
                    resolved = candidate.absolute()
                key = os.path.normcase(str(resolved))
                if key not in unsupported_seen:
                    unsupported_seen.add(key)
                    unsupported.append(resolved)
                continue
            resolved = candidate.resolve(strict=True)
            key = os.path.normcase(str(resolved))
            if key not in seen:
                seen.add(key)
                result.append(resolved)
    return CollectedPaths(result, unsupported)


def _stat_signature(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _hash_stream(stream, cancel=None) -> str:
    digest = hashlib.sha256()
    while True:
        _check_cancel(cancel)
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def _srgb_on_white(image: Image.Image) -> Image.Image:
    """Honor embedded color profiles before flattening transparency onto paper."""
    color = image
    alpha = None
    rgb = None
    try:
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            with image.convert("RGBA") as rgba:
                alpha = rgba.getchannel("A")
        if image.mode not in {"RGB", "CMYK", "LAB", "L"}:
            color = image.convert("L" if image.mode == "LA" else "RGB")
        profile = image.info.get("icc_profile")
        if profile is None:
            rgb = color.convert("RGB")
        else:
            try:
                rgb = ImageCms.profileToProfile(
                    color, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                    ImageCms.createProfile("sRGB"), outputMode="RGB",
                )
            except (ImageCms.PyCMSError, OSError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Invalid or unsupported color profile. Export this photo as sRGB and add it again."
                ) from exc
        if alpha is not None:
            paper = Image.new("RGB", rgb.size, "white")
            try:
                paper.paste(rgb, mask=alpha)
                return paper
            except BaseException:
                paper.close()
                raise
        # The page/thumbnail needs only sRGB pixels, never source EXIF/GPS metadata.
        rgb.info.clear()
        result, rgb = rgb, None
        return result
    finally:
        if color is not image:
            color.close()
        if alpha is not None:
            alpha.close()
        if rgb is not None:
            rgb.close()


def _load_photo(path: Path, target: tuple[int, int], expected: str | None = None,
                cancel=None) -> tuple[Image.Image, tuple[int, int], str]:
    """Decode one source, using JPEG decoder downsampling before allocation."""
    _check_cancel(cancel)
    try:
        with Path(path).open("rb") as stream, warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            before = _stat_signature(os.fstat(stream.fileno()))
            if not stat.S_ISREG(before[2]):
                raise ValueError("Not a regular image file.")
            fingerprint = _hash_stream(stream, cancel)
            if expected is not None and fingerprint != expected:
                raise ValueError("This photo changed since it was added. Remove it and add it again.")
            with Image.open(stream) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ValueError("Only JPEG and PNG image content is supported.")
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image exceeds the 60-million-pixel safety limit.")
                # PNG verify must run before metadata access can load the image.
                if image.format == "PNG":
                    image.verify()
                    stream.seek(0)
                    image = Image.open(stream)
                orientation = image.getexif().get(274, 1)
                dimensions = (height, width) if orientation in {5, 6, 7, 8} else (width, height)
                draft_target = target[::-1] if orientation in {5, 6, 7, 8} else target
                image.draft("RGB", draft_target)
                image.load()
                oriented = ImageOps.exif_transpose(image)
                try:
                    oriented.thumbnail(target, Image.Resampling.LANCZOS)
                    rgb = _srgb_on_white(oriented)
                finally:
                    oriented.close()
                if _stat_signature(os.fstat(stream.fileno())) != before:
                    rgb.close()
                    raise ValueError("This photo changed while being read. Try adding it again.")
                image.close()
        if cancel is not None and cancel.is_set():
            rgb.close()
            _check_cancel(cancel)
        return rgb, dimensions, fingerprint
    except ExportCancelled:
        raise
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError(f"Cannot read {Path(path).name}: {exc}") from exc


def inspect_photo(path: Path, cancel: threading.Event | None = None) -> Photo:
    path = Path(path).expanduser().resolve(strict=True)
    _check_cancel(cancel)
    image, dimensions, fingerprint = _load_photo(path, (128, 128), cancel=cancel)
    try:
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return Photo(path, dimensions[0], dimensions[1], buffer.getvalue(), fingerprint)
    finally:
        image.close()


@lru_cache(maxsize=48)
def _font(size: int, unicode_wide: bool = False):
    base = Path(__file__).resolve().parent
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    wide = [windows / "msyh.ttc", windows / "msgothic.ttc",
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc")]
    candidates = ([*wide] if unicode_wide else []) + [
        base / "assets" / "DejaVuSans.ttf", windows / "segoeui.ttf", windows / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"), *wide]
    for candidate in candidates:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                pass
    return ImageFont.load_default(size=size)


def _text_font(text: str, size: int):
    return _font(size, any(ord(char) >= 0x2E80 for char in text))


def _clean_text(text: str) -> str:
    return "".join(" " if ord(char) < 32 else char for char in text)


def _ellipsize(text: str, font, width: int) -> str:
    """Middle ellipsis keeps both the recognizable stem and extension."""
    if font.getlength(text) <= width:
        return text
    marker = "…"
    if font.getlength(marker) > width:
        return ""
    low, high = 0, len(text)
    best = marker
    while low <= high:
        keep = (low + high) // 2
        left, right = (keep + 1) // 2, keep // 2
        candidate = text[:left] + marker + (text[-right:] if right else "")
        if font.getlength(candidate) <= width:
            best, low = candidate, keep + 1
        else:
            high = keep - 1
    return best


def _draw_centered(draw, text: str, center_x: float, top: float, width: int,
                   size: int, fill: str = "#333333") -> None:
    font = _text_font(text, size)
    text = _ellipsize(_clean_text(text), font, width)
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((center_x - (box[2] - box[0]) / 2 - box[0], top - box[1]),
              text, font=font, fill=fill)


def _caption_width_mm(settings: SheetSettings) -> float:
    return (settings.page_mm()[0] - 2 * settings.margin_mm
            - (settings.columns - 1) * settings.gap_mm) / settings.columns


@lru_cache(maxsize=4096)
def _caption_lines(filename: str, width_mm: float) -> tuple[str, ...]:
    """Wrap without dropping characters, using the same metrics at every DPI."""
    text = _clean_text(filename)
    font = _text_font(text, CAPTION_SIZE)
    # Half a millimetre on each side keeps antialiased edges inside the cell.
    width = (width_mm - 1.0) * CAPTION_DPI / 25.4
    def fits(line):
        box = font.getbbox(line)
        return max(font.getlength(line), box[2] - box[0]) <= width
    def fits_band(lines):
        line_height = sum(font.getmetrics())
        limit = CAPTION_HEIGHT_MM * CAPTION_DPI / 25.4
        return all(CAPTION_DPI / 25.4 + index * line_height
                   + font.getbbox(line)[3] - font.getbbox(line)[1] <= limit
                   for index, line in enumerate(lines))
    if fits(text) and fits_band((text,)):
        return (text,)
    # Keep combining marks, variation selectors and joined sequences together.
    breaks = [i for i in range(1, len(text))
              if not unicodedata.category(text[i]).startswith("M")
              and text[i] != "\u200d" and text[i - 1] != "\u200d"]
    # Prefer a separator near the middle, then any balanced character break.
    breaks.sort(key=lambda i: (text[i - 1] not in " _-", abs(i - len(text) / 2)))
    for index in breaks:
        if fits(text[:index]) and fits(text[index:]) and fits_band((text[:index], text[index:])):
            return text[:index], text[index:]
    raise ValueError("The filename needs more than two caption lines.")


def validate_captions(photos: list[Photo], settings: SheetSettings,
                      cancel: threading.Event | None = None) -> None:
    """Preflight every filename before preview readiness or output staging."""
    settings.validate()
    if not settings.captions:
        return
    width_mm = _caption_width_mm(settings)
    for index, photo in enumerate(photos):
        _check_cancel(cancel)
        try:
            _caption_lines(photo.path.name, width_mm)
        except ValueError as exc:
            raise CaptionLayoutError(photo.path.name, index // settings.per_page + 1) from exc


def _draw_caption(page: Image.Image, filename: str, width_mm: float,
                  left: float, top: float, resolution: int) -> None:
    """Scale one reference rendering so wrapping and 8 pt sizing stay consistent."""
    lines = _caption_lines(filename, width_mm)
    font = _text_font(_clean_text(filename), CAPTION_SIZE)
    scale = CAPTION_DPI / 25.4
    band = Image.new("RGB", (max(1, round(width_mm * scale)),
                             round(CAPTION_HEIGHT_MM * scale)), "white")
    try:
        draw = ImageDraw.Draw(band)
        ascent, descent = font.getmetrics()
        line_height = ascent + descent
        y = round(scale)  # One millimetre between the photo and caption.
        for line in lines:
            box = draw.textbbox((0, 0), line, font=font)
            draw.text(((band.width - (box[2] - box[0])) / 2 - box[0], y - box[1]),
                      line, font=font, fill="#333333")
            y += line_height
        output = band.resize((max(1, round(width_mm * resolution / 25.4)),
                              max(1, round(CAPTION_HEIGHT_MM * resolution / 25.4))),
                             Image.Resampling.LANCZOS)
        try:
            page.paste(output, (round(left), round(top)))
        finally:
            output.close()
    finally:
        band.close()


def render_page(photos: list[Photo], settings: SheetSettings, page_index: int,
                dpi: int | None = None, cancel: threading.Event | None = None) -> Image.Image:
    settings.validate()
    resolution = settings.dpi if dpi is None else dpi
    width, height = settings.page_pixels(resolution)
    pages = settings.page_count(len(photos))
    if isinstance(page_index, bool) or not isinstance(page_index, int) or not 0 <= page_index < pages:
        raise ValueError("Page number is outside the available photos.")
    _check_cancel(cancel)
    page = Image.new("RGB", (width, height), "white")
    try:
        draw = ImageDraw.Draw(page)
        scale = resolution / 25.4
        margin, gap = settings.margin_mm * scale, settings.gap_mm * scale
        header, footer = (12.0 * scale if settings.title.strip() else 0), 8.0 * scale
        caption_h = CAPTION_HEIGHT_MM * scale if settings.captions else 0
        tile_w = _caption_width_mm(settings) * scale
        tile_h = (settings.page_mm()[1] * scale - 2 * margin - header - footer
                  - (settings.rows - 1) * gap) / settings.rows
        image_h = tile_h - caption_h
        if settings.title.strip():
            _draw_centered(draw, settings.title.strip(), width / 2, margin,
                           round(width - 2 * margin), round(14 * resolution / 72))
        first = page_index * settings.per_page
        for offset, photo in enumerate(photos[first:first + settings.per_page]):
            _check_cancel(cancel)
            if settings.captions:
                try:
                    _caption_lines(photo.path.name, _caption_width_mm(settings))
                except ValueError as exc:
                    raise CaptionLayoutError(photo.path.name, page_index + 1) from exc
            row, column = divmod(offset, settings.columns)
            left, top = margin + column * (tile_w + gap), margin + header + row * (tile_h + gap)
            image, dimensions, _ = _load_photo(photo.path, (max(1, math.floor(tile_w)), max(1, math.floor(image_h))),
                                               photo._fingerprint, cancel)
            try:
                if dimensions != (photo.width, photo.height):
                    raise ValueError(f"{photo.path.name} changed dimensions since it was added. Add it again.")
                # Fit small sources as well as large ones. Keeping source pixels at
                # 1:1 would give a different physical size at preview/export DPI.
                fit = min(tile_w / dimensions[0], image_h / dimensions[1])
                fit_size = (max(1, min(math.floor(tile_w), round(dimensions[0] * fit))),
                            max(1, min(math.floor(image_h), round(dimensions[1] * fit))))
                if image.size != fit_size:
                    fitted = image.resize(fit_size, Image.Resampling.LANCZOS)
                    image.close()
                    image = fitted
                page.paste(image, (round(left + (tile_w - image.width) / 2),
                                   round(top + (image_h - image.height) / 2)))
            finally:
                image.close()
            if settings.captions:
                _draw_caption(page, photo.path.name, _caption_width_mm(settings),
                              left, top + image_h, resolution)
        _draw_centered(draw, f"Page {page_index + 1} of {pages}", width / 2,
                       height - margin - 4.5 * scale, round(width - 2 * margin),
                       max(8, round(8 * resolution / 72)), "#666666")
        _check_cancel(cancel)
        return page
    except BaseException:
        page.close()
        raise


def _validate_stem(stem: str) -> None:
    if (not isinstance(stem, str) or not stem or len(stem) > 120
            or stem != stem.strip() or stem.endswith(".")
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', stem)):
        raise ValueError("Use a filename of 1–120 characters without path separators, reserved symbols, or trailing spaces/dots.")
    device = stem.split(".", 1)[0].upper()
    if device in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} or re.fullmatch(r"(?:COM|LPT)[0-9¹²³]", device):
        raise ValueError("That filename is reserved on Windows. Choose another name.")


def output_paths(count: int, settings: SheetSettings, destination: Path,
                 stem: str = "contact-sheet", format: str = "PDF") -> list[Path]:
    settings.validate()
    _validate_stem(stem)
    if not isinstance(format, str) or format.upper() not in {"PDF", "JPEG"}:
        raise ValueError("Export format must be PDF or JPEG.")
    pages = settings.page_count(count)
    if not pages:
        raise ValueError("Add at least one photo before exporting.")
    destination = Path(destination).expanduser()
    if format.upper() == "PDF":
        return [destination / f"{stem}.pdf"]
    return [destination / f"{stem}-{number:03d}.jpg" for number in range(1, pages + 1)]



def available_output_stem(count: int, settings: SheetSettings, destination: Path,
                          stem: str = "contact-sheet", format: str = "PDF") -> str:
    """Find one unused name for the whole batch; export still installs exclusively.

    This is a suggestion, not a reservation. A file arriving later must cause the
    normal non-overwrite export to fail safely rather than silently replacing it.
    """
    candidate = stem
    paths = output_paths(count, settings, destination, candidate, format)
    occupied_jpeg_stems = set()
    if format.upper() == "JPEG":
        # Older batches can have more pages than this one. Do not mix the new
        # batch with their trailing sheets, even when page 001 no longer exists.
        for path in Path(destination).expanduser().iterdir():
            match = re.fullmatch(r"(.+)-[0-9]{3,}\.jpg", os.path.normcase(path.name))
            if match:
                occupied_jpeg_stems.add(match.group(1))
    number = 1
    for _ in range(100):
        if (os.path.normcase(candidate) not in occupied_jpeg_stems
                and not any(path.exists() or path.is_symlink() for path in paths)):
            return candidate
        number += 1
        suffix = f" ({number})"
        candidate = stem[:120 - len(suffix)].rstrip(" .") + suffix
        paths = output_paths(count, settings, destination, candidate, format)
    raise ValueError("No unused batch name found. Choose another filename or folder.")


def _snapshot(path: Path) -> tuple[int, ...] | None:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(value.st_mode):
        raise ValueError(f"Output must be a regular file, not a folder or shortcut: {path.name}")
    return _stat_signature(value)


def _protect_sources(photos: list[Photo], outputs: list[Path]) -> None:
    source_names = {os.path.normcase(str(Path(photo.path).resolve())) for photo in photos}
    source_ids = set()
    for photo in photos:
        value = Path(photo.path).stat()
        source_ids.add((value.st_dev, value.st_ino))
    for path in outputs:
        if os.path.normcase(str(path.resolve())) in source_names:
            raise ValueError(f"An export cannot replace an original photo: {path.name}")
        if path.exists():
            value = path.stat()
            if (value.st_dev, value.st_ino) in source_ids:
                raise ValueError(f"An export cannot replace an original photo or hardlink: {path.name}")


def _verify_sources(photos: list[Photo], cancel) -> None:
    """Catch edits to earlier pages while later pages were being rendered."""
    checked: set[tuple[Path, str | None]] = set()
    for photo in photos:
        key = (photo.path, photo._fingerprint)
        if key in checked:
            continue
        checked.add(key)
        _check_cancel(cancel)
        try:
            with Path(photo.path).open("rb") as stream:
                before = _stat_signature(os.fstat(stream.fileno()))
                fingerprint = _hash_stream(stream, cancel)
                if (photo._fingerprint is not None and fingerprint != photo._fingerprint
                        or _stat_signature(os.fstat(stream.fileno())) != before):
                    raise ValueError("This photo changed during export. Add it again.")
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot read {Path(photo.path).name}: {exc}") from exc


def _remove_if_ours(path: Path, signature: tuple[int, ...]) -> bool:
    """Never remove a replacement placed at the same path by another process."""
    current = _snapshot(path)
    if current is None:
        return True
    if current[:5] == signature[:5]:
        path.unlink()
        return True
    return False


def _install_exclusive(source: Path, target: Path, cancel=None) -> tuple[int, ...]:
    """Install without replacing any existing path, including on removable media.

    Windows rename and POSIX hardlinks make the completed file visible atomically.
    Unsupported POSIX filesystems use exclusive creation and a bounded copy. That
    fallback is briefly visible while copying; cancellation/errors remove our file.
    No multi-file export can promise rollback after process or power failure.
    """
    _check_cancel(cancel)
    signature = _snapshot(source)
    if _WINDOWS:
        # Unlike POSIX rename, Windows rename refuses an existing destination.
        os.rename(source, target)
        return signature
    try:
        os.link(source, target)
        return signature
    except OSError as exc:
        unsupported = {errno.EPERM, errno.EOPNOTSUPP, errno.ENOSYS, errno.EXDEV}
        if exc.errno not in unsupported:
            raise
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    created = _stat_signature(os.fstat(descriptor))
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
            while True:
                _check_cancel(cancel)
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
            _check_cancel(cancel)
            return _stat_signature(os.fstat(output.fileno()))
    except BaseException as exc:
        # The size/mtime change during copying; inode identity identifies our file.
        try:
            current = _snapshot(target)
            if current is not None and current[:2] == created[:2]:
                target.unlink()
            elif current is not None:
                raise OSError("Another process replaced the incomplete output.")
        except (OSError, ValueError) as cleanup_error:
            raise RuntimeError(f"Export stopped, but an incomplete or externally changed file remains at {target}. It could not be safely removed: {cleanup_error}") from exc
        raise


def _commit_outputs(staged: list[Path], outputs: list[Path], snapshots: list,
                    photos: list[Photo], cancel) -> list[Path]:
    """Exclusive installation avoids racing another file into oblivion."""
    _check_cancel(cancel)
    _protect_sources(photos, outputs)
    for target, original in zip(outputs, snapshots):
        if _snapshot(target) != original:
            raise FileExistsError(f"Output changed during export: {target.name}. Nothing was replaced.")
    installed: list[tuple[Path, tuple[int, ...]]] = []
    backups: list[tuple[Path, Path]] = []
    try:
        for index, (source, target, original) in enumerate(zip(staged, outputs, snapshots)):
            _check_cancel(cancel)
            if _snapshot(target) != original:
                raise FileExistsError(f"Output changed during export: {target.name}.")
            if original is not None:
                backup = source.parent / f"backup-{index}"
                os.replace(target, backup)
                backups.append((backup, target))
                if _snapshot(backup)[:5] != original[:5]:
                    raise FileExistsError(f"Output changed during export: {target.name}.")
            signature = _install_exclusive(source, target, cancel)
            installed.append((target, signature))
        _check_cancel(cancel)
    except BaseException as exc:
        recovery_failures = []
        for target, signature in reversed(installed):
            try:
                if not _remove_if_ours(target, signature):
                    recovery_failures.append(target)
            except (OSError, ValueError):
                recovery_failures.append(target)
        for backup, target in reversed(backups):
            try:
                _install_exclusive(backup, target)
                backup.unlink(missing_ok=True)
            except (OSError, ValueError):
                recovery_failures.append(target)
        if recovery_failures:
            message = "Export stopped, but some files could not be safely rolled back. Check: " + ", ".join(str(path) for path in dict.fromkeys(recovery_failures))
            if any(staged[0].parent.glob("backup-*")):
                message += f". Original backups are preserved in {staged[0].parent}"
            raise RuntimeError(message) from exc
        raise
    retained = []
    for backup, _ in backups:
        try:
            backup.unlink()
        except OSError:
            # Installation succeeded. Report cleanup separately so callers do
            # not retry a completed export or claim that nothing was saved.
            retained.append(backup)
    return retained


class ExportedPaths(list):
    """Successful output paths plus any previous-sheet backups left for cleanup."""

    def __init__(self, paths, retained_backups=()):
        super().__init__(paths)
        self.retained_backups = tuple(retained_backups)


def export_sheets(photos: list[Photo], settings: SheetSettings, destination: Path,
                  stem: str = "contact-sheet", format: str = "PDF", overwrite: bool = False,
                  cancel: threading.Event | None = None,
                  progress: Callable[[int, int], None] | None = None,
                  phase: Callable[[str], None] | None = None) -> list[Path]:
    """Render all pages before committing; preserve originals and existing exports."""
    settings.validate()
    if not isinstance(overwrite, bool):
        raise ValueError("Overwrite must be explicitly enabled or disabled.")
    _check_cancel(cancel)
    destination = Path(destination).expanduser().resolve(strict=True)
    if not destination.is_dir():
        raise ValueError("Choose an existing destination folder.")
    photos = list(photos)
    outputs = output_paths(len(photos), settings, destination, stem, format)
    validate_captions(photos, settings, cancel)
    _protect_sources(photos, outputs)
    snapshots = [_snapshot(path) for path in outputs]
    conflicts = [path.name for path, snapshot in zip(outputs, snapshots) if snapshot is not None]
    if conflicts and not overwrite:
        raise FileExistsError("Output already exists: " + ", ".join(conflicts))
    stage_dir = Path(tempfile.mkdtemp(prefix=".contact-sheet-", dir=destination))
    staged = [stage_dir / path.name for path in outputs]
    total = settings.page_count(len(photos))
    try:
        if phase:
            phase("rendering")
        if format.upper() == "PDF":
            from reportlab.pdfgen import canvas
            width_mm, height_mm = settings.page_mm()
            page_points = (width_mm * 72 / 25.4, height_mm * 72 / 25.4)
            document = canvas.Canvas(str(staged[0]), pagesize=page_points, pageCompression=1)
            document.setTitle(settings.title.strip() or stem)
            document.setCreator("Contact Sheet Maker")
            for page_index in range(total):
                _check_cancel(cancel)
                page = render_page(photos, settings, page_index, cancel=cancel)
                try:
                    # Inline images avoid retaining each page's decoded pixels in the PDF cache.
                    document.drawInlineImage(page, 0, 0, width=page_points[0], height=page_points[1])
                    document.showPage()
                finally:
                    page.close()
                if progress:
                    progress(page_index + 1, total)
            _check_cancel(cancel)
            document.save()
        else:
            for page_index, path in enumerate(staged):
                _check_cancel(cancel)
                page = render_page(photos, settings, page_index, cancel=cancel)
                try:
                    page.save(path, "JPEG", quality=95, subsampling=0,
                              dpi=(settings.dpi, settings.dpi), optimize=True)
                finally:
                    page.close()
                if progress:
                    progress(page_index + 1, total)
        _check_cancel(cancel)
        if phase:
            phase("checking")
        _verify_sources(photos, cancel)
        if phase:
            phase("committing")
        retained = _commit_outputs(staged, outputs, snapshots, photos, cancel)
        return ExportedPaths(outputs, retained)
    finally:
        # Retain any irreplaceable rollback backup, otherwise remove all staging files.
        if not any(stage_dir.glob("backup-*")):
            shutil.rmtree(stage_dir, ignore_errors=True)
