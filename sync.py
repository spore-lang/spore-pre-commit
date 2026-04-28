# /// script
# requires-python = ">=3.12"
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

from check_invariants import validate_repo_state

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
    validate_repo_state()
    maybe_publish_current_tag(current_version)
    versions = find_new_versions(current_version)
    if not versions:
        print("No new stable releases to mirror.")
        return

    for index, version in enumerate(versions):
        tag_name = f"v{version}"
        if remote_tag_exists(tag_name):
            print(f"Skipping existing tag {tag_name}.")
            continue

        changed_paths = update_files(version)
        if not changed_paths:
            print(f"No file changes for {tag_name}; skipping.")
            continue

        git(["add", *changed_paths])
        git(["commit", "-m", f"🔄 chore: mirror {PACKAGE_NAME} {tag_name}"])
        publish_tag_and_release(tag_name, version, push_head=True, latest=index == len(versions) - 1)


def read_current_version() -> Version:
    with PYPROJECT.open("rb") as handle:
        pyproject = tomllib.load(handle)

    project_version = Version(pyproject["project"]["version"])
    requirement = Requirement(pyproject["project"]["dependencies"][0])
    specifier = next(iter(requirement.specifier), None)
    if specifier is None or specifier.operator != "==":
        raise RuntimeError(f"Expected an exact {PACKAGE_NAME} pin in pyproject.toml.")
    dependency_version = Version(specifier.version)
    if project_version != dependency_version:
        raise RuntimeError(
            "pyproject.toml version and dependency pin must match "
            f"({project_version} != {dependency_version})."
        )
    return dependency_version


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

    tag_name = f"v{current_version}"
    if remote_tag_exists(tag_name):
        return

    print(f"Publishing missing mirror tag {tag_name} for current repository state.")
    publish_tag_and_release(tag_name, current_version, push_head=False, latest=True)


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


def publish_tag_and_release(
    tag_name: str,
    version: Version,
    *,
    push_head: bool,
    latest: bool,
) -> None:
    git(["tag", tag_name])
    if push_head:
        git(["push", REMOTE_NAME, f"HEAD:refs/heads/{TARGET_BRANCH}", "--tags"])
    else:
        git(["push", REMOTE_NAME, "--tags"])

    release_cmd = [
        "gh",
        "release",
        "create",
        tag_name,
        "--title",
        tag_name,
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
