# Public beta validation

Version: **0.1.0b1** (`v0.1.0-beta.1`).

This document separates automated evidence from real-device and user research. The GitHub release's validation receipt identifies the exact source revision and packaged bytes. A draft release is not a public download.

## Release changes

- Complete filename captions wrap to two readable lines; layouts that cannot preserve them are rejected before export.
- Export readiness has a nearby visible explanation. Full import errors remain available, including batches with more than 100 failures.
- System, Light, Dark ordering; refreshed screenshots; explicit beta/unsigned-package documentation.
- The Support action opens the Studio support page only on request. Donations remain unavailable there until payment-provider privacy is verified.
- Release assets and QA are staged on draft GitHub releases, avoiding the account's Actions artifact-storage quota. Ubuntu 24.04 verifies the exact Ubuntu 22.04 package bytes before publication.

## Evidence

Baseline native CI passed 206 tests on each of Windows Server 2022 and Ubuntu 22.04, plus native package builds and executable/AppImage smoke checks. Historical artifact uploads failed because of quota; those builds were not reused as public downloads.

On 2026-10-23, the changed beta source passed the complete integrated suite on Windows: **243 passed, 6 skipped**. This used Python 3.12.10 and the exact project dependency lock, including PySide6 6.11.2, Pillow 12.3.0, ReportLab 5.0.1 and pytest 9.1.1, with Qt's offscreen platform. The six skips are symlink cases unavailable without elevated rights on this host.

The suite covers complete caption wrapping at preview/export resolutions, rejection of an overflowing filename on a later page before output staging, automatic recovery after layout changes, preservation of export receipts, more than 100 import errors, and the draft-release validation gates. Source GUI smoke also passed: 13 synthetic Unicode-named inputs, two PDF pages and two JPEG sheets, with original input hashes unchanged. Refreshed light, dark and compact screenshots were inspected.

These are Windows source/offscreen results. The changed beta's native package builds, packaged-executable/AppImage smoke checks and Ubuntu 24.04 verification of the exact retained Ubuntu 22.04 bytes are still pending. Record their exact release revision, checksums and workflow receipt before offering binary downloads. Historical baseline results do not validate the changed packages.

## Remaining real-device checks

Automated Qt smoke tests do not certify a human's interactive experience, screen readers, multiple monitors, high-DPI hardware, or physical removable filesystems. These remain beta feedback targets. Linux distribution support is limited to the exact environments recorded by the release receipt.

## Version 1.0 gate

Observe five people who already make proof sheets, using non-sensitive material and their real comparison workflow. At least four must finish unaided, three must prefer this workflow, and two must voluntarily return for another job. There must be no silent omission, clipped identifying caption, or source-file modification in the tested corpus. Fix observed barriers and repeat the relevant checks.

Downloads are not unique users. Voluntary donation attribution, repeat use, support burden, and maintenance time are separate evidence. No revenue forecast or final-release claim is made by this beta.
