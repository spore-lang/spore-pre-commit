# spore-pre-commit

`spore-pre-commit` is a tiny mirror repository for running `spore-lang` through
[`pre-commit`](https://pre-commit.com/).

The repository keeps one mirrored snapshot per upstream `spore-lang`
release:

1. `.pre-commit-hooks.yaml` is copied from `spore` tag `vX.Y.Z` when it exists,
   and otherwise falls back to `spore@main`.
2. `pyproject.toml` pins `spore-lang==X.Y.Z`.
3. This README updates the example `rev` to the latest mirrored tag.

`sync.py` is the only automation entrypoint. The GitHub Actions workflow runs it
on pushes to `main`, on a schedule, and on demand. When a new stable
`spore-lang` release appears on PyPI, the script updates tracked files, creates
the corresponding mirror commit, pushes tag `vX.Y.Z`, and opens a GitHub
release that points back to the mirrored PyPI release.

## Usage

```yaml
repos:
  - repo: https://github.com/spore-lang/spore-pre-commit
    rev: v0.0.2
    hooks:
      - id: spore-format
      - id: spore-check
```

`main` starts at the current published `spore-lang` version. The sync workflow
automatically creates the matching mirror tag if it is not present yet.

## Source of truth

- Hook metadata lives in `spore/.pre-commit-hooks.yaml`.
- Release discovery comes from `https://pypi.org/pypi/spore-lang/json`.
- Mirror tags are cut only for stable upstream releases.
- Automated update commits use `🔄 chore: mirror spore-lang vX.Y.Z`.
