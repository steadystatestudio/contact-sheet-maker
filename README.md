# Contact Sheet Maker

A free, offline Steady State Studio desktop utility for turning local JPEG and PNG photos into printable contact sheets.

**1.0.0 is released.** Every feature is free. No account, uploads, watermarks, or feature gates. Get the [version 1.0.0 downloads](https://github.com/steadystatestudio/contact-sheet-maker/releases/tag/v1.0.0) and see the [retained validation receipt](https://github.com/steadystatestudio/contact-sheet-maker/releases/download/v1.0.0/RELEASE-READY.json) for its exact source, native checks and package hashes. Real-user preference and repeat use are still being evaluated.

[App details](https://steady-state-studio.steadystatestudio1.workers.dev/apps/contact-sheet-maker/) · [Studio website](https://steady-state-studio.steadystatestudio1.workers.dev/) · [Versioned downloads](https://github.com/steadystatestudio/contact-sheet-maker/releases) · [Report a problem](https://github.com/steadystatestudio/contact-sheet-maker/issues) · [Donate on Ko-fi](https://ko-fi.com/steadystatestudio)

![Dark interface](docs/screenshot-dark.png)

## What works

- Add selected photos, one folder, or dropped files/folders. Folder imports are naturally sorted (`2` before `10`), deduplicated and non-recursive.
- Visible ordering with multi-row Up/Down, Remove and Clear; thumbnail list and full-sheet preview.
- A4 or US Letter, portrait/landscape, rows/columns, millimetre margins/gaps, filename captions and optional sheet title.
- Three print presets (12, 20, or 6 photos); last layout/export choices and window arrangement are remembered locally.
- Resizable table/preview split, page navigation and a scrollable full-resolution Zoom preview. Short work areas scroll independently while export and status stay visible; output controls stack in narrow windows, and restored windows fit the available monitor.
- Multipage PDF or numbered JPEG sheets at 150, 200 or 300 dpi. Photos always fit without cropping; EXIF rotation is honoured. Embedded color profiles are converted to sRGB before transparent areas are placed on white paper.
- System/Light/Dark appearance, keyboard shortcuts, readable focus borders and accessible control labels.
- Background import, preview and export with cancellation. Close during work asks first and waits for safe cleanup.
- Import feedback stays visible after the preview finishes: added, already-listed and unreadable photos are counted separately. Missing or unreadable selections are reported while valid selections are added. Cancelling an import leaves the photo list unchanged.

## Run from source

Python 3.10+ (tested with Python 3.12 on Debian 13 x86_64):

```sh
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -e .
python -m contact_sheet
```

For the exact development dependency versions use `python -m pip install -r requirements-build-lock.txt` first. All packages come from the normal Python package index; no global installation is necessary. Installing requires Internet access; the running app does not.

### Linux downloads

Use the assets and SHA-256 checksums on the exact published release. Download `Contact-Sheet-Maker-x86_64.AppImage`, make it executable, and run it. Where FUSE is unavailable, use `APPIMAGE_EXTRACT_AND_RUN=1`. A portable `Contact-Sheet-Maker-linux-x86_64.tar.gz` is also available. The release pipeline builds on Ubuntu 22.04 and verifies the same package bytes on Ubuntu 24.04; consult its validation receipt before assuming those checks passed. A graphical desktop and normal Qt/X11 or Wayland libraries are required. Other Linux distributions, ARM, and macOS have no supported download.

### Windows

Extract `Contact-Sheet-Maker-windows-x86_64.zip` from the versioned release and run `Contact-Sheet-Maker/Contact-Sheet-Maker.exe`. Keep the `_internal` folder beside it. Python is bundled; no administrator installation is required. **Windows packages are unsigned** and Windows may show a reputation warning. Verify the source and checksum, follow your organisation's policy, and do not disable security protections to run it.

See `packaging/README-WINDOWS.txt` for native build commands and the remaining interactive checklist. Automated checks run on Windows Server 2022; interactive Windows 10/11, screen-reader, and high-DPI hardware behavior are ongoing validation targets, not certified coverage.

## Workflow

1. Add photos/folder. Select rows and use ↑/↓ to establish print order; Alt+Up/Down also works, Delete removes selected rows, Ctrl+O adds photos.
2. Choose a preset or customize the layout. The current preview must finish successfully before Export enables. Use page arrows and Zoom to inspect it.
3. Choose format, DPI and filename. Export Sheets asks for a destination directory. `contact-sheet.pdf` is one multipage PDF; JPEG yields `contact-sheet-001.jpg`, `contact-sheet-002.jpg`, etc.
4. If output names already exist, choose Replace, Keep Both, or Cancel. Keep Both uses one unused filename for the whole batch, such as `contact-sheet (2)`; Cancel leaves everything unchanged. Open Folder appears after success.

Removing selected photos keeps the next remaining row selected so you can continue with the keyboard. Moving photos keeps the current row with its photo; Delete and Alt+Up/Down act only inside the photo list. Hover a photo row to read its full path. Duplicate-only additions preserve your selection and preview. Open Folder remains available for the last successful export after later imports or cancelled operations; its tooltip identifies that folder.

PDF page dimensions match the selected paper. Complete filename captions wrap to at most two 8 pt lines; a layout that cannot fit them is rejected with guidance before export. The optional title is 14 pt. Pages are raster images inside the PDF, so text is not selectable/searchable. The 90-dpi UI preview uses the same layout renderer; exported pages use the chosen higher DPI. Fonts and image resampling can make small preview text appear slightly different, while positions and full-photo fitting remain consistent.

## Privacy and safety

No telemetry, automatic upload, cloud account, subscription, watermark, or feature gate. Donate opens the Studio's Ko-fi page in your default browser only when clicked. Donations are optional; checkout is handled on Ko-fi, outside the app. Help and processing are local. The app saves ordinary UI preferences and last chosen folder paths with Qt settings; the loaded photo list is not persisted.

Original photos are never modified. Output names cannot replace source files, including hardlink aliases. Files are inspected as actual JPEG/PNG content, corruption is reported, and images above 60 million pixels are refused. Very large compressed files can still take time to read; native decoder calls cannot be interrupted halfway through, so cancellation is checked between safe steps. Source fingerprints detect photos changed since import or while generating sheets and stop export rather than quietly using mixed versions.

Valid embedded ICC profiles, including CMYK JPEG and wide-gamut RGB profiles, are converted to sRGB for both previews and exported pages. Invalid or incompatible profiles are reported instead of silently changing colors. Untagged RGB photos are treated as sRGB; for predictable CMYK colors, export a tagged JPEG or convert it to sRGB first. Transparent pixels are blended onto white after color conversion. Source EXIF/GPS and other personal metadata are not copied into sheets.

All sheets render into a temporary directory inside the selected destination before commit. Existing outputs require explicit replacement; exclusive installation rejects unexpected files that appear during export. Cancellation and ordinary commit failures roll back installed files and restore previous outputs. If another process blocks restoration, the error identifies retained backups for manual recovery. If export succeeds but old backups cannot be removed, the app confirms the sheets were saved and lists those backups separately.

On filesystems without hardlinks, an exclusive-create copy fallback is used (Windows first uses native no-replace rename). The copy fallback can briefly expose an incomplete newly created output. **Abrupt process termination, power loss, disk failure or outside modification during a multi-file commit cannot guarantee rollback.** Do not point another program at output files while exporting; keep backups of important prior sheets. Filesystem fallback is fault-injection-tested here, not tested against a physical exFAT volume.

## Tests and development

```sh
python -m pip install -e ".[test,build]"
QT_QPA_PLATFORM=offscreen python -m pytest -q
python scripts/render_preview.py
python scripts/fetch_appimagetool.py  # Linux only: pinned tool and runtime
python scripts/build.py
python scripts/smoke_bundle.py dist/Contact-Sheet-Maker/Contact-Sheet-Maker
```

On Windows set `QT_QPA_PLATFORM=offscreen` in the environment if you want headless tests, or run with the normal desktop Qt platform. The renderer creates original synthetic landscape art, screenshots and real sample output under `docs/`; no user photographs are packaged. `docs/VALIDATION.md` records the checks actually run.

## Windows and Linux build workflow

`.github/workflows/build.yml` runs on pushes, pull requests and manual dispatch. It installs the exact dependency lock, runs the complete suite on Windows Server 2022 and Ubuntu 22.04, builds native packages, and smoke-tests the actual packaged executables. Linux also smoke-tests the AppImage without requiring FUSE. The release workflow adds a separate Ubuntu 24.04 job that downloads and verifies the exact Ubuntu 22.04 package bytes, then exercises both the extracted bundle and AppImage.

Download published packages from the repository's versioned Releases. A separate trusted-tag release workflow stages platform packages, checksums, dependency sources, and QA reports in a draft prerelease, then verifies the exact Linux package bytes on Ubuntu 24.04. Drafts remain unpublished until release checks and the privacy review pass. Ordinary CI does not depend on Actions artifact storage.

Packages include `BUILD-INFO.json` (exact source commit, source hashes and dependency versions) and accompanying SHA-256 checksums. Actions use fixed commit SHAs. AppImage packaging verifies both its tool and runtime by fixed size and SHA-256 before execution; there are no mutable `latest` downloads. Ordinary CI has read-only permissions. Only trusted release staging jobs may write draft release assets; the workflow does not publish automatically.

The smoke test imports 13 synthetic photos with Unicode filenames through the real UI, exports two pages as PDF/JPEG, checks physical page sizes and DPI, verifies input hashes, and captures the UI. It has a 120-second external timeout. This is automated native/headless validation, not a claim of human usability testing. See each exact commit's Actions result for its verified platform status.

For a native folder/archive build without AppImage tooling, use `python scripts/build.py --bundle-only`. Smoke output must use a fresh directory; the runner refuses to replace an existing report.

## Deliberate limits / remaining work

- JPEG and PNG only; no RAW, HEIC, TIFF, video or animated-frame selection. For animated PNG, only the first frame is used.
- No direct printer integration, crop-to-fill, borders, per-photo caption editing, saved projects or recursive folder traversal.
- Unicode paths work. Caption glyph coverage is font-dependent; DejaVu Sans is bundled for broad Latin/Greek/Cyrillic coverage, with platform CJK font fallback where installed. Emoji and every writing system are not guaranteed.
- The 60M-pixel safety cap and one-source-at-a-time rendering bound large decoded images, but this is not a hardened untrusted-file sandbox. PNG decoding may still require substantial memory. PDF encoding retains compressed document data, so very large documents can consume increasing memory.
- Interactive Windows behavior, high-DPI displays, screen readers, physical USB filesystems, distribution signing and wider Linux compatibility remain ongoing validation targets. Native CI results are recorded per commit and do not imply human QA. See `docs/RELEASE-CANDIDATE.md` for current release gates and `docs/BETA-RELEASE.md` for historical beta evidence.

MIT license, copyright © 2026 Steady State Studio. The actual File Renamer theme/status component was adapted under its MIT license; exact provenance and dependency notices are in `THIRD_PARTY_NOTICES.md`. Every feature remains free, with optional support never required to finish a job.
