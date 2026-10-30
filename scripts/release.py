"""Stage and verify a manual release candidate. This tool never publishes a release.

The reviewed workflow may create a missing stable or beta tag after source validation;
existing tags are never moved. All release-asset operations require the selected
exact-commit draft with the tag's matching release channel. No personal settings
or input photos are included in QA archives. Run only from the reviewed release workflow.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "steadystatestudio/contact-sheet-maker"
PLATFORMS = ("Windows", "Linux", "Sources", "Ubuntu24")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def tag_version(tag: str) -> tuple[str, bool]:
    """Return canonical package version and prerelease flag; reject other refs."""
    number = r"(?:0|[1-9][0-9]*)"
    match = re.fullmatch(rf"v({number}\.{number}\.{number})(?:-beta\.([1-9][0-9]*))?", tag)
    if not match:
        raise ValueError("Use a vX.Y.Z or vX.Y.Z-beta.N tag")
    return (f"{match[1]}b{match[2]}", True) if match[2] else (match[1], False)


def validate_candidate(tag: str, commit: str) -> str:
    expected_version, _ = tag_version(tag)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected commit must be a complete lowercase Git SHA")
    if git("rev-parse", "--verify", f"{commit}^{{commit}}") != commit:
        raise ValueError("Source does not match the expected commit")
    project = tomllib.loads(git("show", f"{commit}:pyproject.toml"))
    module = ast.parse(git("show", f"{commit}:src/contact_sheet/__init__.py"))
    versions = [node.value for node in module.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
    if (project["project"]["version"] != expected_version or len(versions) != 1
            or ast.literal_eval(versions[0]) != expected_version):
        raise ValueError("Release tag does not match the application version")
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], cwd=ROOT, check=True)
    return git("rev-parse", f"{commit}^{{tree}}")


def api(path: str, payload=None):
    command = ["gh", "api", path]
    if payload is not None:
        command += ["--method", "POST", "--input", "-"]
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def validate_draft(release: dict, tag: str, commit: str) -> None:
    _, prerelease = tag_version(tag)
    if (release.get("draft") is not True or release.get("prerelease") is not prerelease
            or release.get("tag_name") != tag or release.get("target_commitish") != commit):
        raise ValueError("Refusing to modify anything except the selected exact-commit draft with matching release channel")


def verify_remote_tag(tag: str, commit: str) -> None:
    """Re-read GitHub's ref and peel annotated tags after a potentially long build."""
    obj = api(f"repos/{REPOSITORY}/git/ref/tags/{tag}")["object"]
    for _ in range(10):
        if obj.get("type") == "commit":
            if obj.get("sha") != commit:
                raise ValueError("Remote release tag moved away from the reviewed commit")
            return
        if obj.get("type") != "tag" or not re.fullmatch(r"[0-9a-f]{40}", obj.get("sha", "")):
            break
        obj = api(f"repos/{REPOSITORY}/git/tags/{obj['sha']}")["object"]
    raise ValueError("Remote release tag does not resolve to a commit")


def ensure_remote_tag(tag: str, commit: str) -> None:
    """Create only a missing reviewed tag; existing tags are never moved."""
    target = f"refs/tags/{tag}"
    refs = api(f"repos/{REPOSITORY}/git/matching-refs/tags/{tag}")
    if (not isinstance(refs, list) or any(not isinstance(ref, dict)
            or not isinstance(ref.get("ref"), str) for ref in refs)):
        raise ValueError("Cannot establish whether the reviewed release tag exists")
    matches = [ref for ref in refs if ref["ref"] == target]
    if len(matches) > 1:
        raise ValueError("Duplicate release tag refs in GitHub response")
    if not matches:
        try:
            api(f"repos/{REPOSITORY}/git/refs", {"ref": target, "sha": commit})
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            # A concurrent creator or an uncertain response may have completed
            # the one write. Reread rather than retrying or moving any tag.
            verify_remote_tag(tag, commit)
            return
    verify_remote_tag(tag, commit)


def current_release(args) -> dict:
    release = api(f"repos/{REPOSITORY}/releases/{args.release_id}")
    validate_draft(release, args.tag, args.commit)
    return release


