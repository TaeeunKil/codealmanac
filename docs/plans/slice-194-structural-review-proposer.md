# Slice 194: Structural review and patch proposer boundary

## Intent

Make the current experimental surface honest and useful. It is not yet a
self-improvement system: it selects evidence, asks a bounded Codex runtime to
propose one structural patch, and leaves that patch in a detached worktree for
human inspection. Evaluation, promotion, commit, merge, push, and deployment
remain outside this slice.

The durable service and state names remain `improvement` for compatibility with
the existing persisted runs. The public language must describe the actual
behavior as an **experimental structural review and patch proposal**.

## Contract

```text
session evidence
    -> prepared review run
    -> Codex structural review in a detached worktree
    -> observed patch candidate
    -> human inspection / later evaluation
```

The proposer may edit only the prepared editable surface in its candidate
worktree. A successful proposal records the observed changed paths and a typed
manifesto. It never writes the baseline checkout, AWM state, Vault, Git
history, or remote repository.

`awm improve` remains the canonical command group because the persisted domain
is already shipped. Its help, acknowledgement, output, and model prompt must
call the operation a structural review and patch proposal. No CLI wording may
claim that the current command completes self-improvement.

## Naming decisions

- User-facing run: **structural review run**.
- User-facing Codex role: **structural review and patch proposer**.
- User-facing result: **patch candidate**.
- Internal `Improvement*` types and state directory: unchanged until a
  persistence migration is designed.

This keeps a clean seam for a later full loop:

```text
structural review -> paired evaluator -> approval gate -> draft PR -> human merge
```

That later loop may earn the name self-improvement only after evaluation and
promotion outcomes are durable and feed the next run.

## Verification

- CLI help and acknowledgement identify structural review / patch proposal.
- Codex instructions forbid commits, branch changes, promotion, and remote
  publication.
- A successful proposal still records a candidate in a detached worktree.
- Existing persisted improvement runs and internal APIs remain loadable.
- Focused improvement tests, full AWM tests, Ruff, JavaScript syntax, and diff
  checks pass.
