Contact Sheet Maker: Linux x86-64 private test build

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

AppImages are unsigned private CI artifacts, not a public release.
The separate dynamic libraries may be replaced with compatible modified
versions in the extracted one-folder bundle. To inspect the AppImage without
installing it, run ./Contact-Sheet-Maker-x86_64.AppImage --appimage-extract.

Original photographs are processed locally and never uploaded by this app.
