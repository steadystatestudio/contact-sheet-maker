"""Exercise the pinned PyInstaller policy and safe prerequisite manifest."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PyInstaller.building.build_main import Analysis

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("linux_dependencies", ROOT / "scripts/linux_dependencies.py")
dependencies = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dependencies)


def test_official_policy_preserves_python_and_wheels_and_records_os_dependencies(tmp_path, monkeypatch):
    class Candidate:
        exclude_system_libraries = Analysis.exclude_system_libraries
        binaries = [
            ("libglib-2.0.so.0", "/usr/lib/x86_64-linux-gnu/libglib-2.0.so.0", "BINARY"),
            ("libdbus-1.so.3", "/lib/x86_64-linux-gnu/libdbus-1.so.3", "BINARY"),
            ("libpython3.12.so.1.0", "/usr/lib/libpython3.12.so.1.0", "BINARY"),
            ("python3.12/lib-dynload/_ssl.so", "/usr/lib/python3.12/lib-dynload/_ssl.so", "EXTENSION"),
            ("PySide6/Qt/lib/libQt6Core.so.6", "/opt/venv/PySide6/Qt/lib/libQt6Core.so.6", "BINARY"),
            ("pillow.libs/libjpeg-custom.so", "/opt/venv/pillow.libs/libjpeg-custom.so", "BINARY"),
        ]
    candidate = Candidate()
    retained = candidate.binaries[2:]
    monkeypatch.setattr(dependencies, "package_owner", lambda source: "libglib2.0-0" if "glib" in source else "libdbus-1-3")
    manifest = tmp_path / "LINUX-SYSTEM-DEPENDENCIES.json"
    dependencies.omit_system_libraries(candidate, manifest)
    assert candidate.binaries == retained
    info = json.loads(manifest.read_text())
    assert info["packages"] == ["libdbus-1-3", "libglib2.0-0"]
    assert {entry["library"] for entry in info["libraries"]} == {"libglib-2.0.so.0", "libdbus-1.so.3"}
    assert "/opt/" not in manifest.read_text() and "/usr/lib/" not in manifest.read_text()


@pytest.mark.parametrize("packages", [[], ["--option"], ["libfoo;echo secret"], ["../../bad"], "libfoo", [None]])
def test_prerequisite_install_rejects_non_package_arguments(tmp_path, monkeypatch, packages):
    manifest = tmp_path / "dependencies.json"
    manifest.write_text(json.dumps({"packages": packages}))
    monkeypatch.setattr(dependencies.subprocess, "run", lambda *a, **k: pytest.fail("Unsafe package install executed"))
    with pytest.raises(ValueError, match="Invalid system"):
        dependencies.install_prerequisites(manifest)


def test_prerequisite_install_uses_structured_arguments(tmp_path, monkeypatch):
    manifest = tmp_path / "dependencies.json"
    manifest.write_text(json.dumps({"packages": ["libdbus-1-3", "libssl3"]}))
    calls = []
    monkeypatch.setattr(dependencies.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    dependencies.install_prerequisites(manifest)
    assert calls == [(["sudo", "apt-get", "install", "--no-install-recommends", "-y", "libdbus-1-3", "libssl3"], {"check": True})]
