# Slice 195 — Coordinate Vault Sync with transcript sync

## Intent

Prevent the scheduled Vault Git operation from racing the transcript sync that
updates the SQLite state and generated Vault/search views.

## Shape

- Reuse the existing state-root `sync.lock` as the single coordination seam.
- `AWM Sync` keeps exclusive ownership while collecting and refreshing search.
- `VaultRepositoryWorkflow` acquires the same lock before refreshing local
  views and running Vault Git operations, waiting for an in-flight transcript
  sync to finish.
- Surface a bounded timeout as a clear runtime error instead of allowing an
  unlogged task failure.

## Scope

- Add the shared lock to Vault repository workflow construction.
- Cover scheduled/manual Vault sync behavior with focused tests.
- Document the coordination behavior in the user-facing README.

## Non-goals

- No retention or database compaction policy in this slice.
- No deletion or rewriting of Vault history.
- No changes to remote collection semantics.

## Validation

- `uv run pytest tests/test_agentworkmemory_vault_repository.py tests/test_sync_workflow.py`
- `uv run ruff check src/agentworkmemory tests/test_agentworkmemory_vault_repository.py tests/test_sync_workflow.py`
- `git diff --check`
