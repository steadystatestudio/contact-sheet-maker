# Source provenance and third-party notices

Private development project, 2026-10-06. No public release workflow is enabled.

## Steady State Studio design and adapted code

The current sources, READMEs, MIT licenses, and actual repository screenshots were inspected before implementation. Both repositories are copyright © 2026 Steady State Studio and MIT-licensed; the full MIT notice is retained in `LICENSE`.

- File Renamer, commit `342f2cebf672578ff27f299eda466da7c2df4b96`: https://github.com/steadystatestudio/file-renamer/tree/342f2cebf672578ff27f299eda466da7c2df4b96
  - `src/file_renamer/themes.py`, blob `df4830306f38a6dbe65de23f4135fcc1d9ce1722`: adapted as `src/contact_sheet/themes.py`. Changes add double-spin styling, explicit arrow assets and progress-chunk styling.
  - `src/file_renamer/gui.py`, blob `261c2f6ad204da6aee60aeb4534289c2dd9b906c`: its `FileProgressBar` class is retained in `src/contact_sheet/widgets.py`; toolbar order, panel margins, focus treatments, resizable work area and centered primary action informed the new UI.
  - Design history inspected separately: commits `3ee31d91f87cd4f61a9eb86ea1dd6a18c750ab7f`, `befbdf3a3a274a919cffcaf3987536c2a1e0e0f3`, `4f330d22e5c3cfe36914c5dc85a9153c8879622b`, `a2a8c6d83f08f207f073b5a0d3b0e264d50ca759`, and `35f299d7a511d6637a63af1eb30e2b10325c7157`. Applied lessons include visible labels, accessible controls, preview readiness, retained operation outcomes, stable settings identity and nonintrusive row presentation.
- File Renamer `scripts/build.py` and `scripts/fetch_appimagetool.py` informed the native ZIP/AppDir layout and verified-download helper. Both are adapted under the same retained MIT license; runtime pinning, source/build manifests and tests were added for this project.
- Square Photo Padder, commit `2e6bcd925876e4ad8ff5a486f3fe21f44431bc00`: https://github.com/steadystatestudio/square-photo-padder/tree/2e6bcd925876e4ad8ff5a486f3fe21f44431bc00
  - Inspected `gui.py`, `themes.py`, `icons.py`, `settings.py`, README, license and screenshot. No image-processing code or branded icon was copied.

The contact-sheet engine, new UI behavior, contact-sheet SVG app/arrow icons, tests, and generated landscape sample illustrations were created for this project. No external stock photographs are included. Adobe Bridge documentation was considered only as a functional benchmark, not as a visual/source template.

## Runtime and build dependencies

- Python: PSF license. https://www.python.org/psf/license/
- PySide6 / Shiboken6 / Qt: LGPL-3.0-only alternative used by this development build. Dynamic libraries remain separate in a one-folder bundle and may be replaced with compatible modified libraries. No application restriction is imposed on debugging modifications to these libraries. LGPLv3 and GPLv3 texts are included under `packaging/licenses`.
  - Licensing details: https://doc.qt.io/qtforpython-6/licenses.html
  - PySide source: https://code.qt.io/cgit/pyside/pyside-setup.git/
  - Qt source: https://code.qt.io/cgit/qt/qtbase.git/ and https://code.qt.io/cgit/qt/qtsvg.git/
  - Match the version listed in `requirements-build-lock.txt`; acquire matching upstream source and retain all applicable bundled third-party notices before any public redistribution.
- Pillow: MIT-CMU license, with additional bundled component notices. https://github.com/python-pillow/Pillow
- ReportLab: BSD-style license. https://www.reportlab.com/
- PyInstaller: GPLv2-or-later with bootloader distribution exception. https://pyinstaller.org/
- DejaVu Sans: Bitstream Vera/DejaVu license, retained in `packaging/DEJAVU_FONT_LICENSE.txt`; font included for reliable caption rendering. CJK/emoji coverage depends on suitable installed fonts; Unicode filesystem paths do not depend on font coverage.

The build script copies available dependency license files into the portable bundle. This is a private test build, not a claim that public distribution obligations or all target-platform behavior have been independently audited.

## AppImage runtime

The Linux AppImage embeds the fixed type2-runtime release 20251108. Its MIT notice and linked musl/libfuse/squashfuse/zstd/zlib terms are retained in `packaging/linux/APPIMAGE_RUNTIME_LICENSE.txt` and in the packaged notices. Source: https://github.com/AppImage/type2-runtime/tree/dd6cebedcbddde9c82f89b011e8e1d40b6e43868 . Tool and runtime SHA-256/size pins are verified by `scripts/fetch_appimagetool.py`; this is not a public-distribution compliance audit.
