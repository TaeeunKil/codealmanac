# Slice 192 review: experimental proposer freeze and content permission boundary

## Outcome

No blocking findings. The parent review confirmed that the CLI freeze and the
content/destination contract are enforced at the intended boundaries.

## Verified boundaries

- `awm improve prepare` and `awm improve propose` require a non-persistent
  `--experimental` acknowledgement; settings/list/show remain inspection-only.
- The workflow resolves `allow_remote_content` into the immutable attempt policy
  and rejects selected-local evidence before creating an attempt or worktree.
- The Codex integration repeats the same guard before worktree/process use and
  prompt construction repeats it once more for direct callers.
- Metadata-only evidence remains allowed without a grant, and body-bearing
  evidence requires the explicit one-attempt remote grant.
- Existing attempt manifests load with the new grant denied by default; new
  manifests record the effective grant.
- MANUAL.md now describes candidate generation as experimental and incomplete;
  it does not imply evaluation, promotion, merge, push, or live dogfood.

## Residual boundaries

- The proposer still generates candidates without a concrete evaluator, replay
  corpus, trial artifacts, promotion/rejection UI, cleanup, or reconciliation.
  Those are later roadmap phases, not silently included here.
- The improvement JSON store remains non-transactional across candidate/run/
  attempt files, as documented by the audit and Slice 191 review.
- The remote grant is only a permission contract in this slice; no live Codex
  invocation was made and no real AWM state, Vault, or user repository was
  touched by tests.

## Verification

- Focused improvement suites: 39 passed after one test-fixture correction.
- Full repository tests: 209 passed.
- Touched source/tests Ruff check: passed.
- Viewer JavaScript syntax: passed.
- `git diff --check`: passed.
- Repository-wide Ruff still reports the four pre-existing systemd E501
  violations outside this slice.
