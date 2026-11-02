"""Bounded, independent verification of an actual packaged executable."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image
from pypdf import PdfReader


def verify_pdf(path: Path, *, page_count: int, paper_mm: tuple[float, float],
               dpi: int, rows: int, columns: int, margin: float, gap: float,
               captions: bool, colors: list[tuple[int, int, int]]) -> dict:
    """Parse every image stream strictly, then render with a separate PDF engine."""
    pdf = PdfReader(path, strict=True)
    if len(pdf.pages) != page_count:
        raise RuntimeError('Packaged PDF has the wrong page count')
    expected_size = tuple(round(mm * dpi / 25.4) for mm in paper_mm)

    def check_pixels(image, page_index, resolution):
        cell_width = (paper_mm[0] - 2 * margin - (columns - 1) * gap) / columns
        cell_height = (paper_mm[1] - 2 * margin - 8 - (rows - 1) * gap) / rows
        picture_height = cell_height - (9 if captions else 0)
        scale = resolution / 25.4
        with image.convert('RGB') as rgb:
            for offset, wanted in enumerate(colors[page_index * rows * columns:(page_index + 1) * rows * columns]):
                row, column = divmod(offset, columns)
                xy = (round((margin + column * (cell_width + gap) + cell_width / 2) * scale),
                      round((margin + row * (cell_height + gap) + picture_height / 2) * scale))
                actual = rgb.getpixel(xy)
                if max(abs(a - b) for a, b in zip(actual, wanted)) > 8:
                    raise RuntimeError('Packaged PDF photo colors/order do not match the inputs')

    for index, page in enumerate(pdf.pages):
        if any(abs(actual - mm * 72 / 25.4) > .02 for actual, mm in
               zip((float(page.mediabox.width), float(page.mediabox.height)), paper_mm)):
            raise RuntimeError('Packaged PDF has the wrong paper dimensions')
        if not page.get_contents().operations or len(page.images) != 1:
            raise RuntimeError('Packaged PDF image stream is unreadable')
        with page.images[0].image as image:
            if image.size != expected_size:
                raise RuntimeError('Packaged PDF raster has the wrong dimensions')
            check_pixels(image, index, dpi)
    poppler = shutil.which('pdftoppm')
    if not poppler and sys.platform.startswith('linux'):
        raise RuntimeError('Linux PDF verification requires independent Poppler rendering')
    rendered = 0
    if poppler:
        directory = path.parent.parent / 'independent-render'
        directory.mkdir(exist_ok=True)
        prefix = directory / path.stem
        process = subprocess.run([poppler, '-r', '150', '-png', str(path), str(prefix)],
                                 capture_output=True, text=True, timeout=60)
        if process.returncode or process.stderr.strip():
            raise RuntimeError(f'Independent PDF rendering failed: {process.stderr}')
        images = sorted(directory.glob(path.stem + '-*.png'))
        if len(images) != page_count:
            raise RuntimeError('Independent PDF renderer produced the wrong page count')
        for index, rendered_path in enumerate(images):
            with Image.open(rendered_path) as image:
                expected = tuple(mm * 150 / 25.4 for mm in paper_mm)
                if any(abs(actual - wanted) > 1 for actual, wanted in zip(image.size, expected)):
                    raise RuntimeError('Independent PDF render has the wrong paper dimensions')
                check_pixels(image, index, 150)
            rendered += 1
    return {'strict_pages_decoded': page_count, 'poppler_pages_rendered': rendered,
            'poppler_available': bool(poppler)}


def verify_output(directory: Path) -> dict:
    result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
    if not result.get('ok') or result.get('photos') != 13 or result.get('pages') != 2:
        raise RuntimeError(f'Unexpected bundle smoke result: {result}')
    inputs = sorted((directory / 'inputs').glob('*.png'))
    if len(inputs) != 13 or not all('café' in path.name for path in inputs):
        raise RuntimeError('Packaged Unicode input test was incomplete')
    before = result['input_hashes_before']
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    if before != after or not result.get('originals_unchanged'):
        raise RuntimeError('Packaged export modified an input')
    for path in inputs:
        with Image.open(path) as image:
            if not image.info.get('icc_profile'):
                raise RuntimeError('Packaged color-profile import test was incomplete')
    pdf_checks = {'standard': verify_pdf(directory / 'outputs/smoke.pdf',
        page_count=2, paper_mm=(210, 297), dpi=200, rows=4, columns=3,
        margin=10, gap=4, captions=True, colors=[(40 + i * 12, 110, 160) for i in range(13)])}
    strict_inputs = sorted((directory / 'strict-inputs').glob('*.png'))
    if (len(strict_inputs) != 13 or result.get('strict_pages') != 3
            or result.get('strict_input_hashes_before') !=
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in strict_inputs}):
        raise RuntimeError('Packaged strict-PDF test modified or omitted an input')
    pdf_checks['letter_boundary'] = verify_pdf(directory / 'outputs/strict-letter.pdf',
        page_count=3, paper_mm=(215.9, 279.4), dpi=150, rows=2, columns=3,
        margin=15, gap=6, captions=False, colors=[(230, 180, 30)] * 13)
    pages = sorted((directory / 'outputs').glob('*.jpg'))
    if [path.name for path in pages] != ['smoke-001.jpg', 'smoke-002.jpg']:
        raise RuntimeError('Packaged JPEG filenames/page count are wrong')
    for path in pages:
        with Image.open(path) as image:
            image.load()
            if image.size != (1654, 2339) or image.info.get('dpi') != (200, 200):
                raise RuntimeError('Packaged JPEG dimensions or print resolution are wrong')
            if image.getextrema() == ((255, 255),) * 3:
                raise RuntimeError('Packaged JPEG is blank')
    with Image.open(directory / 'ui.png') as screenshot:
        screenshot.verify()
    if list((directory / 'outputs').glob('.contact-sheet-*')):
        raise RuntimeError('Packaged export left staging files behind')
    result['independent_pdf_checks'] = pdf_checks
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    suffix = 'appimage' if executable.suffix == '.AppImage' else 'windows' if executable.suffix.lower() == '.exe' else 'linux'
    output = args.output_dir or Path('artifacts') / f'smoke-{suffix}'
    if output.exists():
        raise SystemExit(f'Refusing to replace existing smoke report: {output}')
    environment = dict(os.environ)
    environment['QT_QPA_PLATFORM'] = environment.get('CONTACT_SHEET_SMOKE_PLATFORM', 'offscreen')
    # Deliberately do not inherit PYTHONPATH: exercise the bundled application.
    environment.pop('PYTHONPATH', None)
    with tempfile.TemporaryDirectory(prefix='contact-sheet-bundle-') as temp:
        destination = Path(temp) / 'smoke-output'
        occupied = Path(temp) / 'occupied-qa'
        occupied.mkdir()
        sentinel = occupied / 'keep.txt'
        sentinel.write_text('unchanged', encoding='utf-8')
        refused = subprocess.run([str(executable), '--qa-ui', str(occupied)],
                                 capture_output=True, text=True, timeout=30,
                                 env=environment, cwd=temp,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if (refused.returncode == 0 or sentinel.read_text(encoding='utf-8') != 'unchanged'
                or set(p.name for p in occupied.iterdir()) != {'keep.txt'}):
            raise RuntimeError('Packaged interactive QA mode did not refuse an existing folder')
        completed = subprocess.run([str(executable), '--smoke-test', str(destination)],
                                   capture_output=True, text=True, timeout=args.timeout,
                                   env=environment, cwd=temp,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        output.mkdir(parents=True)
        (output / 'process.log').write_text(completed.stdout + '\n' + completed.stderr, encoding='utf-8')
        if completed.returncode:
            raise RuntimeError(f'Packaged executable exited {completed.returncode}; see {output / "process.log"}')
        result = verify_output(destination)
        result['executable_name'] = executable.name
        result['platform'] = sys.platform
        result['qt_platform'] = environment['QT_QPA_PLATFORM']
        result['qa_ui_existing_folder_refused'] = True
        (output / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        for screenshot in destination.glob('ui*.png'):
            shutil.copy2(screenshot, output / screenshot.name)
        shutil.copytree(destination / 'outputs', output / 'outputs')
        if (destination / 'independent-render').exists():
            shutil.copytree(destination / 'independent-render', output / 'independent-render')
    print(f'Packaged smoke passed: {executable.name}; report: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
