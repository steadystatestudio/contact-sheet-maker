# Validation record

Build: Contact Sheet Maker 0.1.0, private development build, 2026-10-06.

## Passed on this environment

Debian 13 x86_64, Python 3.12.14, Qt/PySide6 6.11.2, Pillow 12.3.0, ReportLab 5.0.1. Isolated project virtual environment; Qt offscreen platform. No desktop or existing Studio repositories were modified.

- Final complete suite: **106 passed in 6.71 seconds**. JUnit details: `docs/test-results.xml`.
- Core: 85 tests. Natural order/deduplication; unusual Unicode numeric names; EXIF rotation; corruption/unsupported content; 60M-pixel limit; invalid layouts/names; full-image fitting; real PDF/JPEG counts/dimensions/DPI; source fingerprint changes; source/hardlink conflicts; existing-output refusal; cancellation; exclusive-install races; rollback/retained-backup reporting; unsupported-filesystem fallback and simulated Windows rename semantics.
- GUI: 13 tests. Import/deduplication, repeated actions, reorder/remove/clear, pagination, rapid layout changes, invalid layout recovery, preview-gated Export, successful exports and conflicts, cancellation, settings Apply/Cancel, persistence, explicit Donate URL, busy-close Yes/No, corrupt preferences, compact window, replacement confirmation, cancelled file dialogs, and Zoom dismissal.
- Additional regression suite: 8 cases covering terminal-status retention, close-confirmation completion race, stale-preview prevention, Unicode sorting and honest partial-cleanup errors.
- Python byte-compilation succeeded.
- Native Linux one-folder executable built with PyInstaller 6.22.3.
- Both source and bundled executable smoke-tested through the real UI workers: 13 generated Unicode-name PNG files imported, live preview rendered, 2-page PDF and two 200-dpi JPEG sheets exported, original input hashes unchanged. Bundled result: `{"ok":true,"photos":13,"pages":2,"originals_unchanged":true}`.
- Final light, dark and compact screenshots inspected. No overlapping controls, clipped title/format/DPI labels or hidden spin/combo arrows. Full-preview Zoom is dismissible without changing the document.
- Sample exported PDF independently parsed: 2 pages, A4 MediaBox 595.2756 × 841.8898 pt. First page rendered through Poppler and visually checked. Captions and title were readable; portraits/landscapes kept their aspect ratios. Numbered JPEGs: 1654 × 2339 pixels at 200 dpi.
- Original synthetic landscape art only; no user photos, credentials, private chat material, caches or environment files are included in deliverable archives.

## Fixes exercised before packaging

Completed-export status used to be overwritten by a resumed preview; completion inside the close-confirmation dialog could leave a frozen window; Unicode circled/superscript digits could break natural sorting; outside output edits and fallback cleanup locks could previously be underreported. All now have passing regressions. A final low-resolution-source check also fixed inconsistent physical sizing between preview and export; the same image now fits identically at 90, 200 and 300 dpi.

## Not run / remaining limits

Actual Windows execution/build, actual physical FAT/exFAT storage, interactive desktop display, HiDPI/multimonitor hardware, screen-reader evaluation, public distribution/signing and older Linux distributions were not tested. Simulated filesystem tests are not a substitute for native Windows or USB-drive validation. The archive is a Linux development bundle, not a Windows executable or AppImage.

On filesystems requiring exclusive-copy fallback, a file can be briefly visible before its copy completes. Ordinary cancellation/errors attempt rollback; process termination, power loss, disk failure or concurrent outside mutation cannot guarantee a whole-batch transaction. Any retained output or backup requiring attention is reported.

PDF pages are raster; captions are not searchable text. Unicode path support is verified, while glyph coverage depends on the font. Very large batches can still use increasing memory for thumbnails and compressed PDF data; imported thumbnails are limited to 128 pixels on their longest side, and full images are processed one at a time.

## Build-workflow preparation, 2026-10-06

After the original MVP validation above, native packaging and CI configuration added 34 packaging tests and 3 independent bundle-smoke checks. The local full suite now passes **143 tests**. The default Linux build, native executable smoke, extraction-mode AppImage smoke, runtime notices, and both archive checksums passed locally on Debian 13. Actions use verified full commit pins; AppImage tool and runtime use verified SHA-256/size pins. The private repository exists; Windows/Ubuntu22.04 CI status must be read from the exact pushed commit run. No Windows success is inferred from Linux or simulated filesystem tests.
