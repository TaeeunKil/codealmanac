# Worklog

## Goal

Critically audit every self-improvement attempt in Agent Work Memory—implemented,
experimental, historical, or planned—to determine what exists, what actually
closes a feedback loop, and what should be preserved, simplified, removed, or
redesigned.

## Core questions

- Why does each mechanism exist?
- Does it learn from outcomes, or merely automate work?
- Is there a measured objective and a trustworthy evaluator?
- Can a candidate alter evidence, evaluation, permissions, or promotion?
- Does learned memory return to later work?
- Is the current shape the smallest safe shape for the product?

## Non-goals

- Do not modify production code.
- Do not run a live paid proposer.
- Do not mutate the real AWM state, Vault, schedules, or Git branches.
- Do not treat passing unit tests as proof of a complete learning loop.

## Investigation log

### 2026-08-11 — repository orientation

- Read `CLAUDE.md`, `MANUAL.md`, and the deep-refactor-audit skill.
- Confirmed the active product is `src/agentworkmemory/`; `src/codealmanac/`
  and `archive/code/` are historical reference.
- Mapped the active improvement service, workflow, integrations, app wiring,
  CLI, tests, plans, Git history, and local/remote branches.
- Found local `main` ahead of `origin/main` by four commits, including the two
  improvement commits, their merge, and the memory-reconnection draft.

### 2026-08-11 — current implementation trace

- Traced prepare: explicitly selected sessions -> copied evidence -> Git HEAD
  anchor -> immutable run.
- Traced propose: policy resolution -> attempt -> detached worktree -> Codex
  structured turn -> Git-observed paths -> candidate -> attempt finalization.
- Traced evaluate: a caller/evaluator supplies case booleans -> fixed gate ->
  qualified/rejected report.
- Confirmed there is no concrete evaluator implementation and no CLI evaluation
  or promotion surface.
- Confirmed worktrees are retained with no cleanup/reconciliation operation.
- Confirmed JSON lifecycle transitions are atomic per file/directory but not
  transactional across run, attempt, candidate, and evaluation artifacts.

### 2026-08-11 — verification

- `uv run pytest tests/test_agentworkmemory_improvement.py
  tests/test_agentworkmemory_improvement_proposer.py -q`: 33 passed.
- Focused Ruff check: passed.
- `git diff --check`: passed.
- CLI help confirmed exactly six operations: prepare, settings, configure,
  propose, list, show.
- Full AWM suite, expanded explicitly for PowerShell: 203 passed.
- Viewer JavaScript syntax and final diff check: passed.
- Repository-wide focused AWM Ruff currently reports four pre-existing E501
  findings in the recently added systemd scheduler code/tests. The audit did
  not modify those unrelated files; the improvement-specific Ruff scope passes.

### 2026-08-11 — local dogfood evidence

- Read the canonical local improvement directory and CLI list without opening
  retained evidence bodies: zero improvement runs exist.
- Queried body-free session metadata and distillation receipts in read-only
  mode.
- Confirmed the memory system retained the self-improvement design work and
  four successful distillation runs updated three durable topic pages.
- Read only the relevant durable pages. They already state that quality tracing
  and replay evaluation should precede automatic source editing.
- Observed mismatches between changed-file receipts and per-session
  `no-durable-knowledge` classifications, plus malformed/duplicated source
  frontmatter. These are direct examples of why structural completion is not a
  quality metric.
- Did not modify the heavily dirty user Vault.

### 2026-08-11 — prior art

- Reviewed Lilian Weng's harness-engineering synthesis and the primary
  Self-Harness, AHE, and Meta-Harness papers.
- Reviewed the current NVIDIA NOOA memory package documentation because the
  local memory draft explicitly defers design pending selective absorption.
- Kept only patterns compatible with AWM's person-owned evidence and
  human-reviewed durable memory.

## Success criteria status

- Current architecture mapped: complete.
- Major boundaries judged: complete.
- Questionable features called out: complete.
- Hand-rolled machinery assessed: complete.
- Legitimate and accidental complexity separated: complete.
- Prior art researched: complete.
- Target architecture and roadmap written: complete.
