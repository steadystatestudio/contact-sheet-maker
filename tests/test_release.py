"""Release safety checks use fake archives and APIs, never a live release."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load("release")
sources = load("fetch_release_sources")


@pytest.mark.parametrize("change", [{"draft": False}, {"prerelease": False}, {"tag_name": "v1.0.0"}, {"target_commitish": "main"}])
def test_published_or_wrong_release_is_never_mutated(change):
    value = {"draft": True, "prerelease": True, "tag_name": "v0.1.0-beta.1", "target_commitish": "a" * 40}
    value.update(change)
    with pytest.raises(ValueError, match="draft prerelease"):
        release.validate_draft(value, "v0.1.0-beta.1", "a" * 40)


def test_candidate_requires_matching_tag_version_and_main_ancestor(monkeypatch):
    def git(*args):
        if args[0] == "show":
            return '[project]\nversion="0.1.0b1"\n'
        return "b" * 40 if "^{tree}" in args[-1] else "a" * 40
    calls = []
    monkeypatch.setattr(release, "git", git)
    monkeypatch.setattr(release.subprocess, "run", lambda command, **kwargs: calls.append(command))
    assert release.validate_candidate("v0.1.0-beta.1", "a" * 40) == "b" * 40
    assert calls[0][-2:] == ["a" * 40, "origin/main"]
    with pytest.raises(ValueError, match="version"):
        release.validate_candidate("v0.1.0-beta.2", "a" * 40)
    with pytest.raises(ValueError, match="expected commit"):
        release.validate_candidate("v0.1.0-beta.1", "c" * 40)


@pytest.mark.parametrize("tag,commit", [("main", "a" * 40), ("v1.0.0", "a" * 40), ("v0.1.0-beta.1;evil", "a" * 40), ("v0.1.0-beta.1", "main")])
def test_invalid_candidate_never_invokes_git(tag, commit, monkeypatch):
    monkeypatch.setattr(release, "git", lambda *args: pytest.fail("invalid input reached Git"))
    with pytest.raises(ValueError):
        release.validate_candidate(tag, commit)


def test_qa_archive_excludes_inputs_preferences_and_other_local_files(tmp_path):
    paths = ["test-results.xml", "smoke-win/result.json", "smoke-win/process.log", "smoke-win/ui.png",
             "smoke-win/outputs/sheets.pdf", "smoke-win/inputs/private.jpg", "smoke-win/smoke-settings.ini", "personal.txt"]
    for name in paths:
        path = tmp_path / "artifacts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    archive = release.qa_archive(tmp_path / "artifacts", tmp_path / "qa.zip")
    with zipfile.ZipFile(archive) as file:
        assert set(file.namelist()) == set(paths[:5])


def make_tar(path, name, *, link=None):
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo(name)
        if link is not None:
            member.type = tarfile.SYMTYPE
            member.linkname = link
            archive.addfile(member)
        else:
            member.size = 4
            archive.addfile(member, io.BytesIO(b"test"))


@pytest.mark.parametrize("name,link", [("../escape", None), ("Other/file", None), ("Contact-Sheet-Maker/../escape", None), ("Contact-Sheet-Maker/link", "../escape")])
def test_untrusted_archive_cannot_escape_bundle(tmp_path, name, link):
    archive = tmp_path / "archive.tar.gz"
    make_tar(archive, name, link=link)
    with pytest.raises(ValueError, match="archive"):
        release.extract_bundle(archive, tmp_path / "candidate")
    assert not (tmp_path / "escape").exists()


def test_portable_archive_can_be_extracted(tmp_path):
    archive = tmp_path / "archive.tar.gz"
    make_tar(archive, "Contact-Sheet-Maker/BUILD-INFO.json")
    release.extract_bundle(archive, tmp_path / "candidate")
    assert (tmp_path / "candidate/Contact-Sheet-Maker/BUILD-INFO.json").read_bytes() == b"test"


def info():
    return {"source_commit": "a" * 40, "source_tree": "b" * 40, "platform": "linux", "qt_runtime": "6.11.2",
            "application_version": "0.1.0b1",
            "dependencies": {name: "6.11.2" for name in ["PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6"]}}


@pytest.mark.parametrize("field,value", [("source_commit", "c" * 40), ("source_tree", None), ("platform", "win32"), ("qt_runtime", "6.12.0")])
def test_build_provenance_mismatch_stops_verification(field, value):
    value_info = info()
    value_info[field] = value
    with pytest.raises(ValueError, match="BUILD-INFO"):
        release.check_build_info(value_info, "a" * 40, "b" * 40, "linux")


def test_sources_match_all_four_locked_distributions():
    index = sources.source_index()
    assert len(index["archives"]) == 5
    assert "shiboken6" in index["archives"][1]["covers"]
    assert index["archives"][0]["size"] == 1019661552
    assert all(item["url"].startswith("https://") for item in index["archives"])


def test_source_version_drift_fails_closed(tmp_path):
    (tmp_path / "packaging").mkdir()
    (tmp_path / "packaging/source-archives.json").write_text((ROOT / "packaging/source-archives.json").read_text())
    (tmp_path / "requirements-build-lock.txt").write_text("PySide6==6.12.0\n")
    with pytest.raises(ValueError, match="dependency lock"):
        sources.source_index(tmp_path)


class Response(io.BytesIO):
    def geturl(self):
        return "https://download.qt.io/fixture"


@pytest.mark.parametrize("body", [b"bad", b"toolong"])
def test_changed_source_bytes_never_replace_existing_file(tmp_path, monkeypatch, body):
    target = tmp_path / "source.tar.xz"
    target.write_bytes(b"old")
    monkeypatch.setattr(sources.urllib.request, "urlopen", lambda *a, **k: Response(body))
    item = {"name": target.name, "url": "https://download.qt.io/fixture", "size": 4, "sha256": hashlib.sha256(b"good").hexdigest()}
    with pytest.raises(RuntimeError, match="checksum|pinned size"):
        sources.download(item, tmp_path)
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob("*.download"))


def test_beta_workflow_is_manual_exact_sha_staging_only():
    text = (ROOT / ".github/workflows/release-beta.yml").read_text()
    assert "workflow_dispatch:" in text and "expected_commit:" in text
    assert "github.repository == 'steadystatestudio/contact-sheet-maker'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "pull_request" not in text and "push:" not in text
    assert "upload-artifact" not in text and "download-artifact" not in text
    assert "verify-linux" in text and "ubuntu-24.04" in text
    assert "fetch_release_sources.py" in text and "release.py finalize" in text
    assert "--draft=false" not in text and "publish:" not in text
    assert all(re.fullmatch(r"actions/(checkout|setup-python)@[0-9a-f]{40}", item)
               for item in re.findall(r"uses: (\S+)", text))


def test_another_run_cannot_supply_pass_receipt(monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "20")
    args = SimpleNamespace(commit="a" * 40, tree="b" * 40)
    receipt = {"source_commit": args.commit, "source_tree": args.tree, "platform": "Linux", "run_id": "19"}
    with pytest.raises(ValueError, match="workflow run"):
        release.check_receipt(receipt, args, "Linux")


@pytest.mark.parametrize("annotated", [False, True])
def test_remote_tag_is_rechecked_and_annotated_tags_are_peeled(monkeypatch, annotated):
    calls = []
    def api(path):
        calls.append(path)
        if "/git/ref/" in path and annotated:
            return {"object": {"type": "tag", "sha": "b" * 40}}
        return {"object": {"type": "commit", "sha": "a" * 40}}
    monkeypatch.setattr(release, "api", api)
    release.verify_remote_tag("v0.1.0-beta.1", "a" * 40)
    assert len(calls) == (2 if annotated else 1)
    with pytest.raises(ValueError, match="moved"):
        release.verify_remote_tag("v0.1.0-beta.1", "c" * 40)


@pytest.mark.parametrize("names", [["package.zip", "unreviewed.txt"], [], ["package.zip", "package.zip"]])
def test_unreviewed_extra_missing_and_duplicate_assets_block_ready_receipt(names):
    with pytest.raises(ValueError, match="asset set"):
        release.check_asset_set([{"name": name} for name in names], [{"name": "package.zip"}])


def test_exact_asset_set_allows_only_prior_ready_receipt():
    release.check_asset_set([{"name": "package.zip"}, {"name": "RELEASE-READY.json"}], [{"name": "package.zip"}])
