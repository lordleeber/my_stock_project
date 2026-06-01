# Git hooks

Version-controlled hooks for this repo. Enable them **once per clone**:

```bash
git config core.hooksPath .githooks
```

(`core.hooksPath` is a local git setting — it isn't cloned, so every checkout
must run that command once.)

## `pre-commit`

Runs `ruff format --check` + `ruff check` (via the repo-local `venv/bin/ruff`,
pinned to the same `0.12.12` the CI uses) over the **staged** `*.py` files
before each commit. This is the local mirror of the **Python Linter** GitHub
Action (`.github/workflows/lint.yaml`), so format/lint problems are caught
before they turn the PR red.

- Non-mutating: on failure it prints the exact fix command and aborts; it never
  rewrites your files behind your back.
- Scoped to staged files only, so untracked work-in-progress scripts don't block
  unrelated commits.
- Bypass a single commit with `git commit --no-verify` (use sparingly).
