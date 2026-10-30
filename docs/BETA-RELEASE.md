# Public beta validation

This is the historical beta record. For the **1.0.0 release candidate**, see [RELEASE-CANDIDATE.md](RELEASE-CANDIDATE.md). The user-observation target below is preserved as ongoing usability research and has not been marked as passed by automated tests. The current stable-release criteria concern verified features, file safety, native artifacts and truthful support limits; they do not assert product-market fit.

Historical candidate: **0.1.0b2** (`v0.1.0-beta.2`). Use the exact release's validation receipt and download assets to establish publication and native results.

## Beta.2 changes and validation

- The desktop toolbar now says **Donate**, matching the other Studio utilities, and opens `https://ko-fi.com/steadystatestudio` in the default browser only when clicked.
- Donations are optional and checkout is outside the app. If the browser cannot open, a dismissible message shows the Ko-fi address; retrying does not disturb loaded photos or export readiness.
- README and in-app Help describe the explicit-click behavior. Regression tests cover startup, repeated clicks and browser failure/dismiss/retry. Photo processing, export behavior and the dependency lock are unchanged.
- The existing manual draft workflow can create a missing beta tag only after validating the exact commit, both application/package versions and main ancestry. Existing tags are never moved; the remote tag is reread and verified before staging and again before the final receipt. No workflow permissions were added.

The Donate implementation passed **270 local tests** on Debian 13 with Python 3.12 and Qt offscreen, plus a source smoke test of 13 synthetic photos into two PDF pages and two JPEG sheets with original hashes unchanged. Light, dark and compact interfaces were rendered; dark and compact views and the real browser-failure dialog were checked. These checks do not establish native release-package results.

The complete beta.2 local suite passed **309 tests, zero failures and zero skips** in 130.34 seconds on 2026-10-28. The focused release-safety suite passed **70 tests**; dependency compatibility, byte compilation, version consistency and diff checks also passed. Before publication, the exact beta.2 source must pass native Windows Server 2022 and Ubuntu 22.04 tests, package builds and packaged smoke checks, plus Ubuntu 24.04 verification and smoke tests of the exact retained Linux bytes. Matching library sources, asset digests and `RELEASE-READY.json` must be retained in the draft release. Public identity/binary metadata, donation destination and synthetic QA must be reviewed before publishing. No beta.1 hashes or native results below are evidence for beta.2.

## Beta.1 historical evidence

Version: **0.1.0b1** (`v0.1.0-beta.1`).

This document separates automated evidence from real-device and user research. The GitHub release's validation receipt identifies the exact source revision and packaged bytes. A draft release is not a public download.

### Release changes

- Complete filename captions wrap to two readable lines; layouts that cannot preserve them are rejected before export.
- Export readiness has a nearby visible explanation. Full import errors remain available, including batches with more than 100 failures.
- System, Light, Dark ordering; refreshed screenshots; explicit beta/unsigned-package documentation.
- The Support action opens the Studio support page only on request. Donations remain unavailable there until payment-provider privacy is verified.
- Release assets and QA are staged on draft GitHub releases, avoiding the account's Actions artifact-storage quota. Ubuntu 24.04 verifies the exact Ubuntu 22.04 package bytes before publication.

### Evidence

Baseline native CI passed 206 tests on each of Windows Server 2022 and Ubuntu 22.04, plus native package builds and executable/AppImage smoke checks. Historical artifact uploads failed because of quota; those builds were not reused as public downloads.

On 2026-10-23, the changed beta source passed the complete integrated suite on Windows: **243 passed, 6 skipped**. This used Python 3.12.10 and the exact project dependency lock, including PySide6 6.11.2, Pillow 12.3.0, ReportLab 5.0.1 and pytest 9.1.1, with Qt's offscreen platform. The six skips are symlink cases unavailable without elevated rights on this host.

The suite covers complete caption wrapping at preview/export resolutions, rejection of an overflowing filename on a later page before output staging, automatic recovery after layout changes, preservation of export receipts, more than 100 import errors, and the draft-release validation gates. Source GUI smoke also passed: 13 synthetic Unicode-named inputs, two PDF pages and two JPEG sheets, with original input hashes unchanged. Refreshed light, dark and compact screenshots were inspected.

The final release source is `f48da01185fcb7a756425d98e580bc8d800b1699` (tree `ff9c0411f778c02c4b063f87417d252c83a43a92`). [Release workflow 40002009253](https://github.com/steadystatestudio/contact-sheet-maker/actions/runs/40002009253) passed **269 tests, zero failures and zero skips on each of Windows Server 2022 and Ubuntu 22.04**. Native package builds and packaged-executable/AppImage smoke checks passed. Ubuntu 24.04 independently verified and ran the exact retained Ubuntu 22.04 tar bundle and AppImage with their declared desktop prerequisites installed. All five smoke checks exported 13 photos into two PDF pages and two JPEG sheets without changing original input hashes.

The [published beta release](https://github.com/steadystatestudio/contact-sheet-maker/releases/tag/v0.1.0-beta.1) retains the exact packages, build information, checksums, synthetic QA and matching library source archives. Its `RELEASE-READY.json` records the automated draft-stage result; publication followed a review of source history, binary contents, screenshots, output metadata and package licenses. Linux packages use the host's system libraries, listed in their `LINUX-SYSTEM-DEPENDENCIES.json`. They are not fully self-contained distributions.

| Download | SHA-256 |
| --- | --- |
| Windows ZIP | `217aa26ee37349d481d188432747bb143e3c48cfd1ebe5fe62f81692c0ff80c3` |
| Linux tar.gz | `8544c06cba355eb393dacc12850646c005d7ec25b15be6eef994f53e185cef32` |
| Linux AppImage | `f0abf53cd359bde90c2fd64db07817c9dcfdfff49e1ba7f6528240d893b28196` |

## Remaining real-device checks

Automated Qt smoke tests do not certify a human's interactive experience, screen readers, multiple monitors, high-DPI hardware, or physical removable filesystems. These remain beta feedback targets. Linux distribution support is limited to the exact environments recorded by the release receipt.

## Historical version 1.0 observation target — ongoing research

Observe five people who already make proof sheets, using non-sensitive material and their real comparison workflow. At least four must finish unaided, three must prefer this workflow, and two must voluntarily return for another job. There must be no silent omission, clipped identifying caption, or source-file modification in the tested corpus. Fix observed barriers and repeat the relevant checks.

Downloads are not unique users. Voluntary donation attribution, repeat use, support burden, and maintenance time are separate evidence. No revenue forecast or human-validation claim is made by the technical 1.0 release.
