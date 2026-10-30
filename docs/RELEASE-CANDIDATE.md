# Contact Sheet Maker 1.0.0 — historical prepublication record

Prepared 2026-10-30 before publication. Version [1.0.0 is now published](https://github.com/steadystatestudio/contact-sheet-maker/releases/tag/v1.0.0); its [retained validation receipt](https://github.com/steadystatestudio/contact-sheet-maker/releases/download/v1.0.0/RELEASE-READY.json) identifies the exact release source, native checks and package hashes. The sections below preserve the evidence and remaining checks as recorded before publication, including the unmeasured usability and demand targets. They do not claim observed user preference. The previous beta record remains in [BETA-RELEASE.md](BETA-RELEASE.md).

## Changes being verified

The image loader now converts embedded ICC profiles to sRGB for thumbnails, previews and export. Synthetic CMYK JPEG and Display P3 PNG cases verify actual color changes against LittleCMS conversion; transparent RGB/grayscale/palette inputs preserve alpha before blending onto white. Invalid or incompatible profiles are reported, and source bytes remain unchanged.

The shared Studio toolbar remains fixed while short workspaces scroll. Selection and progress use readable dark text on the blue accent, while the centered Export action retains its darker blue, white text and visible keyboard focus. The photo-list/page-preview split, ordering, preview gating, cancellation, retained result and Open Folder behavior remain intact.

The release workflow accepts canonical `vX.Y.Z` and `vX.Y.Z-beta.N` tags. It requires matching package/application versions, an exact source commit on main, unchanged remote tag resolution, the correct release channel, and an unpublished exact-commit draft before asset mutations. It never publishes. Windows, Ubuntu 22.04 and exact-byte Ubuntu 24.04 checks and dependency-source retention remain required for the final automated receipt.

## Verification status

The complete source suite passed **320 tests, with six symlink tests skipped**, on Windows with Python 3.12 and the exact dependency lock (Qt 6.11.2, Pillow 12.3.0, ReportLab 5.0.1). The skips reflect unavailable native symlink privileges. Tests exercised real filesystem rollback outside the restricted test sandbox, eight color-profile cases, narrow-window toolbar access, rendered text contrast, both release channels' protections, and source GUI import/export with ICC-tagged synthetic inputs. Dependency compatibility, byte compilation and diff checks passed.

Light, dark and compact screenshots were generated from synthetic artwork and inspected. Snapshot generation now waits for the second layout pass when switching to stacked export controls, and the smoke checks require the export group to retain its complete minimum height. The focused layout/smoke recheck passed five tests after this adjustment. The package build's `BUILD-INFO.json`, checksums and smoke report identify the exact candidate bytes; Windows evidence does not establish Linux compatibility. Native Linux and cross-Ubuntu validation remain required from the exact release workflow.

The native package check also exposed an environment-specific build fault: unrelated Poppler/libheif directories on the build host's PATH could supply incompatible ICU/UCRT libraries. The Windows PyInstaller subprocess now searches only the isolated interpreter and Windows directories; other build steps keep their normal environment. A clean-path rebuild passed the actual frozen executable smoke check with 13 ICC-tagged inputs, two PDF/JPEG pages and unchanged source hashes.

## Remaining release decisions

- Stable acceptance requires the documented features and file-safety checks to pass, no known blocking defect, native platform tests/build/smoke checks, and exact package checksums, build receipts, dependency sources and synthetic QA. Publication waits for that technical evidence for the exact candidate.
- Review the actual package UI and output, public identity/binary metadata and donation destination. Signing, screen-reader behavior, high-DPI/multi-monitor hardware and physical removable filesystems are not certified by offscreen tests.

## Ongoing usability and demand research

The historical user-observation target calls for five relevant users, four unaided completions, three preferences and two voluntary return jobs. **No such observation evidence is available in this candidate record.** It remains an ongoing research target rather than a technical stable-release prerequisite. Passing software tests does not establish demand, preference, repeat use, accessibility certification or willingness to donate.

All features remain free and donations optional. Donation conversion and sustainable revenue remain unmeasured.