def invalidate_receipt(args) -> None:
    release = current_release(args)
    for asset in release.get("assets", []):
        if asset["name"] == "RELEASE-READY.json":
            subprocess.run(["gh", "api", "--method", "DELETE",
                            f"repos/{REPOSITORY}/releases/assets/{asset['id']}"], check=True)


def upload(args, paths: list[Path]) -> None:
    current_release(args)
    subprocess.run(["gh", "release", "upload", args.tag, "--repo", REPOSITORY,
                    "--clobber", *[str(path) for path in paths]], check=True)


def json_file(path: Path, content) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def file_record(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing or unsafe release asset: {path.name}")
    return {"name": path.name, "size": path.stat().st_size, "sha256": digest(path)}


def qa_archive(artifacts: Path, target: Path) -> Path:
    """Allowlist synthetic QA outputs; exclude input photos and local settings."""
    candidates = [artifacts / "test-results.xml"]
    for pattern in ("smoke-*/result.json", "smoke-*/process.log", "smoke-*/ui*.png",
                    "smoke-*/outputs/*.pdf", "smoke-*/outputs/*.jpg"):
        candidates.extend(artifacts.glob(pattern))
    files = sorted({path for path in candidates if path.is_file() and not path.is_symlink()})
    if not files:
        raise ValueError("No QA evidence to retain")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(artifacts).as_posix())
    return target


def check_build_info(info: dict, commit: str, tree: str, platform: str) -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if (info.get("source_commit") != commit or info.get("source_tree") != tree
            or info.get("platform") != platform or info.get("qt_runtime") != "6.11.2"
            or info.get("application_version") != version):
        raise ValueError("BUILD-INFO does not match the tested source/platform/Qt version")
    for name in ("PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6"):
        if info.get("dependencies", {}).get(name) != "6.11.2":
            raise ValueError("BUILD-INFO dependencies do not match retained sources")


def matching_releases(tag: str) -> list[dict]:
    """Exhaust the authenticated release inventory before treating a tag as new."""
    matches = []
    page = 1
    while True:
        releases = api(f"repos/{REPOSITORY}/releases?per_page=100&page={page}")
        if (not isinstance(releases, list) or len(releases) > 100
                or any(not isinstance(item, dict) or not isinstance(item.get("tag_name"), str)
                       for item in releases)):
            raise ValueError("Cannot establish the complete release inventory")
        matches.extend(item for item in releases if item["tag_name"] == tag)
        if len(releases) < 100:
            return matches
        page += 1


def init(args) -> None:
    tree = validate_candidate(args.tag, args.commit)
    _, prerelease = tag_version(args.tag)
    matches = matching_releases(args.tag)
    if len(matches) > 1:
        raise ValueError("Multiple releases refer to the reviewed release tag")
    if matches:
        release = matches[0]
        # Never recreate a deleted tag belonging to a published or unrelated
        # release, which could silently change its public source association.
        validate_draft(release, args.tag, args.commit)
    ensure_remote_tag(args.tag, args.commit)
    if not matches:
        release = api(f"repos/{REPOSITORY}/releases", {
            "tag_name": args.tag, "target_commitish": args.commit, "draft": True,
            "prerelease": prerelease, "name": f"Contact Sheet Maker {args.tag}" + (" (beta)" if prerelease else ""),
            "body": "Draft release candidate. Do not publish until RELEASE-READY.json exists and "
                    "privacy, donation destination, native review and product-maturity gates are resolved. "
                    "All features are free. Packages are unsigned. This workflow never publishes.",
        })
    args.release_id = str(release["id"])
    invalidate_receipt(args)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(f"release_id={args.release_id}\ncommit={args.commit}\ntree={tree}\n")


