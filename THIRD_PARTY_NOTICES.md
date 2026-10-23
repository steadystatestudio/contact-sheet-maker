# Source provenance and third-party notices

Contact Sheet Maker public beta. Application source is MIT-licensed. The manual
release workflow stages a draft prerelease; publishing remains a separate review.

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
- PySide6 / Shiboken6 / Qt 6.11.2: LGPL-3.0-only alternative used by this build. Dynamic libraries remain separate in a one-folder bundle and may be replaced with compatible modified libraries. No application restriction is imposed on reverse engineering for debugging modifications to these libraries. LGPLv3 and GPLv3 texts are included under `packaging/licenses`.
  - Licensing details: https://doc.qt.io/qtforpython-6/licenses.html
  - PySide source: https://code.qt.io/cgit/pyside/pyside-setup.git/
  - Qt source: https://code.qt.io/cgit/qt/qtbase.git/ and https://code.qt.io/cgit/qt/qtsvg.git/
  - The complete matching Qt and pyside-setup source archives (including Shiboken and build scripts) are required assets on the same GitHub release as the packages. Exact official URLs, sizes and SHA-256 hashes are in `packaging/source-archives.json`, copied into each bundle as `SOURCE-INDEX.json`. The release gate checks the installed Qt and binding versions against these pins. No Studio patches are applied to Qt/PySide/Shiboken.
  - See the bundled `LIBRARY-REPLACEMENT.txt` for practical replacement/rebuild instructions. Qt's upstream guidance: https://www.qt.io/development/open-source-lgpl-obligations . These instructions and retained evidence are not a general legal certification.
- Pillow: MIT-CMU license, with additional bundled component notices. https://github.com/python-pillow/Pillow
- ReportLab: BSD-style license. https://www.reportlab.com/
- PyInstaller: GPLv2-or-later with bootloader distribution exception. https://pyinstaller.org/
- DejaVu Sans: Bitstream Vera/DejaVu license, retained in `packaging/DEJAVU_FONT_LICENSE.txt`; font included for reliable caption rendering. CJK/emoji coverage depends on suitable installed fonts; Unicode filesystem paths do not depend on font coverage.

The build script retains dependency license, copyright and notice files in the
portable bundle and records their paths and hashes in `LICENSE-INDEX.json`.
`NATIVE-LIBRARIES.json` inventories the separately replaceable binaries.
`BUILD-INFO.json` records exact package/runtime versions, source commit and source
hashes. The official source archives preserve their own complete third-party
notices. Keep these notices and source assets available when redistributing.
`licenses/QT-THIRD-PARTY-NOTICES.txt` also retains the attribution and license
texts from the matching Qt base, SVG, image-format and Wayland source modules;
its preamble records the checksum-verified official source archives. It is an
intentionally broader notice set than the linked binary subset, not a claim
that every optional Qt component is used by this application.
Packaging excludes the unused Qt PDF, Virtual Keyboard, QML/Quick, WebEngine,
networking and optional Mesa software OpenGL components. The build rejects these
components if they reappear. Native desktop input methods and platform plugins
are retained, except the unused VNC remote-display plugin; PDF/JPEG generation
is provided by ReportLab/Pillow.

Linux packages use PyInstaller's supported `Analysis.exclude_system_libraries`
method to leave distribution-owned `/lib` and `/usr/lib` libraries on the host.
`LINUX-SYSTEM-DEPENDENCIES.json` records the actual omitted library names and
Ubuntu package owners without personal build paths. The package manager supplies
those libraries and their notices/source availability. The unused Python
readline module and GTK platform theme are excluded. Qt/PySide/Pillow wheel
libraries and Python remain bundled and are covered by the retained notices.

## AppImage runtime

The Linux AppImage embeds type2-runtime release 20251108, commit
`dd6cebedcbddde9c82f89b011e8e1d40b6e43868`. Its MIT notice and complete
musl/libfuse/squashfuse/zstd/zlib/mimalloc license texts are retained under
`packaging/licenses/appimage` and `packaging/linux/APPIMAGE_RUNTIME_LICENSE.txt`.
Source: https://github.com/AppImage/type2-runtime/tree/dd6cebedcbddde9c82f89b011e8e1d40b6e43868 .
The runtime source (including its libfuse patch), matching libfuse 3.15.0 and
squashfuse 0.5.2 sources are also retained release assets with exact source pins.
The runtime's upstream recipe uses Alpine 3.21 packages for its other static
libraries without recording exact package revisions; this is not a reproducible
build claim. Tool and runtime binary hashes remain verified by
`scripts/fetch_appimagetool.py`.
