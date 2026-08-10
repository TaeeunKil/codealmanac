# Refactor roadmap

## Phase 0: freeze and make the experiment honest

Goal: prevent the local-only proposer from becoming an accidentally public,
misleading, or privacy-unsafe surface.

Changes:

- Do not push the local merge to remote `main` as-is.
- Mark `awm improve` experimental or hide it behind an explicit experimental
  enablement.
- Reject `SELECTED_LOCAL` evidence when the proposer destination is remote.
- Resolve content access and destination in the same proposal request.
- Update `MANUAL.md` and public contracts only after deciding whether explicit
  proposal is an allowed second AI invocation category.
- Record that no real improvement run has occurred.

Why first: this closes the only concrete permission contradiction and prevents
unit-tested machinery from being mistaken for a shipped learning loop.

Risk: low. It may temporarily reduce the CLI surface.

Verification:

- selected-local plus remote proposer is rejected before any process starts;
- metadata-only proposal remains possible;
- no retained body appears in a proposer request without an explicit matching
  destination grant.

## Phase 1: instrument current distillation

Goal: make every memory-writing run attributable and explainable.

Changes:

- Add `HarnessVersion`, `DistillEvidenceBundle`, and `DistillationTrace`.
- Version/hash current prompt, evidence selector, validator, runtime, and
  related-page context.
- Replace the current outcome ambiguity with separate facts: file changed,
  session cited, citation valid, quality reviewed, knowledge disposition.
- Validate source session IDs against retained sessions; reject duplicates,
  malformed entries, and missing required provider fields.
- Record exact excerpts and selection reasons rather than every event body.
- Add explicit correction/revert/missing-knowledge feedback verbs.

Why first: the existing durable decision already names this as the prerequisite
for self-improvement, and local dogfood shows concrete attribution defects.

Risk: medium. Trace volume and privacy scope need careful bounds.

Verification:

- one run can be reconstructed without reading unrelated transcript content;
- every changed page has valid, nonduplicated provenance;
- changed-file and per-session dispositions cannot contradict silently;
- traces contain no secrets or full unselected transcripts;
- current distillation behavior remains otherwise compatible.

## Phase 2: build the replay corpus and rubric

Goal: define “better memory” before optimizing it.

Changes:

- Curate at least 30 representative cases, stratified across short/long,
  success/failure, no-op, multi-project, sensitive-content, correction-heavy,
  and multiple-provider sessions.
- For each case, record expected durable claims, forbidden claims, required
  provenance, acceptable target pages, and retrieval questions.
- Keep a sealed held-out partition unavailable to the proposer.
- Add hard gates for paths, secrets, source integrity, YAML/frontmatter,
  deletion, and idempotency.
- Add quality measures for expected-claim coverage, canonical-page reuse,
  duplicates/thin pages, unfinished-work retention, retrieval answerability,
  user correction, cost, and latency.

Why second: a proposer without a task distribution and utility function cannot
produce attributable improvement.

Risk: medium. Human labels can be inconsistent; store rationale and allow
reviewed revisions.

Verification:

- two reviewers can explain each expected/forbidden label;
- baseline scores are reproducible enough to distinguish real changes;
- the corpus includes known current failures, including middle-session evidence
  loss and malformed attribution.

## Phase 3: implement paired shadow evaluation

Goal: compare active and candidate harnesses without touching the live Vault.

Changes:

- Implement one concrete `PairedReplayEvaluator`.
- Run baseline and candidate against identical isolated Vault snapshots and
  evidence bundles.
- Persist immutable trial artifacts, harness/corpus identities, costs, and
  repetitions.
- Derive gate decisions from trial artifacts rather than submitted booleans.
- Repeat stochastic cases (recommended three paired repetitions initially) and
  report uncertainty instead of collapsing directly to one boolean.
- Add CLI `experiment evaluate/show-trials` for operators; no promotion yet.

Why third: this is the first point at which a candidate patch can be called an
evaluated experiment.

Risk: high cost and nondeterminism. Bound corpus size and model budget during
development.

Verification:

- a known bad candidate is rejected;
- a known targeted fix improves its held-in case and does not regress sealed
  cases;
- evaluator/corpus files are not writable from the candidate worktree;
- no trial mutates the live Vault or baseline checkout.

