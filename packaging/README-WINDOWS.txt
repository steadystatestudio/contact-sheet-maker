CONTACT SHEET MAKER — WINDOWS BUILD INSTRUCTIONS

This project has not been run or packaged on Windows yet. Build natively on
Windows 10/11 x64 with Python 3.12 (official python.org distribution):

  py -3.12 -m venv .venv
  .venv\Scripts\python -m pip install -r requirements-build-lock.txt
  .venv\Scripts\python -m pip install --no-deps --no-build-isolation -e .
  .venv\Scripts\python -m pytest -q
  .venv\Scripts\python scripts\build.py

Then run dist\Contact-Sheet-Maker\Contact-Sheet-Maker.exe.
Keep the entire _internal folder alongside the EXE. All features are free.
The current build is unsigned; do not bypass OS security warnings on behalf
of someone else. Public distribution requires native testing and signing or
an intentional unsigned-release policy.

Recommended native smoke checks:
- JPEG/PNG import, Unicode paths, EXIF rotation, corrupt files
- Fit preview, Zoom, reorder, page changes, all three themes
- PDF and numbered JPEG export, replace prompt, source-name collision
- Cancel import/export and close while work runs
- NTFS and exFAT destination behavior, HiDPI display, screen reader labels

Build scripts do not create releases, upload photos, or publish repositories.

The private GitHub Actions workflow also builds and smoke-tests Windows.
Consult the exact commit run for current native CI status; this document
records the original local-development validation limits.
Successful runs provide Contact-Sheet-Maker-windows-x86_64.zip.