def stage(args) -> None:
    invalidate_receipt(args)
    output = ROOT / "dist/release-stage"
    output.mkdir(parents=True, exist_ok=True)
    files = []
    inputs = {}
    if args.platform in {"Windows", "Linux"}:
        bundle = ROOT / "dist/Contact-Sheet-Maker"
        info = json.loads((bundle / "BUILD-INFO.json").read_text(encoding="utf-8"))
        check_build_info(info, args.commit, args.tree, "win32" if args.platform == "Windows" else "linux")
        names = ["Contact-Sheet-Maker-windows-x86_64.zip"] if args.platform == "Windows" else [
            "Contact-Sheet-Maker-linux-x86_64.tar.gz", "Contact-Sheet-Maker-x86_64.AppImage"]
        files.extend(ROOT / "dist" / name for name in names)
        files.append(json_file(output / f"BUILD-INFO-{args.platform}.json", info))
        files.append(qa_archive(ROOT / "artifacts", output / f"QA-{args.platform}.zip"))
    elif args.platform == "Sources":
        from fetch_release_sources import source_index
        index = source_index()
        files.extend(ROOT / "dist/release-sources" / item["name"] for item in index["archives"])
        for item, path in zip(index["archives"], files):
            if file_record(path) != {key: item[key] for key in ("name", "size", "sha256")}:
                raise ValueError("Retained sources differ from pinned sources")
        files.append(ROOT / "dist/release-sources/SOURCE-INDEX.json")
    else:
        files.append(qa_archive(ROOT / "artifacts", output / "QA-Ubuntu24.zip"))
        inputs["RELEASE-Linux.json"] = digest(ROOT / "candidate/RELEASE-Linux.json")
    records = [file_record(path) for path in files]
    checksums = output / f"SHA256SUMS-{args.platform}.txt"
    checksums.write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in records), encoding="ascii")
    files.append(checksums)
    records.append(file_record(checksums))
    receipt = json_file(output / f"RELEASE-{args.platform}.json", {
        "source_commit": args.commit, "source_tree": args.tree, "platform": args.platform,
        "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "files": records, "verified_inputs": inputs,
    })
    upload(args, files)
    upload(args, [receipt])  # A receipt is retained only after all of its files.


def download_assets(args, names: list[str], destination: Path) -> None:
    current_release(args)
    destination.mkdir(parents=True, exist_ok=True)
    command = ["gh", "release", "download", args.tag, "--repo", REPOSITORY, "--dir", str(destination)]
    for name in names:
        if Path(name).name != name or "/" in name or "\\" in name or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Unsafe release asset name")
        command += ["--pattern", name]
    subprocess.run(command, check=True)


def check_receipt(receipt: dict, args, platform: str) -> None:
    if (receipt.get("source_commit") != args.commit or receipt.get("source_tree") != args.tree
            or receipt.get("platform") != platform or receipt.get("run_id") != os.environ.get("GITHUB_RUN_ID")):
        raise ValueError("Release evidence belongs to another source, platform or workflow run")
    expected = {f"SHA256SUMS-{platform}.txt"}
    if platform == "Windows":
        expected |= {"Contact-Sheet-Maker-windows-x86_64.zip", "BUILD-INFO-Windows.json", "QA-Windows.zip"}
    elif platform == "Linux":
        expected |= {"Contact-Sheet-Maker-linux-x86_64.tar.gz", "Contact-Sheet-Maker-x86_64.AppImage", "BUILD-INFO-Linux.json", "QA-Linux.zip"}
    elif platform == "Sources":
        from fetch_release_sources import source_index
        expected |= {"SOURCE-INDEX.json", *[item["name"] for item in source_index()["archives"]]}
    else:
        expected.add("QA-Ubuntu24.zip")
    names = [item["name"] for item in receipt.get("files", [])]
    if len(names) != len(set(names)) or set(names) != expected:
        raise ValueError("Release receipt has missing, duplicate or unexpected assets")


def check_asset_set(assets: list[dict], records: list[dict]) -> None:
    names = [asset["name"] for asset in assets]
    required = {item["name"] for item in records}
    if (len(names) != len(set(names)) or len(records) != len(required)
            or set(names) - {"RELEASE-READY.json"} != required):
        raise ValueError("Draft asset set contains missing, duplicate or unreviewed extra files")


