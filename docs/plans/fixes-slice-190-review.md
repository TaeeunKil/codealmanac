# Slice 190 review fixes: self-improvement harness foundation

## Review result

The foundation now matches the slice boundary and repository architecture. The
improvement control plane stays inside the canonical `agentworkmemory` package
and state root while using dedicated service, workflow, integration, and
`<state_dir>/improvement` boundaries. It neither writes to the Markdown Vault
nor exposes autonomous editing, command execution, application, commit, or
merge behavior.

No open review findings remain for this slice.

## Findings fixed

### Public metadata query boundary

The first implementation listed `AgentEventMetadata` in the sessions package
`__all__` without binding the name. A wildcard import therefore failed at
runtime. The sessions package now imports and exports the type consistently,
with a regression test that exercises the public export.

### Immutable prepared evidence

The first store update guard protected only the evidence tuple. That allowed a
caller of the store boundary to replace other facts that define a prepared
run. `ImprovementStore.update_run` now rejects changes to the repository, base
revision, content-access decision, editable paths, evidence, and creation time.

### Honest single-candidate lifecycle

The run state is terminal after one candidate is evaluated, so allowing
several candidates under one run produced candidates that could never be
evaluated honestly. Candidate recording now requires the `prepared` state and
the slice permits exactly one candidate per run. A future comparison workflow
can introduce an explicit experiment model instead of overloading this
lifecycle.

### Unique evaluation identities

The initial acceptance gate could count the same `(suite, case_id)` more than
once. Duplicate case identities now force rejection, and the persistence
boundary also refuses a forged qualified report containing duplicates.

### Static checks

Luna xhigh applied the remaining Ruff import-order fixes without changing
behavior.

## Residual boundary

Artifact publication and manifest replacement are atomic per file or directory,
but a candidate publication followed by its run-state update is not a single
cross-file transaction. A process crash between those operations can leave a
published candidate beside a still-`prepared` manifest. This first slice does
not run autonomously or on a scheduler, so the condition is observable and
recoverable from the filesystem. Before unattended proposing is enabled, add
startup reconciliation or a journaled lifecycle transition and test forced
crashes at each publication boundary.

The evaluation inputs are supplied through a typed evaluator port in this
slice. Concrete baseline/candidate execution, candidate worktree mutation, and
the Luna proposer remain intentionally deferred; they must stay outside the
candidate-editable surface and the trusted acceptance gate.

## Verification coverage

- Metadata-only evidence persists no event bodies.
- Selected-local evidence copies only explicitly selected sessions.
- Unknown sessions leave no partial run directory.
- Run and candidate publication stays below the improvement state root.
- Escaping candidate paths are rejected before persistence and rechecked at
  evaluation.
- Held-in fixes qualify only when held-in and held-out passing behavior does not
  regress.
- Duplicate evaluation identities cannot qualify.
- CLI list and show output never prints retained event bodies.
- Git revision lookup is bounded, read-only, and sanitizes URL credentials.
- Existing AWM tests and static checks remain the final merge gate.
