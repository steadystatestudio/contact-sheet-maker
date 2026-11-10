# Contact Sheet Maker 1.2.13 validation

At version preparation on 2026-11-09, the final 1.2.13 package builds,
release receipts and native package acceptance are pending. Earlier audit
checks support the dependency changes; they do not validate rebuilt bytes.

Use the exact release's `RELEASE-READY.json`, platform receipts, package hashes
and verified application source archive to identify the source and checks for
a download. Detailed synthetic QA and native build logs remain private.
Earlier development or release results do not validate a rebuilt package.

The manual reviewed-release workflow requires an exact main-branch commit,
matching application/tag versions and an unpublished exact-commit draft. It
runs the source suite and packaged smoke checks on Windows and Ubuntu 22.04,
then checks the same retained Linux bytes on Ubuntu 24.04. Matching Qt 6.12.0,
PySide/Shiboken and AppImage dependency sources are required release assets.
The workflow creates the final automated receipt only after all these gates
pass, and leaves publication as a separate action.

Synthetic checks cover PDF/JPEG output, ordering and layout, color conversion,
file preservation, cancellation, package startup and dependency provenance.
Inspect the actual packaged interface and output before publication. Automated
checks do not certify screen readers, high-DPI or multiple-monitor hardware,
physical removable filesystems, every Linux desktop, or real-user usability.
Packages are unsigned; all features remain free and support remains optional.
Optional support payment and receipt delivery have not been tested.

Public releases must retain checksums, accurate platform summaries, matching
dependency sources and a verified application source archive for the published
package bytes. Preserve the original private build and QA receipts when
preparing the public release metadata.
