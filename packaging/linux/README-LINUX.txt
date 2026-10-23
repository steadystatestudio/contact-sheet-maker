Contact Sheet Maker: Linux x86-64 public beta

AppImage:
  chmod +x Contact-Sheet-Maker-x86_64.AppImage
  ./Contact-Sheet-Maker-x86_64.AppImage

If FUSE is unavailable, use the runtime's extraction mode:
  APPIMAGE_EXTRACT_AND_RUN=1 ./Contact-Sheet-Maker-x86_64.AppImage

Portable tar.gz:
  Extract the archive, then run Contact-Sheet-Maker/Contact-Sheet-Maker.
  Keep _internal and the executable together. Python is bundled.

GitHub Actions builds on Ubuntu 22.04 x86-64. A graphical desktop and
compatible Qt/X11 or Wayland system libraries are required for interactive
use. An AppImage is not a guarantee of compatibility with every distribution.
See BUILD-INFO.json for the actual build OS, Python and dependency versions.

Linux libraries provided by Ubuntu are not copied into this package. Both the
AppImage and tar.gz use those system libraries. Ubuntu 22.04 and 24.04 x86-64
desktop installations are the tested targets. Before first use, install the
packages listed by the "install" command in LINUX-SYSTEM-DEPENDENCIES.json.
That manifest is generated from the actual excluded libraries and their Ubuntu
package owners. Ubuntu 24.04 may resolve some names to their t64 replacements.
Your package manager supplies their updates, notices and source availability.
Qt, PySide, Pillow and Python remain bundled; Python need not be installed.

AppImages are unsigned. Verify SHA256SUMS-Linux.txt from the same release.
The separate dynamic libraries may be replaced with compatible modified
versions in the extracted one-folder bundle. To inspect the AppImage without
installing it, run ./Contact-Sheet-Maker-x86_64.AppImage --appimage-extract.

Original photographs are processed locally and never uploaded by this app.
See LIBRARY-REPLACEMENT.txt, SOURCE-INDEX.json and licenses/ for matching
library sources, complete notices and replacement/rebuild instructions.
