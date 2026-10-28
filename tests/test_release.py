"""Release safety checks use fake archives and APIs, never a live release."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import subprocess
import tarfile
import tomllib
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
            return ('[project]\nversion="0.1.0b1"\n' if args[1].endswith(":pyproject.toml")
                    else '__version__ = "0.1.0b1"\n')
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
            "application_version": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
            "dependencies": {name: "6.11.2" for name in ["PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6"]}}


def test_application_version_matches_package_metadata():
    from contact_sheet import __version__
    assert __version__ == tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_build_provenance_accepts_current_version_and_rejects_drift():
    value_info = info()
    release.check_build_info(value_info, "a" * 40, "b" * 40, "linux")
    value_info["application_version"] = "0.0.0"
    with pytest.raises(ValueError, match="BUILD-INFO"):
        release.check_build_info(value_info, "a" * 40, "b" * 40, "linux")


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


def candidate_git(project_version="0.1.0b2", application_source='__version__ = "0.1.0b2"'):
    def git(*args):
        if args[0] == "show":
            if args[1].endswith(":pyproject.toml"):
                return f'[project]\nversion="{project_version}"\n'
            return application_source
        return "b" * 40 if "^{tree}" in args[-1] else "a" * 40
    return git


@pytest.mark.parametrize("application_source", [
    '__version__ = "0.1.0b1"', '', '__version__ = "0.1.0b2"\n__version__ = "0.1.0b2"',
    '__version__ = calculate_version()',
])
def test_candidate_rejects_application_version_drift_before_ancestry(application_source, monkeypatch):
    monkeypatch.setattr(release, "git", candidate_git(application_source=application_source))
    monkeypatch.setattr(release.subprocess, "run", lambda *a, **k: pytest.fail("drift reached ancestry check"))
    with pytest.raises(ValueError):
        release.validate_candidate("v0.1.0-beta.2", "a" * 40)


def test_untrusted_source_never_reaches_remote_tag_creation(monkeypatch):
    monkeypatch.setattr(release, "git", candidate_git())
    def fail_ancestry(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(release.subprocess, "run", fail_ancestry)
    monkeypatch.setattr(release, "api", lambda *a, **k: pytest.fail("untrusted source reached GitHub"))
    with pytest.raises(subprocess.CalledProcessError):
        release.init(SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40))


@pytest.mark.parametrize("annotated", [False, True])
def test_existing_reviewed_tag_is_only_verified_never_rewritten(monkeypatch, annotated):
    calls = []
    def api(path, payload=None):
        calls.append((path, payload))
        assert payload is None
        if "/matching-refs/" in path:
            return [{"ref": "refs/tags/v0.1.0-beta.2"}]
        if "/git/ref/" in path and annotated:
            return {"object": {"type": "tag", "sha": "b" * 40}}
        return {"object": {"type": "commit", "sha": "a" * 40}}
    monkeypatch.setattr(release, "api", api)
    release.ensure_remote_tag("v0.1.0-beta.2", "a" * 40)
    assert len(calls) == (3 if annotated else 2)


@pytest.mark.parametrize("prefix_refs", [[], [{"ref": "refs/tags/v0.1.0-beta.20"}]])
def test_missing_reviewed_tag_created_once_then_reread(monkeypatch, prefix_refs):
    calls = []
    def api(path, payload=None):
        calls.append((path, payload))
        if "/matching-refs/" in path:
            return prefix_refs
        if payload is not None:
            assert payload == {"ref": "refs/tags/v0.1.0-beta.2", "sha": "a" * 40}
            return {"ref": payload["ref"]}
        return {"object": {"type": "commit", "sha": "a" * 40}}
    monkeypatch.setattr(release, "api", api)
    release.ensure_remote_tag("v0.1.0-beta.2", "a" * 40)
    assert calls[1][0].endswith("/git/refs")
    assert calls[2][0].endswith("/git/ref/tags/v0.1.0-beta.2")
    assert sum(payload is not None for _, payload in calls) == 1


def test_conflicting_existing_tag_is_never_moved(monkeypatch):
    def api(path, payload=None):
        assert payload is None
        if "/matching-refs/" in path:
            return [{"ref": "refs/tags/v0.1.0-beta.2"}]
        return {"object": {"type": "commit", "sha": "c" * 40}}
    monkeypatch.setattr(release, "api", api)
    with pytest.raises(ValueError, match="moved"):
        release.ensure_remote_tag("v0.1.0-beta.2", "a" * 40)


@pytest.mark.parametrize("remote_commit", ["a" * 40, "c" * 40, None])
def test_tag_creation_error_is_reread_without_retry(monkeypatch, remote_commit):
    calls = []
    def api(path, payload=None):
        calls.append((path, payload))
        if "/matching-refs/" in path:
            return []
        if payload is not None or remote_commit is None:
            raise subprocess.CalledProcessError(1, ["gh", "api", path])
        return {"object": {"type": "commit", "sha": remote_commit}}
    monkeypatch.setattr(release, "api", api)
    if remote_commit == "a" * 40:
        release.ensure_remote_tag("v0.1.0-beta.2", "a" * 40)
    else:
        with pytest.raises(ValueError if remote_commit else subprocess.CalledProcessError):
            release.ensure_remote_tag("v0.1.0-beta.2", "a" * 40)
    assert sum(payload is not None for _, payload in calls) == 1
    assert len(calls) == 3


@pytest.mark.parametrize("response", [None, {}, [None], [{}], [{"ref": None}], [
    {"ref": "refs/tags/v0.1.0-beta.2"}, {"ref": "refs/tags/v0.1.0-beta.2"},
]])
def test_unreadable_tag_inventory_never_means_absent(monkeypatch, response):
    calls = []
    monkeypatch.setattr(release, "api", lambda *args: calls.append(args) or response)
    with pytest.raises(ValueError):
        release.ensure_remote_tag("v0.1.0-beta.2", "a" * 40)
    assert len(calls) == 1


def test_failed_tag_inventory_never_attempts_a_write(monkeypatch):
    calls = []
    def api(path, payload=None):
        calls.append((path, payload))
        raise subprocess.CalledProcessError(1, ["gh", "api", path])
    monkeypatch.setattr(release, "api", api)
    with pytest.raises(subprocess.CalledProcessError):
        release.ensure_remote_tag("v0.1.0-beta.2", "a" * 40)
    assert len(calls) == 1 and calls[0][1] is None


def test_init_validates_source_and_tag_before_draft_release_mutation(tmp_path, monkeypatch):
    args = SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40)
    calls = []
    monkeypatch.setattr(release, "validate_candidate", lambda *a: calls.append("source") or "b" * 40)
    monkeypatch.setattr(release, "ensure_remote_tag", lambda *a: calls.append("tag"))
    def api(path, payload=None):
        calls.append("release-write" if payload else "release-read")
        return {"id": 7} if payload else []
    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(release, "invalidate_receipt", lambda *a: calls.append("invalidate"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    release.init(args)
    assert calls == ["source", "release-read", "tag", "release-write", "invalidate"]


@pytest.mark.parametrize("change", [{"draft": False}, {"target_commitish": "c" * 40}])
def test_init_never_recreates_deleted_tag_of_published_or_unrelated_release(monkeypatch, change):
    args = SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40)
    existing = {"draft": True, "prerelease": True, "tag_name": args.tag, "target_commitish": args.commit}
    existing.update(change)
    monkeypatch.setattr(release, "validate_candidate", lambda *a: "b" * 40)
    monkeypatch.setattr(release, "api", lambda *a: [existing])
    monkeypatch.setattr(release, "ensure_remote_tag", lambda *a: pytest.fail("unrelated release reached tag write"))
    with pytest.raises(ValueError, match="draft prerelease"):
        release.init(args)


def test_malformed_creation_response_is_resolved_by_exact_reread(monkeypatch):
    calls = []
    def api(path, payload=None):
        calls.append((path, payload))
        if "/matching-refs/" in path:
            return []
        if payload is not None:
            raise json.JSONDecodeError("unexpected response", "", 0)
        return {"object": {"type": "commit", "sha": "a" * 40}}
    monkeypatch.setattr(release, "api", api)
    release.ensure_remote_tag("v0.1.0-beta.2", "a" * 40)
    assert len(calls) == 3 and sum(payload is not None for _, payload in calls) == 1


def release_page(page, size=100):
    return [{"tag_name": f"v0.0.{page}-beta.{number}"} for number in range(size)]


def test_published_release_on_second_page_blocks_any_tag_write(monkeypatch):
    args = SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40)
    published = {"tag_name": args.tag, "target_commitish": args.commit, "draft": False, "prerelease": True}
    calls = []
    def api(path, payload=None):
        calls.append(path)
        assert payload is None
        return release_page(1) if path.endswith("page=1") else [published]
    monkeypatch.setattr(release, "validate_candidate", lambda *a: "b" * 40)
    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(release, "ensure_remote_tag", lambda *a: pytest.fail("published release reached tag write"))
    with pytest.raises(ValueError, match="draft prerelease"):
        release.init(args)
    assert len(calls) == 2 and calls[-1].endswith("page=2")


@pytest.mark.parametrize("full_pages,last_size", [(1, 0), (2, 0), (2, 3)])
def test_absent_release_exhausts_later_pages_before_tag_write(tmp_path, monkeypatch, full_pages, last_size):
    args = SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40)
    calls = []
    def api(path, payload=None):
        if payload is not None:
            calls.append("create-draft")
            return {"id": 7}
        page = int(path.rsplit("page=", 1)[1])
        calls.append(page)
        return release_page(page, 100 if page <= full_pages else last_size)
    monkeypatch.setattr(release, "validate_candidate", lambda *a: "b" * 40)
    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(release, "ensure_remote_tag", lambda *a: calls.append("tag"))
    monkeypatch.setattr(release, "invalidate_receipt", lambda *a: None)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    release.init(args)
    assert calls == [*range(1, full_pages + 2), "tag", "create-draft"]


@pytest.mark.parametrize("response", [None, {}, [None], [{}], [{"tag_name": None}], release_page(2, 101)])
def test_malformed_later_release_page_never_means_absent(monkeypatch, response):
    args = SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40)
    calls = []
    def api(path, payload=None):
        calls.append(path)
        assert payload is None
        return release_page(1) if path.endswith("page=1") else response
    monkeypatch.setattr(release, "validate_candidate", lambda *a: "b" * 40)
    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(release, "ensure_remote_tag", lambda *a: pytest.fail("unreadable page reached tag write"))
    with pytest.raises(ValueError, match="release inventory"):
        release.init(args)
    assert len(calls) == 2


def test_failed_later_release_page_never_means_absent(monkeypatch):
    args = SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40)
    def api(path, payload=None):
        assert payload is None
        if path.endswith("page=1"):
            return release_page(1)
        raise subprocess.CalledProcessError(1, ["gh", "api", path])
    monkeypatch.setattr(release, "validate_candidate", lambda *a: "b" * 40)
    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(release, "ensure_remote_tag", lambda *a: pytest.fail("failed page reached tag write"))
    with pytest.raises(subprocess.CalledProcessError):
        release.init(args)


def test_duplicate_release_across_pages_blocks_tag_write(monkeypatch):
    args = SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40)
    draft = {"id": 7, "tag_name": args.tag, "target_commitish": args.commit, "draft": True, "prerelease": True}
    def api(path, payload=None):
        assert payload is None
        return [draft, *release_page(1, 99)] if path.endswith("page=1") else [draft]
    monkeypatch.setattr(release, "validate_candidate", lambda *a: "b" * 40)
    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(release, "ensure_remote_tag", lambda *a: pytest.fail("ambiguous release reached tag write"))
    with pytest.raises(ValueError, match="Multiple releases"):
        release.init(args)


def test_existing_draft_on_second_page_is_reused_after_full_inventory(tmp_path, monkeypatch):
    args = SimpleNamespace(tag="v0.1.0-beta.2", commit="a" * 40)
    draft = {"id": 7, "tag_name": args.tag, "target_commitish": args.commit, "draft": True, "prerelease": True}
    calls = []
    def api(path, payload=None):
        assert payload is None
        calls.append("page1" if path.endswith("page=1") else "page2")
        return release_page(1) if path.endswith("page=1") else [draft]
    monkeypatch.setattr(release, "validate_candidate", lambda *a: "b" * 40)
    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(release, "ensure_remote_tag", lambda *a: calls.append("tag"))
    monkeypatch.setattr(release, "invalidate_receipt", lambda *a: calls.append("invalidate"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    release.init(args)
    assert calls == ["page1", "page2", "tag", "invalidate"]
    assert args.release_id == "7"
