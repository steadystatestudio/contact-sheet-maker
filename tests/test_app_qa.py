"""An interactive QA launch must not reuse ordinary user preferences."""
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from contact_sheet import app as startup


def test_qa_preferences_are_explicit_ini_without_fallbacks(tmp_path):
    directory = tmp_path / "fresh"
    settings = startup._qa_settings(str(directory))
    assert settings.format() == QSettings.IniFormat
    assert Path(settings.fileName()) == directory / "settings.ini"
    assert not settings.fallbacksEnabled()
    settings.setValue("layout", "synthetic QA")
    settings.sync()
    assert (directory / "settings.ini").is_file()


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_qa_refuses_existing_target_without_changing_it(tmp_path, kind):
    target = tmp_path / "occupied"
    if kind == "directory":
        target.mkdir()
        sentinel = target / "keep.txt"
    else:
        sentinel = target
    sentinel.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        startup._qa_settings(str(target))
    assert sentinel.read_text(encoding="utf-8") == "original"


def test_qa_refuses_missing_parent_and_traversal(tmp_path):
    with pytest.raises(FileNotFoundError):
        startup._qa_settings(str(tmp_path / "absent" / "fresh"))
    with pytest.raises(ValueError, match="traversal"):
        startup._qa_settings(str(tmp_path / ".." / "fresh"))


@pytest.mark.parametrize("target_exists", [False, True])
def test_qa_refuses_linked_ancestors_and_target(tmp_path, target_exists):
    actual = tmp_path / "actual"
    if target_exists:
        actual.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("Host cannot create symlinks without elevated rights")
    with pytest.raises(ValueError, match="links"):
        startup._qa_settings(str(alias))
    with pytest.raises(ValueError, match="links"):
        startup._qa_settings(str(alias / "fresh"))
    assert not (actual / "fresh").exists()


def test_qa_launch_injects_preferences_and_runs_normal_event_loop(tmp_path, monkeypatch):
    calls = []

    class Application:
        def __init__(self, args):
            pass
        def setApplicationName(self, value):
            pass
        def setOrganizationName(self, value):
            pass
        def setApplicationVersion(self, value):
            pass
        def setStyle(self, value):
            pass
        def exec(self):
            calls.append("event loop")
            return 0

    class Window:
        def __init__(self, settings):
            calls.append(Path(settings.fileName()))
        def show(self):
            calls.append("show")

    monkeypatch.setattr(startup, "QApplication", Application)
    from contact_sheet import system_fonts
    monkeypatch.setattr(system_fonts, "capture_system_appearance", lambda app: {})
    monkeypatch.setattr(startup, "MainWindow", Window)
    target = tmp_path / "interactive"
    monkeypatch.setattr(startup.sys, "argv", ["contact-sheet", "--qa-ui", str(target)])
    assert startup.main() == 0
    assert calls == [target / "settings.ini", "show", "event loop"]
