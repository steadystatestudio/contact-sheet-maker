"""Packaging safety, provenance and CI contract checks without network or builds."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_script("build")
fetch = load_script("fetch_appimagetool")


class Response(io.BytesIO):
    def __init__(self, body, url="https://release-assets.githubusercontent.com/test"):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


def download(monkeypatch, target, body=b"verified tool", response_body=None, **kwargs):
    calls = []

    def urlopen(request, timeout):
        calls.append((request, timeout))
        return Response(body if response_body is None else response_body)

    monkeypatch.setattr(fetch.urllib.request, "urlopen", urlopen)
    result = fetch.download_verified(target, fetch.URL, hashlib.sha256(body).hexdigest(), len(body), **kwargs)
    return result, calls


def symlink_or_skip(target, link, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("Host cannot create symlinks without elevated rights")


def test_downloader_fixed_official_pins():
    assert "/1.9.1/" in fetch.URL
    assert "/20251108/" in fetch.RUNTIME_URL
    assert "continuous" not in fetch.RUNTIME_URL
    assert fetch.SHA256 == "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
    assert fetch.RUNTIME_SHA256 == "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"
    assert fetch.SIZE == 15_092_216 and fetch.RUNTIME_SIZE == 944_632


def test_verified_download_is_atomic_and_executable(tmp_path, monkeypatch):
    target = tmp_path / "tools/appimagetool"
    result, calls = download(monkeypatch, target, executable=True)
    assert result == target and target.read_bytes() == b"verified tool"
    assert calls[0][0].full_url == fetch.URL and calls[0][1] == 120
    assert not list(target.parent.glob("*.download"))
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o755


def test_verified_cache_does_not_download(tmp_path, monkeypatch):
    target = tmp_path / "tool"
    target.write_bytes(b"verified tool")
    _, calls = download(monkeypatch, target)
    assert calls == []


def test_invalid_cache_is_replaced_only_with_verified_bytes(tmp_path, monkeypatch):
    target = tmp_path / "tool"
    target.write_bytes(b"wrong cache")
    download(monkeypatch, target)
    assert target.read_bytes() == b"verified tool"


@pytest.mark.parametrize("bad", [b"changed bytes", b"truncated", b"a" * 100])
def test_changed_download_fails_closed_and_keeps_existing_cache(tmp_path, monkeypatch, bad):
    target = tmp_path / "tool"
    target.write_bytes(b"prior cache")
    with pytest.raises(RuntimeError, match="checksum|pinned size"):
        download(monkeypatch, target, response_body=bad)
    assert target.read_bytes() == b"prior cache"
    assert not list(tmp_path.glob("*.download"))


def test_network_error_does_not_replace_file(tmp_path, monkeypatch):
    target = tmp_path / "tool"
    target.write_bytes(b"prior cache")
    def fail(*args, **kwargs):
        raise OSError("offline")
    monkeypatch.setattr(fetch.urllib.request, "urlopen", fail)
    with pytest.raises(OSError, match="offline"):
        fetch.download_verified(target, fetch.URL, fetch.SHA256, fetch.SIZE)
    assert target.read_bytes() == b"prior cache"


def test_insecure_redirect_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda *a, **k: Response(b"x", "http://example.org/tool"))
    with pytest.raises(RuntimeError, match="insecure"):
        fetch.download_verified(tmp_path / "tool", fetch.URL, "unused", 1)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("url,size", [("http://example.org/tool", 1), (fetch.URL, 0), (fetch.URL, fetch.MAX_DOWNLOAD_BYTES + 1)])
def test_unsafe_download_parameters_rejected(tmp_path, url, size):
    with pytest.raises(ValueError, match="bounded HTTPS"):
        fetch.download_verified(tmp_path / "tool", url, fetch.SHA256, size)


def test_download_rejects_symlink_target(tmp_path, monkeypatch):
    original = tmp_path / "original"
    original.write_bytes(b"untouched")
    link = tmp_path / "tool"
    symlink_or_skip(original, link)
    with pytest.raises(ValueError, match="symlink"):
        download(monkeypatch, link)
    assert original.read_bytes() == b"untouched"


def test_main_downloader_confines_directory(tmp_path, monkeypatch):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    symlink_or_skip(outside, root / "build", directory=True)
    monkeypatch.setattr(fetch, "ROOT", root)
    with pytest.raises(RuntimeError, match="escaped"):
        fetch.main()


def test_main_downloader_fetches_both_pinned_inputs(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    monkeypatch.setattr(fetch, "download_verified", lambda *a, **k: calls.append((a, k)))
    assert fetch.main() == 0
    assert len(calls) == 2
    assert calls[0][0][1:] == (fetch.URL, fetch.SHA256, fetch.SIZE)
    assert calls[1][0][1:] == (fetch.RUNTIME_URL, fetch.RUNTIME_SHA256, fetch.RUNTIME_SIZE)
    assert calls[0][1] == {"executable": True}


def test_verify_rejects_wrong_size_digest_and_nonfile(tmp_path):
    path = tmp_path / "tool"
    assert not fetch.verify_file(path, "none", 1)
    assert not fetch.verify_file(tmp_path, "none", 1)
    path.write_bytes(b"x")
    assert not fetch.verify_file(path, "none", 1)
    assert not fetch.verify_file(path, hashlib.sha256(b"x").hexdigest(), 2)


@pytest.mark.parametrize("relative", [".", "../outside", "build/../../outside"])
def test_build_output_rejects_escape(tmp_path, relative):
    with pytest.raises(RuntimeError, match="escaped"):
        build.confined_output(tmp_path, tmp_path / relative)


def test_build_output_allows_project_descendants(tmp_path):
    assert build.confined_output(tmp_path, tmp_path / "build/work") == tmp_path / "build/work"


def test_build_output_rejects_symlink_escape(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    symlink_or_skip(outside, root / "dist", directory=True)
    with pytest.raises(RuntimeError, match="escaped"):
        build.confined_output(root, root / "dist/app")


@pytest.mark.parametrize("target_platform", ["linux", "win32"])
def test_pyinstaller_native_command_paths_and_icon(tmp_path, target_platform):
    command = build.pyinstaller_command(tmp_path, target_platform)
    assert command[:3] == [sys.executable, "-m", "PyInstaller"]
    assert "--onedir" in command and "--windowed" in command and "--noupx" in command
    assert command[command.index("--specpath") + 1] == str(tmp_path / "build")
    assert command[-1] == str(tmp_path / "scripts/launcher.py")
    assert ("--icon" in command) == (target_platform == "win32")
    assert "contact_sheet" in command


def test_source_hashes_exclude_private_files_and_caches(tmp_path):
    source = tmp_path / "src/contact_sheet"; source.mkdir(parents=True)
    (source / "app.py").write_text("example", encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__/app.pyc").write_bytes(b"cache")
    (tmp_path / "private-photo.jpg").write_bytes(b"private")
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/input.png").write_bytes(b"private")
    hashes = build.source_hashes(tmp_path)
    assert hashes == {"src/contact_sheet/app.py": hashlib.sha256(b"example").hexdigest()}


def test_build_metadata_has_pins_commit_and_relative_input_hashes(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"; bundle.mkdir()
    (tmp_path / "pyproject.toml").write_text("project", encoding="utf-8")
    monkeypatch.setenv("BUILD_SOURCE_COMMIT", "a" * 40)
    monkeypatch.setattr(build.metadata, "version", lambda package: "1.2.3")
    build.write_build_info(tmp_path, bundle, "linux")
    info = json.loads((bundle / "BUILD-INFO.json").read_text(encoding="utf-8"))
    assert info["source_commit"] == "a" * 40
    assert info["application_version"] == "1.2.3"
    assert info["appimage_inputs"]["runtime"]["sha256"] == fetch.RUNTIME_SHA256
    assert info["source_sha256"] == {"pyproject.toml": hashlib.sha256(b"project").hexdigest()}
    assert str(tmp_path) not in json.dumps(info)


def test_source_revision_rejects_malformed_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_SOURCE_COMMIT", "main")
    with pytest.raises(RuntimeError, match="complete Git"):
        build.source_revision(tmp_path)


def test_source_revision_distinguishes_uncommitted_build(tmp_path, monkeypatch):
    monkeypatch.delenv("BUILD_SOURCE_COMMIT", raising=False)
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(128, "git")
    monkeypatch.setattr(build.subprocess, "check_output", fail)
    assert build.source_revision(tmp_path) == "uncommitted-local-build"


def appdir_fixture(tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "dist/Contact-Sheet-Maker").mkdir(parents=True)
    bundle = tmp_path / "dist/Contact-Sheet-Maker"
    (bundle / "Contact-Sheet-Maker").write_bytes(b"native executable")
    (tmp_path / "build/icon.png").write_bytes(b"icon")
    (tmp_path / "packaging/linux").mkdir(parents=True)
    for name in ("AppRun", "contact-sheet-maker.desktop"):
        (tmp_path / "packaging/linux" / name).write_bytes((ROOT / "packaging/linux" / name).read_bytes())
    return bundle


def test_appdir_has_launcher_icon_desktop_and_bundle(tmp_path):
    bundle = appdir_fixture(tmp_path)
    appdir = build.make_appdir(tmp_path, bundle)
    assert (appdir / "usr/lib/contact-sheet-maker/Contact-Sheet-Maker").read_bytes() == b"native executable"
    assert (appdir / "contact-sheet-maker.png").read_bytes() == b"icon"
    assert '"$@"' in (appdir / "AppRun").read_text()
    assert "Icon=contact-sheet-maker" in (appdir / "contact-sheet-maker.desktop").read_text()
    if os.name != "nt":
        assert (appdir / "AppRun").stat().st_mode & stat.S_IXUSR


def test_appimage_refuses_unverified_inputs_before_execution(tmp_path, monkeypatch):
    bundle = appdir_fixture(tmp_path)
    monkeypatch.delenv("APPIMAGETOOL", raising=False)
    monkeypatch.delenv("APPIMAGE_RUNTIME", raising=False)
    with pytest.raises(RuntimeError, match="unverified"):
        build.package_appimage(tmp_path, bundle)
    assert not (tmp_path / "build/Contact-Sheet-Maker.AppDir").exists()


def test_appimage_passes_verified_runtime_and_does_not_download(tmp_path, monkeypatch):
    bundle = appdir_fixture(tmp_path)
    checks, calls = [], []
    monkeypatch.delenv("APPIMAGETOOL", raising=False)
    monkeypatch.delenv("APPIMAGE_RUNTIME", raising=False)
    def verify(*args):
        checks.append(args)
        return True
    def run(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).write_bytes(b"appimage")
    monkeypatch.setattr(build.appimage_inputs, "verify_file", verify)
    monkeypatch.setattr(build.subprocess, "run", run)
    output = build.package_appimage(tmp_path, bundle)
    assert checks[0][1:] == (fetch.SHA256, fetch.SIZE)
    assert checks[1][1:] == (fetch.RUNTIME_SHA256, fetch.RUNTIME_SIZE)
    command, kwargs = calls[0]
    assert command[1] == "--runtime-file"
    assert command[2] == str((tmp_path / "build/tools/runtime-x86_64").resolve())
    assert kwargs["env"]["APPIMAGE_EXTRACT_AND_RUN"] == "1"
    assert kwargs["env"]["ARCH"] == "x86_64" and kwargs["check"] is True
    assert kwargs["timeout"] == 1200 and output.read_bytes() == b"appimage"


@pytest.mark.parametrize("target_platform", ["win32", "linux"])
def test_archives_contain_only_native_bundle_and_checksums(tmp_path, target_platform):
    bundle = tmp_path / "dist/Contact-Sheet-Maker"; bundle.mkdir(parents=True)
    (bundle / "LICENSE").write_text("MIT")
    (tmp_path / "dist/private-photo.png").write_bytes(b"not for upload")
    archive = build.make_archive(tmp_path, target_platform)
    if target_platform == "win32":
        with zipfile.ZipFile(archive) as file:
            names = file.namelist()
    else:
        with tarfile.open(archive) as file:
            names = file.getnames()
    assert "Contact-Sheet-Maker/LICENSE" in names
    assert not any("private-photo" in name for name in names)
    build.write_checksums(tmp_path, [archive])
    line = (tmp_path / "dist/SHA256SUMS.txt").read_text().strip()
    assert line == f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}"


def test_ci_uses_verified_action_pins_and_private_artifact_contract():
    workflow = (ROOT / ".github/workflows/build.yml").read_text()
    actions = re.findall(r"uses: (\S+)", workflow)
    assert set(actions) == {
        "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    }
    assert "contents: read" in workflow and "contents: write" not in workflow
    assert "persist-credentials: false" in workflow and "fail-fast: false" in workflow
    assert "windows-2022" in workflow and "ubuntu-22.04" in workflow
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in workflow and "QT_QPA_PLATFORM: offscreen" in workflow
    assert "--junitxml=artifacts/test-results.xml" in workflow
    assert "APPIMAGE_EXTRACT_AND_RUN=1 python scripts/smoke_bundle.py" in workflow
    assert "retention-days: 14" in workflow and "BUILD_SOURCE_COMMIT" in workflow
    assert "--no-deps --no-build-isolation -e ." in workflow
    assert "timeout-minutes:" in workflow
    assert "pull_request_target" not in workflow and "gh release" not in workflow
    assert "dist/**" not in workflow and "artifacts/**" not in workflow
    assert "artifacts/smoke-*/inputs" not in workflow


def test_appimage_runtime_notice_retained():
    notice = (ROOT / "packaging/linux/APPIMAGE_RUNTIME_LICENSE.txt").read_text()
    assert "Copyright (c) 2004-23 probonopd" in notice
    assert "MIT License" in notice and "libfuse" in notice and "squashfuse" in notice
    assert 'licenses / "APPIMAGE_RUNTIME_LICENSE.txt"' in (ROOT / "scripts/build.py").read_text()
