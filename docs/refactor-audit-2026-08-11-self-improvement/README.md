# Agent Work Memory self-improvement audit

Date: 2026-08-11

Status note (2026-08-12): the experimental surface is now described in the
current manual and CLI as a **structural review and patch proposer**. The
historical `improvement` type and state names remain unchanged for persistence
compatibility; this does not promote it to a self-improvement loop.

## Executive conclusion

Agent Work Memory has not yet completed a self-improvement loop.

It has built four increasingly ambitious pieces:

1. a disciplined human/agent engineering loop (`plan -> build -> review -> fix`);
2. a memory loop that captures sessions and distills them into durable Markdown;
3. a dedicated harness-experiment foundation that can ask Codex to create one
   patch in an isolated Git worktree; and
4. an explicitly incomplete active-memory/MCP design intended to let future
   agents recall and propose memory.

Only the first two are operational end to end. The third stops after candidate
generation. It has no concrete evaluator, no public evaluation command, no
replay corpus, no trustworthy trial artifacts, no user promotion action, and
no cleanup or reconciliation. The fourth is a design draft and says not to
implement it.

The highest-confidence next move is therefore **not another proposer feature**.
It is the distillation-quality instrumentation already named in the user's
durable Wiki: `DistillationTrace`, `HarnessVersion`, and a bounded
`DistillEvidenceBundle`. AWM must learn to measure its memory-making behavior
before it lets a model optimize that behavior.

## What was actually attempted

| Attempt | Period | What exists | Status | Judgment |
| --- | --- | --- | --- | --- |
| Slice review ritual | throughout repository history | plans, implementation slices, independent review, review-fix plans, build/test gates | operational | **Keep.** This is the only proven improvement loop, but it is human-governed engineering rather than runtime self-improvement. |
| CodeAlmanac Build/Absorb/Garden | historical upstream product | agent-authored Wiki creation, incremental absorption, graph gardening, human review escalations, scheduled Garden | archived/reference only | **Keep as prior art, not product code.** Its strongest ideas survived as distillation and validation. Do not restore the broad Garden surface. |
| Scheduled self-update | historical CodeAlmanac | scheduled package installation and smoke checks | not part of current AWM contract | **Do not call this self-improvement.** It changes software version without learning from outcomes. |
| AWM capture and distillation | current product | deterministic session collection, selected/scheduled curator runs, isolated Vault workspaces, allowed-path validation, rollback, receipts, search | operational but open-loop | **Keep and instrument.** This is the correct first optimization target. |
| Distillation-quality-loop analysis | retained sessions and durable Wiki | decision and unfinished-work pages specifying trace, harness version, better evidence bundles, replay, shadow evaluation, and gated promotion | designed, not implemented | **Make this the active roadmap.** It predates and correctly constrains autonomous source editing. |
| Slice 190 harness foundation | local branch/commit `652c5787` | typed run/candidate/evaluation models, file store, acceptance gate, evidence preparation, Git revision reader, prepare/list/show CLI | implemented and unit-tested | **Preserve concepts, reshape persistence and names.** It is an experiment control-plane seed, not a usable self-improver. |
| Slice 191 Codex proposer | local branch/commit `dde25d9f` | configurable Codex policy, detached worktree, structured proposal, observed changed paths, attempt history | implemented with fake-process tests | **Freeze pending evaluator and permission repair.** Candidate generation arrived before trustworthy evaluation. |
| Agent memory reconnection draft | local commit `18518268` | 1,573-line MCP-first active-memory design with a do-not-implement warning | incomplete draft | **Split and defer transport.** Keep bounded recall, provenance, and candidate-only writes as product requirements; reassess the storage model after selective NOOA study. |

## Repository and runtime facts

- Local `main` is four commits ahead of `origin/main`. The self-improvement
  branch is published, and local `main` merged it, but remote `main` does not
  contain the feature.
- The local-only change set is 5,703 added lines across 27 files, including two
  implementation slices and the incomplete memory draft.
- The focused improvement suites pass: 33 tests, plus Ruff and `git diff
  --check`.
- Those tests use fake Codex execution. They do not prove a live proposal,
  sandbox containment, evaluator behavior, or promotion.
- The canonical local AWM state contains **zero improvement runs**. The feature
  has not been dogfooded through `awm improve prepare/propose`.
- The existing memory system did retain and distill the design work. Four
  successful distillation receipts over seven selected sessions updated the
  durable decision, project, and unfinished-work pages for this topic.
- That dogfood also exposes the missing quality layer: some receipts report
  `no-durable-knowledge` while changed files were recorded, and the resulting
  frontmatter contains malformed/duplicated source entries. Structural success
  is not the same as useful, attributable memory.

## Strongest objections

### 1. The order is backwards

The repository first identified the need for distillation traces, harness
versions, richer evidence bundles, replay cases, and shadow evaluation. It then
built a general code proposer before building those prerequisites.