def extract_bundle(archive_path: Path, directory: Path) -> None:
    expected = (directory / "Contact-Sheet-Maker").resolve()
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            parts = member.name.split("/")
            if parts[0] != "Contact-Sheet-Maker" or ".." in parts or "\\" in member.name:
                raise ValueError("Unexpected path in portable archive")
            if member.issym() or member.islnk():
                base = directory / Path(member.name).parent if member.issym() else directory
                if not (base / member.linkname).resolve().is_relative_to(expected):
                    raise ValueError("Portable archive link escapes its bundle")
        archive.extractall(directory, filter="data")


def verify_linux(args) -> None:
    directory = ROOT / "candidate"
    download_assets(args, ["RELEASE-Linux.json"], directory)
    receipt = json.loads((directory / "RELEASE-Linux.json").read_text(encoding="utf-8"))
    check_receipt(receipt, args, "Linux")
    download_assets(args, [item["name"] for item in receipt["files"]], directory)
    for item in receipt["files"]:
        if file_record(directory / item["name"]) != item:
            raise ValueError("Retained Linux package checksum mismatch")
    extract_bundle(directory / "Contact-Sheet-Maker-linux-x86_64.tar.gz", directory)
    info_path = directory / "Contact-Sheet-Maker/BUILD-INFO.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    check_build_info(info, args.commit, args.tree, "linux")
    if info != json.loads((directory / "BUILD-INFO-Linux.json").read_text(encoding="utf-8")):
        raise ValueError("Archive BUILD-INFO differs from retained provenance")


def finalize(args) -> None:
    verify_remote_tag(args.tag, args.commit)
    directory = ROOT / "dist/release-final"
    names = [f"RELEASE-{platform}.json" for platform in PLATFORMS]
    download_assets(args, names, directory)
    release = current_release(args)
    assets = {asset["name"]: asset for asset in release["assets"]}
    records = []
    for platform in PLATFORMS:
        path = directory / f"RELEASE-{platform}.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        check_receipt(receipt, args, platform)
        if platform == "Ubuntu24" and receipt["verified_inputs"].get("RELEASE-Linux.json") != digest(directory / "RELEASE-Linux.json"):
            raise ValueError("Ubuntu24 did not test the currently retained Linux build")
        for item in [*receipt["files"], file_record(path)]:
            asset = assets.get(item["name"], {})
            if asset.get("state") != "uploaded" or asset.get("size") != item["size"] or asset.get("digest") != f"sha256:{item['sha256']}":
                raise ValueError(f"GitHub asset digest does not match verified evidence: {item['name']}")
            records.append(item)
    check_asset_set(release["assets"], records)
    verify_remote_tag(args.tag, args.commit)
    ready = json_file(directory / "RELEASE-READY.json", {
        "status": "automated-checks-passed-awaiting-publication-review", "draft": True,
        "prerelease": tag_version(args.tag)[1],
        "source_commit": args.commit, "source_tree": args.tree, "tag": args.tag,
        "run_id": os.environ.get("GITHUB_RUN_ID"), "files": records,
        "checks": ["Windows native tests/build/smoke", "Ubuntu22 native tests/build/bundle and AppImage smoke",
                   "Ubuntu24 exact retained Linux bytes and BUILD-INFO verified and smoke-tested",
                   "matching Qt/PySide/Shiboken source archives retained and digest-verified"],
        "remaining_review": ["public identity and binary metadata", "donation checkout and receipts",
                             "native interactive review", "five-user criteria before 1.0 or explicit product-maturity decision"],
        "user_observation_gate": "Not evaluated by automation; requires separate evidence or an explicit product-maturity decision.",
    })
    upload(args, [ready])
    print("Automated gates passed. The release remains a draft; publication is a separate reviewed action.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "stage", "verify-linux", "finalize"])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tree")
    parser.add_argument("--release-id", type=int)
    parser.add_argument("--platform", choices=PLATFORMS)
    args = parser.parse_args(argv)
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("Release staging is restricted to the Studio repository")
    if args.command != "init" and (not args.release_id or not args.tree):
        parser.error("This operation requires --release-id and --tree")
    if args.command == "stage" and not args.platform:
        parser.error("Staging requires --platform")
    {"init": init, "stage": stage, "verify-linux": verify_linux, "finalize": finalize}[args.command](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
