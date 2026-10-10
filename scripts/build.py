"""Build native private test packages on Windows or Linux x86-64.

The AppDir layout follows Steady State Studio's MIT-licensed File Renamer:
https://github.com/steadystatestudio/file-renamer/tree/342f2cebf672578ff27f299eda466da7c2df4b96
Copyright (c) 2026 Steady State Studio. See LICENSE for the full MIT notice.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

# Support both `python scripts/build.py` and import-based build tests.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_appimagetool as appimage_inputs

ROOT = Path(__file__).resolve().parents[1]
NAME = "Contact-Sheet-Maker"
LICENSE_PACKAGES = (
    "Pillow", "reportlab", "charset-normalizer", "PySide6", "PySide6_Essentials",
    "PySide6_Addons", "shiboken6", "PyInstaller", "altgraph", "packaging", "setuptools",
)


def confined_output(root: Path, path: Path) -> Path:
    """Check before creating, replacing or cleaning build outputs."""
    resolved = path.resolve()
    if resolved == root.resolve() or not resolved.is_relative_to(root.resolve()):
        raise RuntimeError(f"Build output escaped the project: {path.name}")
    return path


def icon_png(root: Path, target: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(str(root / "src/contact_sheet/assets/icon.svg"))
    if not renderer.isValid():
        raise RuntimeError("Application SVG icon is invalid")
    image = QImage(256, 256, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(target)):
        raise RuntimeError("Could not create application icon")
    # Keep the application alive until rendering has finished.
    app.processEvents()


def pyinstaller_command(root: Path, target_platform: str) -> list[str]:
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--noupx", "--name", NAME, "--paths", str(root / "src"), "--collect-data", "contact_sheet",
        "--specpath", str(root / "build"), "--distpath", str(root / "dist"),
        "--workpath", str(root / "build/pyinstaller"),
    ]
    for module in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "tkinter", "pytest"):
        command.extend(["--exclude-module", module])
    if target_platform == "win32":
        command.extend(["--icon", str(root / "build/icon.png")])
    return command + [str(root / "scripts/launcher.py")]


def source_hashes(root: Path) -> dict[str, str]:
    """Record build inputs, without local photos, caches, absolute paths or secrets."""
    paths = [root / name for name in ("pyproject.toml", "requirements-build-lock.txt", "LICENSE", "THIRD_PARTY_NOTICES.md")]
    for directory in ("src", "scripts", "packaging", ".github/workflows"):
        paths.extend((root / directory).rglob("*"))
    hashes = {}
    for path in sorted(set(paths)):
        relative = path.relative_to(root)
        if (not path.is_file() or path.is_symlink() or "__pycache__" in relative.parts
                or any(part.endswith(".egg-info") for part in relative.parts)
                or path.suffix in {".pyc", ".pyo"}):
            continue
        hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def source_revision(root: Path) -> str:
    revision = os.environ.get("BUILD_SOURCE_COMMIT", "")
    if not revision:
        try:
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return "uncommitted-local-build"
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise RuntimeError("BUILD_SOURCE_COMMIT must be a complete Git commit SHA")
    return revision.lower()


def write_build_info(root: Path, bundle: Path, target_platform: str) -> None:
    dependencies = {}
    for name in LICENSE_PACKAGES:
        dependencies[name] = metadata.version(name)
    for name in ("pefile", "pywin32-ctypes", "pytest", "pypdf"):
        try:
            dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    info = {
        "application": NAME,
        "repository": "steadystatestudio/contact-sheet-maker",
        "source_tree": os.environ.get("BUILD_SOURCE_TREE"),
        "application_version": metadata.version("steady-contact-sheet"),
        "source_commit": source_revision(root),
        "python": platform.python_version(),
        "platform": target_platform,
        "os": platform.platform(),
        "machine": platform.machine(),
        "dependencies": dependencies,
        "source_sha256": source_hashes(root),
        "appimage_inputs": {
            "appimagetool": {"url": appimage_inputs.URL, "sha256": appimage_inputs.SHA256},
            "runtime": {"url": appimage_inputs.RUNTIME_URL, "sha256": appimage_inputs.RUNTIME_SHA256},
        } if target_platform == "linux" else None,
    }
    (bundle / "BUILD-INFO.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_notices(root: Path, bundle: Path, target_platform: str) -> None:
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "requirements-build-lock.txt"):
        shutil.copy2(root / name, bundle / name)
    if (root / "docs/VALIDATION.md").is_file():
        shutil.copy2(root / "docs/VALIDATION.md", bundle / "VALIDATION.md")
    licenses = bundle / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copytree(root / "packaging/licenses", licenses, dirs_exist_ok=True)
    shutil.copy2(root / "packaging/DEJAVU_FONT_LICENSE.txt", licenses / "DEJAVU_FONT_LICENSE.txt")
    readme = "packaging/README-WINDOWS.txt" if target_platform == "win32" else "packaging/linux/README-LINUX.txt"
    shutil.copy2(root / readme, bundle / Path(readme).name)
    if target_platform == "linux":
        shutil.copy2(root / "packaging/linux/APPIMAGE_RUNTIME_LICENSE.txt", licenses / "APPIMAGE_RUNTIME_LICENSE.txt")
    # Full Python license, not an unrelated OS interpreter's license.
    python_licenses = (Path(sys.base_prefix) / "LICENSE.txt", Path(sysconfig.get_path("stdlib")) / "LICENSE.txt")
    for source in python_licenses:
        if source.is_file():
            shutil.copy2(source, licenses / "Python-LICENSE.txt")
            break
    else:
        raise RuntimeError("Python license text is missing from the build interpreter")
    for name in LICENSE_PACKAGES:
        distribution = metadata.distribution(name)
        for entry in distribution.files or []:
            relative = Path(entry)
            if not any(word in str(relative).upper() for word in ("LICENSE", "COPYING", "NOTICE")):
                continue
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                # Preserve relative license paths to avoid silently overwriting same-named notices.
                safe_parts = [part for part in relative.parts if part not in ("..", ".") and part != relative.anchor]
                target = licenses / name / Path(*safe_parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    write_build_info(root, bundle, target_platform)


def make_appdir(root: Path, bundle: Path) -> Path:
    appdir = confined_output(root / "build", root / "build" / f"{NAME}.AppDir")
    if appdir.exists():
        shutil.rmtree(appdir)
    shutil.copytree(bundle, appdir / "usr/lib/contact-sheet-maker", symlinks=True)
    shutil.copy2(root / "build/icon.png", appdir / "contact-sheet-maker.png")
    for name in ("AppRun", "contact-sheet-maker.desktop"):
        shutil.copy2(root / "packaging/linux" / name, appdir / name)
    (appdir / "AppRun").chmod(0o755)
    return appdir


def package_appimage(root: Path, bundle: Path) -> Path:
    tool = Path(os.environ.get("APPIMAGETOOL", str(root / "build/tools/appimagetool")))
    runtime = Path(os.environ.get("APPIMAGE_RUNTIME", str(root / "build/tools/runtime-x86_64")))
    for path, digest, size in (
        (tool, appimage_inputs.SHA256, appimage_inputs.SIZE),
        (runtime, appimage_inputs.RUNTIME_SHA256, appimage_inputs.RUNTIME_SIZE),
    ):
        if not appimage_inputs.verify_file(path, digest, size):
            raise RuntimeError("AppImage input is missing or unverified; run python scripts/fetch_appimagetool.py")
    appdir = make_appdir(root, bundle)
    output = confined_output(root, root / "dist" / f"{NAME}-x86_64.AppImage")
    environment = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    # Supplying --runtime-file prevents the tool's implicit mutable upstream download.
    subprocess.run([str(tool.resolve()), "--runtime-file", str(runtime.resolve()), str(appdir), str(output)],
                   cwd=root, env=environment, check=True, timeout=1200)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("AppImage packaging did not create an output")
    return output


def make_archive(root: Path, target_platform: str) -> Path:
    suffix, format_name = ("windows-x86_64", "zip") if target_platform == "win32" else ("linux-x86_64", "gztar")
    base = confined_output(root, root / "dist" / f"{NAME}-{suffix}")
    return Path(shutil.make_archive(str(base), format_name, root_dir=root / "dist", base_dir=NAME))


def write_checksums(root: Path, artifacts: list[Path]) -> None:
    lines = []
    for path in artifacts:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        lines.append(f"{digest}  {path.name}\n")
    (root / "dist/SHA256SUMS.txt").write_text("".join(lines), encoding="ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-only", action="store_true", help="Skip AppImage creation; still create a portable ZIP/tar archive")
    arguments = parser.parse_args(argv)
    if sys.platform not in {"win32", "linux"}:
        raise SystemExit("Run the native build on Windows or Linux.")
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise SystemExit("These packages require an x86-64 build host.")
    root = ROOT.resolve()
    build = confined_output(root, root / "build")
    dist = confined_output(root, root / "dist")
    for path in (dist / NAME, build / "pyinstaller", build / "pyinstaller-cache", build / "icon.png",
                 dist / "SHA256SUMS.txt", dist / f"{NAME}-windows-x86_64.zip",
                 dist / f"{NAME}-linux-x86_64.tar.gz", dist / f"{NAME}-x86_64.AppImage"):
        confined_output(root, path)
    build.mkdir(exist_ok=True)
    dist.mkdir(exist_ok=True)
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(build / "pyinstaller-cache")
    icon_png(root, build / "icon.png")
    subprocess.run(pyinstaller_command(root, sys.platform), cwd=root, check=True, timeout=1200)
    bundle = dist / NAME
    copy_notices(root, bundle, sys.platform)
    artifacts = [make_archive(root, sys.platform)]
    if sys.platform == "linux" and not arguments.bundle_only:
        artifacts.append(package_appimage(root, bundle))
    write_checksums(root, artifacts)
    for path in artifacts:
        print(f"Built {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
