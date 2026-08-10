# Slice 191: Configurable Codex improvement proposer

## Intent

Turn the slice-190 improvement foundation into one usable proposing path without
weakening its trusted control plane. A user can set durable Codex proposer
defaults, override them for one attempt, and ask AWM to create a candidate in a
dedicated Git worktree. Every attempt records the effective model and reasoning
effort that actually produced it.

The model is intentionally a validated string, not a closed enum, so a model can
be replaced without changing product code. Reasoning effort uses the existing
typed `ReasoningEffort` contract. The shipped default is
`gpt-5.6-luna` with `xhigh`; `max` remains an explicit higher-cost choice.

## Codex configuration contract

Codex supports explicit model selection with `--model` and reasoning selection
through `model_reasoning_effort`. Command-line overrides outrank project,
profile, and user configuration. AWM must therefore resolve its own policy and
always pass both effective values to Codex. It must not inherit either value
silently from the user's global Codex configuration.

Resolution order, from highest to lowest:

1. one-attempt `awm improve propose` flags;
2. the persisted AWM improvement proposer settings;
3. the built-in Luna/xhigh defaults.

There is no automatic model fallback. An unavailable or rejected model fails the
attempt with an inspectable error. Trying another model creates another attempt
with a distinct recorded identity.

## Product configuration

Extend the canonical AWM `config.json`; do not add a second config file or read
provider settings from the Vault.

```python
class ImprovementProposerSettings(AgentWorkMemoryModel):
    model: str = "gpt-5.6-luna"
    reasoning_effort: ReasoningEffort = ReasoningEffort.XHIGH


class AgentWorkMemoryConfig(AgentWorkMemoryModel):
    state_dir: Path
    vault_path: Path | None = None
    improvement_proposer: ImprovementProposerSettings = (
        ImprovementProposerSettings()
    )
```

Loading an existing config without the new object uses defaults. Saving config
preserves both Vault and proposer settings. Validate that the model is nonblank.
Never persist authentication data, environment variables, or Codex account
details.

Add explicit CLI operations:

```text
awm improve settings
awm improve configure --model MODEL --effort EFFORT
awm improve propose RUN_ID [--model MODEL] [--effort EFFORT]
```

`configure` updates only fields explicitly supplied and writes the canonical
config atomically. `settings` prints the current defaults. `propose` resolves
one effective policy without mutating defaults.

## Domain and attempt history

Use typed models rather than shaped dictionaries:

```python
class ImprovementProposerPolicy(AgentWorkMemoryModel):
    runtime: Literal["codex"] = "codex"
    model: str
    reasoning_effort: ReasoningEffort


class ImprovementProposalAttemptState(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ImprovementProposalAttempt(AgentWorkMemoryModel):
    attempt_id: str
    run_id: str
    policy: ImprovementProposerPolicy
    base_revision: str
    worktree: Path
    state: ImprovementProposalAttemptState
    started_at: datetime
    completed_at: datetime | None = None
    candidate_id: str | None = None
    failure: str | None = None
```

Persist attempts below the existing trusted store:

```text
<state_dir>/improvement/
  runs/<run-id>/
    attempts/<attempt-id>/manifest.json
    candidates/<candidate-id>/...
  worktrees/<run-id>/<attempt-id>/
```

Attempt identity, run identity, policy, base revision, and worktree location are
immutable after creation. State transitions may add completion, candidate, or
failure fields but may never replace the effective policy. Persist a failed
attempt even when Codex fails so model experiments remain attributable.

Do not persist raw Codex JSONL or credentials. Error text must be bounded and
sanitized. The candidate manifesto remains the durable semantic output.

## Provider-neutral service boundary

Extend the improvement service-owned port:

```python
class ImprovementProposer(Protocol):
    def propose(
        self,
        run: ImprovementRun,
        attempt: ImprovementProposalAttempt,
        previous_attempts: tuple[ImprovementProposalAttempt, ...],
    ) -> ImprovementCandidateProposal: ...
```

