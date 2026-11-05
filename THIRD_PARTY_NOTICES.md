# Source provenance and third-party notices

Contact Sheet Maker. Application source is MIT-licensed. The manual
release workflow stages a draft candidate; publishing remains a separate review.

## Steady State Studio design and adapted code

Contact Sheet Maker includes code adapted from Steady State Studio's MIT-licensed File Renamer. Copyright (c) 2026 Steady State Studio; the complete MIT notice is retained in `LICENSE`.

- `src/contact_sheet/themes.py` adapts the File Renamer theme, with additional control, arrow and progress styling.
- `src/contact_sheet/widgets.py` retains the File Renamer `FileProgressBar` component.
- The native packaging layout and verified AppImage-input helper adapt Studio packaging code.
- Source project: https://github.com/steadystatestudio/file-renamer-releases .

The contact-sheet engine, application-specific controls, SVG icons and synthetic sample illustrations are maintained as part of this project. No external stock photographs are packaged.

## Runtime and build dependencies

Test-only ICC fixtures in `tests/fixtures/icc` come from saucecontrol/Compact-ICC-Profiles
at commit `bdd84663061bc4ae95ca70decff54f581e27f702`, under CC0-1.0. Their license,
source URL and SHA-256 digests are retained beside the files. They are used with
synthetic images to verify CMYK, wide-gamut RGB and grayscale conversion; they are
not application defaults or packaged runtime assets.

- Python: PSF license. https://www.python.org/psf/license/
- PySide6 / Shiboken6 / Qt 6.12.0: LGPL-3.0-only alternative used by this build. Dynamic libraries remain separate in a one-folder bundle and may be replaced with compatible modified libraries. No application restriction is imposed on reverse engineering for debugging modifications to these libraries. LGPLv3 and GPLv3 texts are included under `packaging/licenses`.
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
The locked PySide6 metapackage also installs the separately versioned
PySide6_Pdf and PySide6_WebEngine 6.12.0.140 build dependencies. Their modules
and libraries are not distributed by this application.
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