Recommendation: freeze the proposer and complete observability plus evaluation
first.

### 2. `selected-local` content can cross a remote-model boundary

`awm improve prepare --allow-local-content` records
`ContentAccess.SELECTED_LOCAL`. `ImproveHarnessWorkflow.propose()` later embeds
that evidence in a Codex prompt. The existing AWM contract defines selected
local content as content for a local runtime, while Codex is a remote model
surface.

Recommendation: disable this combination immediately. Model destination and
content permission must be resolved in one proposal request, with an explicit
remote-content grant. A prepared evidence object must never silently acquire a
broader destination later.

### 3. The acceptance gate trusts pre-reduced booleans

The deterministic gate is good, but its inputs are caller-supplied
`baseline_passed` and `candidate_passed` booleans. There is no concrete
evaluator, trial receipt, corpus identity, harness version, command/result
artifact, repetition count, or cost/latency record. A fixed gate over
unverifiable booleans is not a trusted evaluation system.

Recommendation: make the evaluator produce immutable paired trial artifacts.
The gate derives its decision from those artifacts; callers do not submit a
decision-shaped summary.

### 4. The product surface ends before evaluation

The CLI offers `prepare`, `propose`, `list`, and `show`. There is no `evaluate`,
`compare`, `review`, `promote`, `reject`, `cleanup`, or `reconcile`. No concrete
`ImprovementEvaluator` exists outside tests.

Recommendation: do not document or publish this as self-improvement. Describe
it as an experimental structural review and patch proposer until the full
lifecycle exists.

### 5. The editable surface is prematurely general

The component enum copies seven broad harness categories from research: prompt,
tool description, tool implementation, middleware, skill, subagent
configuration, and long-term memory. AWM has no evaluation suite capable of
attributing gains across that space.

Recommendation: the first editable surface should be only distillation
guidance, evidence selection, related-page retrieval, and the quality rubric.
Permission code, secret filtering, validators, evaluator code, model/budget
authority, and promotion remain fixed.

### 6. Persistence is inspectable but not transactional

The custom JSON directory store provides useful inspectability, yet candidate
publication, run-state updates, and attempt finalization span separate files.
The repository's own review documents crash gaps and started-attempt
reconciliation debt. Full selected event bodies may also be duplicated from
SQLite into unbounded `evidence.json` files with no retention policy.

Recommendation: keep large immutable artifacts as content-addressed files, but
move lifecycle state and references into the existing SQLite/WAL control plane.
Persist bounded evidence excerpts and hashes rather than duplicating every
event body.

### 7. Memory creation and memory reuse are disconnected

AWM captures and distills knowledge, but a future agent only benefits if a user
manually searches or reads the Wiki. The memory-reconnection draft correctly
spots this missing reuse loop, but makes MCP and a new work-memory subsystem the
center too early.

Recommendation: first expose a provider-neutral read service for bounded
context, recall, and canonical provenance. Add one transport only after the
service is evaluated. Agent writes remain review candidates.

## What should remain fixed

- person ownership of memory;
- retained sessions/events as evidence;
- ordinary Markdown as durable knowledge;
- explicit content permission and destination;
- isolated candidate/Vault workspaces;
- allowed-path, citation, secret, frontmatter, and rollback validators;
- evaluator data, model/budget authority, and acceptance/promotion rules;
- human approval before a harness candidate becomes active;
- no automatic merge or deployment in the first complete loop.

## Target shape

```text
work sessions
    -> DistillEvidenceBundle + HarnessVersion
    -> baseline/candidate distillation in isolated Vault copies
    -> fixed structural/privacy gates
    -> quality rubric + retrieval questions
    -> DistillationTrace + explicit user feedback
    -> replay corpus / weakness clusters
    -> bounded harness candidate in detached worktree
    -> paired held-in + sealed held-out trials
    -> deterministic acceptance gate
    -> human review and promotion receipt
    -> next active HarnessVersion
```

The memory reuse path is adjacent, not mixed into harness promotion:

```text
confirmed durable Wiki + retained evidence
    -> bounded MemoryQueryService
    -> context / recall / open with provenance
    -> agent memory candidate
    -> user review
    -> confirmed state or normal distillation
```

See [target-architecture.md](target-architecture.md) and
[refactor-roadmap.md](refactor-roadmap.md).

## Bottom line

Preserve the safety-conscious seams from Slices 190 and 191, but do not keep
growing them in their current order. AWM's next self-improvement milestone is
not “Codex can edit AWM.” It is:

> For one representative session, AWM can explain exactly what evidence it
> selected, which harness version produced which candidate pages, which fixed
> gates and quality checks passed, what the user later corrected, and whether a
> candidate harness improves that case without degrading sealed cases.

Until that statement is true, self-improvement is a proposal mechanism, not a
learning system.
