"""Validate mirrored release metadata stays in lockstep."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"

README_REV_PATTERN = re.compile(r"(?m)^\s*rev: v(?P<version>\d+\.\d+\.\d+)\s*$")


def validate_repo_state() -> None:
    pyproject_version, dependency_pin = read_pyproject_versions()
    if pyproject_version != dependency_pin:
        raise RuntimeError(
            "pyproject.toml version and spore-lang dependency pin must match "
            f"({pyproject_version!r} != {dependency_pin!r})."
        )

    readme_version = read_readme_version()
    if readme_version != pyproject_version:
        raise RuntimeError(
            "README.md rev must match the pyproject.toml version "
            f"({readme_version!r} != {pyproject_version!r})."
        )


def read_pyproject_versions() -> tuple[str, str]:
    with PYPROJECT.open("rb") as handle:
        pyproject = tomllib.load(handle)

    project = pyproject["project"]
    project_version = str(project["version"])
    dependency_pin = read_dependency_pin(project["dependencies"][0])
    return project_version, dependency_pin


def read_dependency_pin(requirement: str) -> str:
    match = re.fullmatch(r"spore-lang==(?P<version>\d+\.\d+\.\d+)", requirement)
    if match is None:
        raise RuntimeError(
            "Expected pyproject.toml to pin spore-lang with an exact release version."
        )
    return match.group("version")


def read_readme_version() -> str:
    matches = README_REV_PATTERN.findall(README.read_text())
    if len(matches) != 1:
        raise RuntimeError("README.md must contain exactly one mirrored rev line.")
    return matches[0]


if __name__ == "__main__":
    validate_repo_state()