The workflow owns resolution and lifecycle orchestration. The Codex integration
owns executable discovery, command construction, process execution, JSONL and
structured-output parsing, and Git worktree mutation. Neither the service nor
workflow builds Codex command arguments.

Allow tests and callers to inject an `ImprovementProposer`. `create_app` composes
the concrete Codex proposer by default.

## Candidate worktree boundary

For every attempt, the integration creates a detached worktree at the prepared
run's exact `base_revision`. It must use bounded Git subprocess calls, reject an
existing target, and never mutate the baseline checkout. The baseline checkout
may advance or switch independently after preparation; only the detached
candidate worktree must remain pinned to the prepared revision.

Codex runs with:

- the candidate worktree as its only writable workspace;
- `workspace-write` sandboxing;
- approval policy `never`;
- network access disabled;
- web search disabled;
- user MCP servers disabled;
- the effective model and reasoning effort passed explicitly;
- a structured output schema for `ImprovementCandidateProposal`;
- no permission to the AWM state directory, Vault, or baseline worktree.

The prompt includes the prepared evidence, editable paths, acceptance rules,
passing behavior to preserve, and summaries of previous attempts. It explicitly
forbids commits, branch changes, worktree management, and edits outside the
prepared surface.

After Codex returns, read changed paths from Git rather than trusting the model.
Require at least one changed path, reject paths outside the prepared editable
surface, and replace the proposal's claimed paths with the observed Git paths
before recording the candidate. Do not automatically commit, apply, merge, or
delete the candidate worktree.

If Codex or validation fails, mark the attempt failed and leave its worktree for
inspection. A later cleanup/reconciliation operation is outside this slice.

## Lifecycle

```python
policy = resolve_policy(
    defaults=config.improvement_proposer,
    model=request.model,
    effort=request.reasoning_effort,
)
attempt = improvement.start_attempt(run.run_id, policy, worktree)

try:
    proposal = proposer.propose(run, attempt, improvement.attempts(run.run_id))
    candidate = improvement.record_candidate(run.run_id, proposal)
except Exception as error:
    improvement.fail_attempt(attempt.attempt_id, sanitized_error(error))
    raise

improvement.complete_attempt(attempt.attempt_id, candidate.candidate_id)
```

The run remains `prepared` after a failed attempt, allowing an explicit retry
with the same or a different model. Exactly one successful candidate is still
allowed per run. Multiple failed attempts preserve model history without
creating unevaluable candidates.

Once a candidate is durably recorded, a later failure while finalizing the
attempt must not rewrite that attempt as failed. It may remain `started` for a
future reconciliation operation, while the candidate and run state remain the
source of truth.

## Verification

- Old config files load Luna/xhigh defaults.
- Configure changes only requested defaults and round-trips atomically.
- One-attempt flags override defaults without changing persisted settings.
- Model strings reject blank values; reasoning effort is typed and supports
  `max`.
- The effective model and effort are always present in Codex arguments and the
  attempt manifest.
- User Codex defaults cannot replace explicit AWM values.
- No silent fallback occurs when Codex fails.
- The worktree is detached at the prepared base revision and stays outside the
  baseline repository.
- Observed Git paths, not model claims, determine the recorded candidate paths.
- Escaping changes fail the attempt and do not create a candidate.
- Failed attempts are persisted and the run remains retryable.
- A successful attempt records one candidate and keeps its worktree for later
  evaluation.
- Tests use isolated repositories and state roots; they never run real Codex,
  access the real AWM state/Vault, or change the current checkout.
- Full AWM tests, Ruff, viewer JavaScript syntax, and diff checks pass.

## Implementation ownership

The parent agent owns this design and the final architecture review. A
`gpt-5.6-luna` implementation agent with `max` reasoning owns all production
code, tests, and implementation-driven amendments in this slice.
