# Slice 190: Self-improvement harness foundation

## Intent

Create an inspectable, evidence-grounded harness-improvement subsystem for
Agent Work Memory. It turns explicitly selected retained work sessions into an
immutable improvement run, records bounded candidate claims, compares baseline
and candidate evaluation outcomes, and qualifies only candidates with a
verified held-in fix and no held-out regression.

This slice builds the durable seams and one honest local workflow. It does not
autonomously edit, commit, merge, or deploy AWM. Provider execution and
candidate worktree mutation are later machinery behind the ports established
here.

## Source design

The design applies the practical loop described in Lilian Weng's “Harness
Engineering for Self-Improvement”:

1. Mine weaknesses from rich, verifier-grounded trajectories rather than a
   terminal error label alone.
2. Give the proposer a bounded editable surface, passing behaviors to preserve,
   and the history of attempted edits.
3. Validate a candidate on held-in cases that represent the target weakness and
   held-out cases that protect unrelated behavior.
4. Keep permissions, evaluation policy, model configuration, and the acceptance
   gate outside the candidate's editable workspace.
5. Persist execution history as files so runs remain inspectable and resumable.

## Boundary decision

The subsystem is separated by process, module, storage directory, and write
authority, but remains part of the canonical `agentworkmemory` package and
state root. A second application, package name, database, Vault, or user config
path would violate the AWM product contract.

```text
src/agentworkmemory/
  services/improvement/       typed lifecycle, store, gate, ports
  workflows/improve_harness/  prepare and evaluate use cases
  integrations/improvement/   future Codex proposer / concrete evaluator

<state_dir>/improvement/
  runs/<run-id>/
    manifest.json
    evidence.json
    candidates/<candidate-id>/
      manifest.json
      evaluation.json
```

The Markdown Vault remains untouched. Session evidence is read through the
existing session service and copied only after explicit content access. The
improvement store writes only below `<state_dir>/improvement`.

## Domain contracts

Use Pydantic models and enums. Do not pass shaped dictionaries between layers.

```python
class ImprovementRunState(StrEnum):
    PREPARED = "prepared"
    CANDIDATE_RECORDED = "candidate-recorded"
    QUALIFIED = "qualified"
    REJECTED = "rejected"


class HarnessComponent(StrEnum):
    SYSTEM_PROMPT = "system-prompt"
    TOOL_DESCRIPTION = "tool-description"
    TOOL_IMPLEMENTATION = "tool-implementation"
    MIDDLEWARE = "middleware"
    SKILL = "skill"
    SUBAGENT_CONFIGURATION = "subagent-configuration"
    LONG_TERM_MEMORY = "long-term-memory"


class ImprovementEvidence(AgentWorkMemoryModel):
    session_id: str
    provider: str
    title: str
    workspace: Path | None
    events: tuple[ImprovementEvidenceEvent, ...]


class ImprovementRun(AgentWorkMemoryModel):
    run_id: str
    repository: Path
    base_revision: str
    content_access: ContentAccess
    editable_paths: tuple[Path, ...]
    evidence: tuple[ImprovementEvidence, ...]
    state: ImprovementRunState
    created_at: datetime
    updated_at: datetime


class ImprovementCandidate(AgentWorkMemoryModel):
    candidate_id: str
    run_id: str
    component: HarnessComponent
    failure_evidence: tuple[str, ...]
    root_cause: str
    targeted_fix: str
    predicted_impact: str
    regression_risks: tuple[str, ...]
    changed_paths: tuple[Path, ...]


class EvaluationCaseResult(AgentWorkMemoryModel):
    suite: EvaluationSuite       # held-in | held-out
    case_id: str
    baseline_passed: bool
    candidate_passed: bool


class EvaluationReport(AgentWorkMemoryModel):
    candidate_id: str
    cases: tuple[EvaluationCaseResult, ...]
    decision: CandidateDecision  # qualified | rejected
    reasons: tuple[str, ...]
```

Model validators must reject blank identifiers/text, repositories that are not
absolute, empty evidence selection, absolute or escaping editable/changed
paths, duplicate paths, and candidate paths outside the prepared editable
surface.

## Product workflow

```python
run = improvement.prepare(
    session_ids=request.session_ids,
    repository=request.repository,
    base_revision=revision_reader.head(request.repository),
    content_access=request.content_access,
    editable_paths=request.editable_paths,
)

candidate = improvement.record_candidate(run.run_id, proposal)

report = improvement.evaluate(
    run_id=run.run_id,
    candidate_id=candidate.candidate_id,
    cases=evaluator.compare(run, candidate),
)
```

`prepare` is deterministic and invokes no model. Metadata-only access stores no
event bodies. Selected-local access stores bodies only for the explicitly named
sessions. Unknown sessions fail the complete operation before anything is
written.

`record_candidate` stores a falsifiable manifesto, not a free-form chat log.
It revalidates every changed path against the run's editable surface.

`evaluate` applies the fixed acceptance gate:

- at least one held-in case must change from failing to passing;
- no held-in case may regress from passing to failing;
- no held-out case may regress from passing to failing;
- both suites must be present;
- a report that violates any rule is rejected with explicit reasons.

The candidate cannot change this gate.

## Ports and deferred machinery

Define only the ports needed to keep future provider and evaluation machinery
additive:

```python
class RepositoryRevisionReader(Protocol):
    def head(self, repository: Path) -> str: ...


class ImprovementEvaluator(Protocol):
    def compare(
        self,
        run: ImprovementRun,
        candidate: ImprovementCandidate,
    ) -> tuple[EvaluationCaseResult, ...]: ...
```

The initial concrete revision reader may call `git rev-parse HEAD` with bounded
output and sanitized errors. Tests use fakes. Do not implement a Codex proposer,
candidate worktree editor, command-config language, scheduler, viewer UI,
automatic application, or Git merge in this slice.

The next slice can add a Codex proposer that uses `gpt-5.6-luna` with `max` or
`xhigh` reasoning. That adapter will receive a prepared run, write only in a
dedicated candidate worktree, and return the typed candidate manifesto. It must
not receive write access to the run store, trusted evaluation policy, baseline
checkout, AWM database, or Vault.

## CLI surface

Add a small explicit command group:

```text
awm improve prepare SESSION_ID... --repo PATH
  [--allow-local-content]
  [--editable PATH ...]

awm improve list
awm improve show RUN_ID
```

Defaults:

- content access is metadata-only;
- repository defaults to the current directory;
- editable paths must be explicitly supplied in this first slice;
- `show` reports identifiers, lifecycle state, evidence counts, editable paths,
  and candidate/evaluation summaries without printing retained event bodies.

Candidate recording and evaluation are service/workflow APIs in this slice,
covered by tests. Do not expose a CLI that accepts arbitrary commands or trusts
candidate-provided evaluation configuration.

## Verification

- Preparing a metadata-only run writes no session event content.
- Preparing with selected-local access includes only explicitly selected
  session events.
- An unknown session leaves no partial run directory.
- Run and candidate writes are atomic and remain inside the improvement root.
- Candidate paths outside the editable surface are rejected before persistence.
- The gate qualifies a held-in fix with no regressions.
- The gate rejects missing suites, no demonstrated fix, held-in regressions,
  and held-out regressions.
- CLI list/show never prints private event bodies.
- Existing AWM tests, Ruff, JavaScript syntax, and diff checks pass.

## Implementation ownership

The parent agent owns this design and final architectural review. A newly
spawned `gpt-5.6-luna` implementation agent with `max` reasoning owns all code,
tests, and implementation-driven plan amendments in this worktree.
