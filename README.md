# spore-pre-commit

`spore-pre-commit` is a tiny mirror repository for running published
`spore-lang` releases through [`pre-commit`](https://pre-commit.com/).

The repository keeps one version-aligned snapshot per upstream `spore-lang`
PyPI release:

1. `.pre-commit-hooks.yaml` is maintained in this repository and only changes
   when the hook surface itself changes.
2. `pyproject.toml` pins `spore-lang==X.Y.Z`.
3. This README updates the example `rev` to the latest mirrored tag.

`sync.py` is the only automation entrypoint. The GitHub Actions workflow runs it
on pushes to `main`, on a schedule, and on demand. When a new stable
`spore-lang` release appears on PyPI, the script only updates tracked version
references in this repository, creates the corresponding mirror commit,
refreshes alias tags `vX` and `vX.Y`, pushes immutable tag `vX.Y.Z`, and
opens a GitHub release that points back to the mirrored PyPI release.

## Usage

```yaml
repos:
  - repo: https://github.com/spore-lang/spore-pre-commit
    rev: v0.0.3
    hooks:
      - id: spore-format
      - id: spore-check
```

`main` starts at the current published `spore-lang` version. The sync workflow
automatically creates the matching mirror tag if it is not present yet.

Mirror tags only move when a stable PyPI release exists. If a downstream repo
needs unreleased `spore` main-branch syntax, keep using a source-built CLI
until the next public package is published.

Hook environments follow the mirrored `spore-lang` package's Python
requirement. The current mirror requires Python 3.13 or newer.

## Source of truth

- Hook metadata lives in this repository's `.pre-commit-hooks.yaml`.
- Release discovery comes from `https://pypi.org/pypi/spore-lang/json`, not
  from GitHub tags in the `spore` repo.
- Automated sync only bumps this repository's version references; it does not
  rewrite hooks automatically.
- Mirror tags are cut only for stable upstream releases.
- Moving alias tags `vX` and `vX.Y` are refreshed to the latest mirrored patch
  release.
- Automated update commits use `🔄 chore: mirror spore-lang vX.Y.Z`.