## Phase 4: reshape and restore the proposer

Goal: reuse the good Slice 190/191 seams inside a complete experiment lifecycle.

Changes:

- Rename improvement concepts to harness experiments/candidates.
- Move lifecycle metadata to SQLite and retain content-addressed artifacts.
- Reconcile or clean started attempts and abandoned worktrees.
- Narrow the editable surface to distillation components.
- Make the proposer consume weakness clusters, passing behaviors, prior trial
  artifacts, and registered predictions.
- Verify real sandbox read/write boundaries with canary files; do not rely only
  on command-argument assertions.
- Run the first opt-in metadata-only live proposer dogfood.

Why fourth: candidate generation becomes useful only after evaluation can reject
it honestly.

Risk: high. Live model execution, filesystem access, and retained worktrees need
operator visibility.

Verification:

- real attempt creates a reviewable patch at the anchored revision;
- it cannot read fixed-control canaries or write outside the candidate surface;
- failed/interrupted attempts reconcile deterministically;
- retry history and policy remain attributable;
- patch, prompt, evidence bundle, and trial artifacts share one experiment ID.

## Phase 5: human promotion

Goal: close the first safe harness-learning loop without autonomous deployment.

Changes:

- Add explicit qualified/rejected/reviewed/promoted states and receipts.
- Render patch, manifesto, paired metrics, regressions, cost, and uncertainty.
- Let the user approve application to a normal review branch or reject it with
  feedback.
- Re-run repository gates after application and before commit.
- Produce a new `HarnessVersion` only after the normal repository review/fix
  ritual completes.

Why fifth: promotion is a product decision, not an evaluator side effect.

Risk: merge drift between anchored base and current branch.

Verification:

- stale-base candidates require rebase/re-evaluation;
- rejection leaves active behavior unchanged;
- promotion produces an auditable version transition;
- no command auto-pushes or auto-deploys.

## Phase 6: reconnect memory to active agents

Goal: let later work benefit from confirmed memory while preserving provenance
and human authority.

Changes:

- Split the incomplete MCP draft into service, retrieval-evaluation, review UI,
  and transport plans with unique slice numbers.
- Implement provider-neutral `context`, `recall`, and `open` over existing Wiki
  and retained evidence.
- Add access receipts and hard budgets.
- Evaluate lexical retrieval against the replay corpus's stored questions.
- Add candidate-only agent writes and user confirmation.
- Add one transport—MCP is reasonable—only after the service contract passes.
- Borrow NOOA's explicit/passive recall separation and observability, but not
  direct authoritative agent writes, automatic forgetting, or a second memory
  database.

Why sixth: reuse closes the memory loop and supplies future signals about which
durable knowledge actually helps.

Risk: privacy leakage and context pollution.

Verification:

- unrelated workspaces and candidates never leak;
- every returned body has provenance and obeys content/destination policy;
- passive injection does not reinforce items by itself;
- memory-on beats memory-off on stored cross-session questions without
  unacceptable cost or stale-memory regressions.

## Phase 7: consider unattended experiments, not unattended promotion

Goal: use idle time for bounded shadow trials after the manual loop proves
stable.

Changes:

- Schedule weakness mining or shadow evaluation under explicit budget/time
  grants.
- Keep proposal, evaluation, and promotion as separately permissioned actions.
- Surface queue, cost, failures, retained worktrees, and storage use.
- Require sustained improvement across multiple promotion cycles before
  widening editable components.

Why last: automation magnifies bad objectives and incomplete containment.

Risk: Goodhart effects, overfitting, cost drift, and silent distribution shift.

Verification:

- scheduled work can only create experiment artifacts;
- it cannot change the active harness, model, budget, validators, or Vault;
- operator review remains mandatory;
- longitudinal metrics show lower correction/repeat-investigation rates, not
  merely more pages or passing self-judgments.

## Recommended immediate ticket sequence

1. Permission contract fix and experimental freeze.
2. Distillation trace/version schema.
3. Bounded evidence compiler with selection reasons.
4. Citation/source validator and honest outcome model.
5. Explicit feedback records.
6. First 10 replay cases, then expand to 30 before candidate qualification.
7. Paired replay evaluator and trial artifacts.
8. Only then migrate and dogfood the existing Codex proposer.

