# Source map

## Current product contract

| Source | Relevance |
| --- | --- |
| `CLAUDE.md` | Canonical AWM product name, layers, state/Vault ownership, and slice workflow. |
| `MANUAL.md` | Living-architecture rules and the current assertion that AI is invoked only for explicit or explicitly scheduled distillation. The new proposer conflicts with this text. |
| `README.md` | Public product surface: capture, sync, distill, search, viewer, remotes, and Vault Git. It does not document `awm improve`. |
| `docs/agent-work-memory-user-guide.md` | Public content-access semantics and operational workflow. |

## Dedicated harness improvement

| Source | Relevance |
| --- | --- |
| `docs/plans/slice-190-self-improvement-harness-foundation.md` | Original intent: evidence-grounded runs, one candidate, held-in/out gate, no autonomous editing. |
| `docs/plans/fixes-slice-190-review.md` | Records immutable-run fixes, single-candidate lifecycle, duplicate-eval defense, and residual cross-file crash gap. |
| `docs/plans/slice-191-configurable-codex-improvement-proposer.md` | Adds Codex policy, attempt history, worktree mutation, and explicit non-promotion boundary. |
| `docs/plans/fixes-slice-191-review.md` | Records baseline-advance and false-failure fixes; explicitly defers evaluation, promotion, merge, and cleanup. |
| `src/agentworkmemory/services/improvement/models.py` | Broad component taxonomy, run/candidate/attempt/evaluation shapes. |
| `src/agentworkmemory/services/improvement/gate.py` | Deterministic held-in/held-out policy. |
| `src/agentworkmemory/services/improvement/service.py` | Lifecycle transitions and path revalidation. |
| `src/agentworkmemory/services/improvement/store.py` | JSON artifact layout, atomic per-file publication, worktree locations. |
| `src/agentworkmemory/workflows/improve_harness/service.py` | Evidence preparation, proposer orchestration, and evaluator port use. |
| `src/agentworkmemory/integrations/improvement/codex.py` | Codex CLI policy, prompt, structured output, and observed-path enforcement. |
| `src/agentworkmemory/integrations/improvement/git.py` | Detached worktree and Git inspection mechanics. |
| `src/agentworkmemory/cli.py` | Publicly reachable improve commands; no evaluation/promotion commands. |
| `tests/test_agentworkmemory_improvement*.py` | Strong unit coverage using temporary repositories and fake proposer execution; no live end-to-end proof. |

## Memory-making loop

| Source | Relevance |
| --- | --- |
| `src/agentworkmemory/workflows/distill/prompt.py` | Current first-intent plus recent-event evidence selection and fixed character budget. |
| `src/agentworkmemory/agents/distill.md` | Curator rubric, allowed durable categories, provenance, secret omission, and no-op policy. |
| `src/agentworkmemory/workflows/distill/service.py` | Isolated curator run, change validation/apply, outcome classification, receipts, and session completion. |
| `src/agentworkmemory/services/distillation/outcomes.py` | Created/merged/already-covered/no-durable attribution based only on citations and changed paths. |
| `src/agentworkmemory/services/vault/service.py` | Snapshot, allowed-path validation, apply, and rollback boundary. |
| `src/agentworkmemory/services/wiki/service.py` | Wiki parsing, sources, links, and generated indexes. |
| `docs/workalmanac-distill-plan.md` | Original distillation boundary and deferred automation/evaluation work. |

## Active-memory direction

| Source | Relevance |
| --- | --- |
| `docs/plans/slice-190-agent-memory-reconnection-interface.md` | Explicitly incomplete MCP-first draft. Defines bounded context/recall/open and candidate-only writes, but awaits NOOA-related redesign. It also reuses slice number 190, creating plan identity ambiguity. |

## Historical precursors

| Source | Relevance |
| --- | --- |
| `archive/code/prompts/operations/absorb.md` | Incremental durable-knowledge extraction from a concrete input. |
| `archive/code/prompts/operations/garden.md` | Whole-graph cleanup, human review escalation application, and no-op discipline. |
| `docs/plans/2026-05-28-review-escalations.md` | Human decisions inserted into an otherwise agent-operated Wiki maintenance loop. |
| `docs/plans/2026-05-14-auto-update.md` and `2026-07-06-scheduled-auto-update.md` | Package update automation. Relevant as an example of a misleading “self-update” label, not learning. |
| `docs/research/2026-05-08-auto-updating-wiki-algorithms.md` | Early investigation of incremental Wiki maintenance. |
| `docs/research/2026-05-08-auto-generating-wikis-deep-research.md` | Memory evolution, reflection, retrieval, and evaluation research groundwork. |

## Git milestones

| Commit | Meaning |
| --- | --- |
| `652c5787` | Self-improvement harness foundation. |
| `dde25d9f` | Configurable Codex improvement proposer. |
| `5e2d4a49` | Local merge of the improvement branch into `main`. |
| `18518268` | Incomplete memory-reconnection design draft. |

## Local runtime evidence, summarized safely

- canonical improvement run count: 0;
- related successful distillation receipts: 4;
- selected sessions across those receipts: 7;
- durable topic pages affected: project, decision, and unfinished-work pages;
- direct quality anomalies: changed pages paired with no-durable outcomes and
  malformed/duplicated source metadata.

No retained event bodies or private session identifiers are copied into this
audit.

