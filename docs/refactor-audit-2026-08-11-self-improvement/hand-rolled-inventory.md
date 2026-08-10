# Hand-rolled machinery inventory

## Improvement JSON store

What is hand-rolled:

- directory staging and atomic publication;
- JSON manifests for runs, attempts, candidates, and evaluations;
- cross-file lifecycle transitions;
- directory scans for queries;
- independent worktree retention.

Existing capability:

- AWM already owns a SQLite/WAL database, typed stores, transaction semantics,
  indexed queries, and receipts.

Judgment: **redesign**.

Keep immutable large artifacts and candidate worktrees on disk. Put lifecycle
state, identities, content hashes, transitions, and artifact references in
SQLite. Export a readable experiment bundle when inspectability is needed.
This deletes reconciliation debt without hiding artifacts from engineers.

## Full evidence copying

What is hand-rolled:

- every selected event is projected into a second `evidence.json` when local
  content is enabled.

Existing capability:

- canonical normalized events already live in SQLite;
- distillation already has bounded evidence selection.

Judgment: **replace with a bounded, content-addressed evidence bundle**.

Store event identities, selection reasons, excerpts actually sent, hashes, and
the permission/destination receipt. Do not copy all event bodies indefinitely.

## Codex process/JSONL parser

What is hand-rolled:

- command construction, schema file lifecycle, JSONL event selection, error
  normalization, timeout, and structured proposal parsing.

Existing capability:

- AWM already uses Yoke and curator adapters for provider execution;
- the proposer has stricter worktree/sandbox needs than ordinary distillation.

Judgment: **keep temporarily behind the port; compare before consolidating**.

Do not force reuse if the shared runtime cannot express the exact sandbox and
structured-output contract. Extract common bounded process/error behavior only
after a second real caller proves the seam.

## Git subprocess wrapper

What is hand-rolled:

- HEAD lookup, detached worktree creation, detached verification, and porcelain
  status parsing.

Existing capability:

- Git CLI is the authoritative mechanism; GitPython would add a large
  dependency without removing the need to understand worktrees.

Judgment: **keep custom, narrow, and tested**.

Add patch/content hashing, worktree removal/prune, and reconciliation only when
the full lifecycle is implemented.

## Acceptance gate

What is hand-rolled:

- held-in fix and no-regression rules.

Existing capability:

- no general library can own AWM's product acceptance policy.

Judgment: **keep deterministic policy, redesign its input**.

The gate should consume paired trial artifacts with corpus/version identity and
repetition statistics, not caller-supplied pass booleans.

## Distillation outcome classifier

What is hand-rolled:

- created/merged/already-covered/no-durable classification inferred from page
  citations and changed paths.

Judgment: **simplify and make honest**.

Separate mechanical attribution from quality. A changed page that fails to cite
the selected session is an attribution failure, not automatically “no durable
knowledge.” Record both facts and let fixed validation reject malformed source
metadata.

## MCP-first active-memory draft

What is proposed:

- a new store, reference scheme, recall policy, access receipts, MCP adapter,
  CLI, Viewer review UI, and NOOA example in one design.

Judgment: **split**.

Build the provider-neutral query/review service first. Evaluate it through a
Python API and current UI/CLI. Add one transport after retrieval quality and
permission behavior are measured. Do not hand-roll MCP framing; use the official
SDK when transport work is authorized.

