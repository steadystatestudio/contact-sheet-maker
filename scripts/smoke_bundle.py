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
    pdf = PdfReader(directory / 'outputs/smoke.pdf')
    if len(pdf.pages) != 2:
        raise RuntimeError('Packaged PDF has the wrong page count')
    for page in pdf.pages:
        if abs(float(page.mediabox.width) - 595.2756) > .01 or abs(float(page.mediabox.height) - 841.8898) > .01:
            raise RuntimeError('Packaged PDF does not use A4 page dimensions')
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
        (output / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        for screenshot in destination.glob('ui*.png'):
            shutil.copy2(screenshot, output / screenshot.name)
        shutil.copytree(destination / 'outputs', output / 'outputs')
    print(f'Packaged smoke passed: {executable.name}; report: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
