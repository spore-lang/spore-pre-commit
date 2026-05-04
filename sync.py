# /// script
# requires-python = ">=3.13"
# dependencies = ["packaging>=24.0"]
# ///
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import tomllib
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"

PACKAGE_NAME = os.environ.get("SPORE_PACKAGE_NAME", "spore-lang")
TARGET_BRANCH = os.environ.get("TARGET_BRANCH", "main")
REMOTE_NAME = os.environ.get("TARGET_REMOTE", "origin")
PYPI_JSON_URL = os.environ.get(
    "SPORE_PYPI_JSON_URL",
    f"https://pypi.org/pypi/{PACKAGE_NAME}/json",
)
MIRROR_SOURCE_URL_TEMPLATE = os.environ.get(
    "SPORE_MIRROR_SOURCE_URL_TEMPLATE",
    f"https://pypi.org/project/{PACKAGE_NAME}/{{version}}/",
)

BOOTSTRAP_VERSION = Version("0.0.0")


def main() -> None:
    current_version = read_current_version()
    maybe_publish_current_tag(current_version)
    versions = find_new_versions(current_version)
    if not versions:
        print("No new stable releases to mirror.")
        return

    for index, version in enumerate(versions):
        full_tag_name = version_tag_names(version)[-1]
        if remote_tag_exists(full_tag_name):
            print(f"Skipping existing tag {full_tag_name}.")
            continue

        changed_paths = update_files(version)
        if not changed_paths:
            print(f"No file changes for {full_tag_name}; skipping.")
            continue

        git(["add", *changed_paths])
        git(["commit", "-m", f"🔄 chore: mirror {PACKAGE_NAME} {full_tag_name}"])
        publish_tag_set_and_release(
            version,
            push_head=True,
            latest=index == len(versions) - 1,
        )


def read_current_version() -> Version:
    with PYPROJECT.open("rb") as handle:
        pyproject = tomllib.load(handle)

    requirement = Requirement(pyproject["project"]["dependencies"][0])
    specifier = next(iter(requirement.specifier), None)
    if specifier is None or specifier.operator != "==":
        raise RuntimeError(f"Expected an exact {PACKAGE_NAME} pin in pyproject.toml.")
    return Version(specifier.version)


def find_new_versions(current_version: Version) -> list[Version]:
    try:
        payload = json.loads(fetch_text(PYPI_JSON_URL))
    except HTTPError as error:
        if error.code == 404 and current_version == BOOTSTRAP_VERSION:
            print(f"{PACKAGE_NAME} is not on PyPI yet; bootstrap state unchanged.")
            return []
        raise

    versions = []
    for raw_version in payload["releases"]:
        version = Version(raw_version)
        if version <= current_version or version.is_prerelease:
            continue
        versions.append(version)
    return sorted(versions)


def update_files(version: Version) -> tuple[str, ...]:
    changed_paths: list[str] = []

    pyproject_before = PYPROJECT.read_text()
    pyproject_after = replace_exact(
        pyproject_before,
        r'(?m)^version = ".*"$',
        f'version = "{version}"',
    )
    pyproject_after = replace_exact(
        pyproject_after,
        rf'"{re.escape(PACKAGE_NAME)}==[^"]+"',
        f'"{PACKAGE_NAME}=={version}"',
    )
    if pyproject_after != pyproject_before:
        PYPROJECT.write_text(pyproject_after)
        changed_paths.append(PYPROJECT.name)

    readme_before = README.read_text()
    readme_after = replace_exact(
        readme_before,
        r"rev: v\d+\.\d+\.\d+",
        f"rev: v{version}",
        allow_multiple=True,
    )
    if readme_after != readme_before:
        README.write_text(readme_after)
        changed_paths.append(README.name)

    return tuple(changed_paths)


def replace_exact(
    content: str,
    pattern: str,
    replacement: str,
    *,
    allow_multiple: bool = False,
) -> str:
    updated, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise RuntimeError(f"Pattern not found: {pattern}")
    if not allow_multiple and count != 1:
        raise RuntimeError(f"Pattern matched {count} times: {pattern}")
    return updated


def maybe_publish_current_tag(current_version: Version) -> None:
    if current_version == BOOTSTRAP_VERSION:
        return
    if not has_remote():
        print(f"Skipping current-tag bootstrap because remote {REMOTE_NAME!r} is not configured.")
        return

    full_tag_name = version_tag_names(current_version)[-1]
    if remote_tag_exists(full_tag_name):
        return

    print(f"Publishing missing mirror tag {full_tag_name} for current repository state.")
    publish_tag_set_and_release(current_version, push_head=False, latest=True)


def remote_tag_exists(tag_name: str) -> bool:
    if not has_remote():
        result = subprocess.run(
            ["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag_name}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--tags", REMOTE_NAME, f"refs/tags/{tag_name}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 2:
        return False
    raise RuntimeError(result.stderr.strip() or f"git ls-remote failed for {tag_name}")


def version_tag_names(version: Version) -> tuple[str, str, str]:
    if len(version.release) != 3:
        raise RuntimeError(f"Expected a three-part release version, got {version}.")

    major, minor, patch = version.release
    return (
        f"v{major}",
        f"v{major}.{minor}",
        f"v{major}.{minor}.{patch}",
    )


def publish_tag_set_and_release(
    version: Version,
    *,
    push_head: bool,
    latest: bool,
) -> None:
    major_tag, minor_tag, full_tag = version_tag_names(version)
    git(["tag", "-f", major_tag])
    git(["tag", "-f", minor_tag])
    git(["tag", full_tag])

    push_args = ["push", REMOTE_NAME]
    if push_head:
        push_args.append(f"HEAD:refs/heads/{TARGET_BRANCH}")
    push_args.extend(
        [
            f"+refs/tags/{major_tag}:refs/tags/{major_tag}",
            f"+refs/tags/{minor_tag}:refs/tags/{minor_tag}",
            f"refs/tags/{full_tag}:refs/tags/{full_tag}",
        ]
    )
    git(push_args)

    release_cmd = [
        "gh",
        "release",
        "create",
        full_tag,
        "--title",
        full_tag,
        "--notes",
        f"Mirrors {PACKAGE_NAME} {version}: {MIRROR_SOURCE_URL_TEMPLATE.format(version=version)}",
        "--verify-tag",
    ]
    if latest:
        release_cmd.append("--latest")
    run(release_cmd)


def has_remote() -> bool:
    result = subprocess.run(
        ["git", "remote", "get-url", REMOTE_NAME],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def git(args: list[str]) -> None:
    run(["git", *args])


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
            "User-Agent": "spore-pre-commit-sync/1",
        },
    )
    with urlopen(request) as response:
        return response.read().decode("utf-8")


if __name__ == "__main__":
    main()
