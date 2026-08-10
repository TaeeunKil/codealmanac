# Slice 191 review: configurable Codex improvement proposer

## Outcome

The parent architecture review found two correctness issues. Luna Max fixed both
in production code and added isolated regression tests. No unresolved blocking
finding remains for this slice.

## Findings resolved

### 1. Candidate work was incorrectly coupled to the live baseline HEAD

The proposer originally rejected a valid detached candidate if the baseline
checkout advanced while Codex was running. That would prevent the user from
continuing normal work during a long proposal even though the candidate
worktree remained pinned to the prepared revision.

The live-baseline comparison was removed. Candidate creation and post-run
verification still require a detached worktree at the exact prepared revision.
A regression test advances and commits the baseline from the fake Codex call,
then proves that the candidate remains detached at the original revision with
independent content.

### 2. Attempt finalization could record a false failure

The workflow originally caught `complete_attempt` failures after a candidate
had already been stored, then rewrote the attempt as failed. That contradicted
the durable candidate and run state.

The failure boundary now covers proposal generation and candidate persistence
only. Finalization happens after that boundary. A regression test forces
finalization to fail and proves the candidate stays recorded, the run stays in
`candidate-recorded`, and the attempt is not falsely marked failed.

## Residual boundaries

- A finalization failure deliberately leaves an attempt in `started`; a future
  reconciliation command should repair that from the durable candidate/run
  state.
- The integration command and sandbox policy are verified with a fake Codex
  process. This slice does not invoke a paid/live model or mutate the user's
  actual AWM state, Vault, or repository during tests.
- Candidate evaluation, promotion, merge, and retained-worktree cleanup remain
  explicit later slices. This slice never performs them automatically.

## Verification

- Focused improvement tests: 33 passed.
- Full test suite: 194 passed.
- Ruff: passed.
- Viewer JavaScript syntax: passed.
- `git diff --check`: passed (Git emitted line-ending normalization warnings
  only).
