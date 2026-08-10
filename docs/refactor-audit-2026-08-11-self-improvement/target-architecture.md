# Target architecture

## Principle

AWM should have two explicit feedback loops and one reuse interface. They share
evidence and versions, but they do not share authority.

## Loop A: memory quality

```text
selected sessions
    -> EvidenceCompiler
    -> DistillEvidenceBundle
    -> CuratorCandidateRun (isolated Vault)
    -> FixedDistillValidator
    -> DistillQualityReviewer
    -> publish/no-op/reject
    -> DistillationTrace
    -> explicit user feedback + later retrieval outcomes
```

### New owned concepts

`HarnessVersion`

- source revision;
- prompt hash;
- evidence-selector version/hash;
- related-page retrieval policy version;
- curator runtime/model/effort;
- validator/rubric versions;
- allowed-path policy version.

`DistillEvidenceBundle`

- selected session/event identities;
- the exact bounded excerpts presented to the curator;
- a reason for each selected excerpt: intent, outcome, decision, failure,
  recovery, test, changed-file signal, correction, or unfinished work;
- content hashes and total budget;
- content-access class and destination receipt;
- no unselected full transcript copy.

`DistillationTrace`

- run and harness identities;
- before/after page hashes;
- proposed and applied paths;
- structural/privacy validation findings;
- quality rubric results;
- per-session attribution result;
- cost, latency, retries, and no-op reason;
- later explicit correction/rejection/retrieval feedback.

`DistillFeedback`

- user accepted unchanged;
- user corrected content/source/title/page choice;
- user rejected or reverted;
- expected knowledge was missing;
- later recall question succeeded or failed.

Only explicit signals count initially. Passive clicks and mere page existence do
not become quality labels.

## Loop B: harness experiments

```text
DistillationTrace corpus
    -> WeaknessMiner
    -> HarnessExperiment
    -> bounded HarnessCandidate worktree
    -> PairedReplayEvaluator
       -> active harness trial
       -> candidate harness trial
    -> AcceptanceGate
    -> HumanPromotionReview
    -> HarnessPromotionReceipt
    -> next HarnessVersion
```

### Honest renames

| Current | Target |
| --- | --- |
| `ImprovementRun` | `HarnessExperiment` |
| `ImprovementCandidate` | `HarnessCandidate` |
| `ImproveHarnessWorkflow` | `HarnessExperimentWorkflow` |
| `ImprovementService` | `HarnessExperimentsService` |
| `ImprovementStore` | SQLite lifecycle store + artifact repository |

These names describe experiments, not guaranteed improvements.

### Trial artifact

```python
class HarnessTrialResult(AgentWorkMemoryModel):
    experiment_id: str
    candidate_id: str | None        # None means active baseline
    harness_version: str
    corpus_version: str
    case_id: str
    suite: EvaluationSuite
    repetition: int
    evidence_bundle_hash: str
    before_vault_hash: str
    after_vault_hash: str
    hard_gate_findings: tuple[GateFinding, ...]
    quality_scores: DistillQualityScores
    retrieval_answers: tuple[RetrievalCheck, ...]
    runtime_seconds: float
    input_tokens: int | None
    output_tokens: int | None
```

The acceptance gate computes paired deltas from these results. No caller can
submit `candidate_passed=True` directly.

### First editable surface

Allow only:

- distillation instruction/prompt;
- evidence-selection policy;
- related-page candidate retrieval;
- merge/split guidance;
- quality-review rubric and context composition, with the evaluator's scoring
  policy held fixed.

Keep read-only:

- content permissions and destination policy;
- original sessions/events;
- secret detection/redaction;
- allowed paths and deletion rules;
- evaluator implementation and corpus labels;
- model/budget authority;
- acceptance and promotion code;
- Git and release controls.

## Persistence

```text
agentworkmemory.db
  harness_versions
  distillation_traces
  distillation_feedback
  harness_experiments
  harness_candidates
  harness_trials
  harness_promotions

<state>/experiments/artifacts/<sha256>/...
  bounded evidence bundle
  candidate patch/diff
  before/after page snapshots
  validation and reviewer raw outputs

<state>/experiments/worktrees/<experiment>/<attempt>/...
  temporary candidate checkout
```

SQLite owns lifecycle and transactions. Files own large immutable artifacts.
Every file reference is content-addressed and has a retention class. Successful
promotion does not silently delete evidence; abandoned worktrees are removable
after their patch and hashes are secured.

## Reuse interface

```python
context = memory.context(workspace=..., task=..., budget=...)
hits = memory.recall(query=..., workspace=..., budget=...)
source = memory.open(reference=..., budget=...)
candidate = memory.propose_candidate(...)
```

Rules:

- service first, transport second;
- confirmed Wiki and explicitly confirmed working state only;
- stable provenance on every non-metadata claim;
- candidate-only agent writes;
- content level and destination fixed at connection/request boundary;
- lexical retrieval first;
- no passive reinforcement merely because a memory was injected;
- access receipts record references and sizes, not returned private bodies;
- retrieval quality is evaluated with stored questions before adding vectors.

## Patterns adopted

- ports and adapters for curator, evaluator, proposer, and memory transport;
- functional core / imperative shell for gates and scoring versus subprocesses,
  Git, SQLite, and files;
- command/query separation between experiment mutations and recall;
- state machine for experiment and promotion lifecycles;
- content-addressed artifacts plus transactional metadata;
- shadow evaluation before any active-harness change.

## Patterns rejected for now

- event sourcing for all AWM state;
- a generic provider/plugin registry;
- automatic Git merge, commit, push, or deployment;
- autonomous modification of validators, permissions, evaluator, or optimizer;
- vector database and knowledge-graph spreading without measured lexical misses;
- automatic forgetting of confirmed durable knowledge;
- direct dependency of AWM core on NOOA or any single agent runtime.

