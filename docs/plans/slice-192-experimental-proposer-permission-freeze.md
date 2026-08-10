# Slice 192: experimental proposer freeze and content permission boundary

## Intent

Make the existing Slice 191 candidate generator honest and permission-safe
before adding evaluation or replay machinery. The proposer remains available
for explicitly enabled experiments, but the ordinary `awm improve` surface must
not silently run an unfinished self-improvement loop or widen a local-content
grant into a remote-model transfer.

## Product boundary

`awm improve settings`, `list`, and `show` remain inspection-only operations.
`prepare` and `propose` require an explicit `--experimental` flag. The flag is
a CLI acknowledgement, not a persistent setting and not a model/budget grant.
The help text and manual call the surface experimental candidate generation;
there is still no automatic evaluation, promotion, merge, or push.

## Content and destination contract

Codex is treated as a remote model destination for this integration. Extend the
typed proposer policy and one-attempt request with an explicit
`allow_remote_content` grant, defaulting to false. Persist the effective grant
in the attempt manifest alongside the model and reasoning effort.

The workflow rejects `SELECTED_LOCAL` evidence for the Codex proposer before a
process starts. A local-only grant cannot be upgraded later. If a future
remote-content evidence mode contains bodies, it also requires the explicit
per-attempt grant. Metadata-only evidence remains usable without the grant.

The integration repeats the checks immediately before prompt construction so a
direct caller or a future workflow cannot bypass the policy boundary. No body
may appear in a Codex prompt unless the effective policy explicitly grants the
remote destination.

## Typed shape

```python
class ImprovementProposerPolicy(AgentWorkMemoryModel):
    runtime: Literal["codex"] = "codex"
    model: str
    reasoning_effort: ReasoningEffort
    allow_remote_content: bool = False


class ProposeImprovement(AgentWorkMemoryModel):
    run_id: ImprovementIdentifier
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    allow_remote_content: bool = False
```

The default is deny. The policy is the single effective value used by the
workflow, attempt history, prompt boundary, and integration guard.

## Required tests

- ordinary CLI `prepare` and `propose` fail unless `--experimental` is present;
- inspection-only improve commands remain available without the flag;
- selected-local preparation followed by Codex proposal is rejected before the
  proposer process starts, even when `--allow-remote-content` is requested;
- metadata-only proposals work without a remote-content grant and contain no
  event bodies;
- body-bearing evidence cannot reach Codex without the explicit grant;
- the effective grant is immutable and round-trips in the attempt manifest;
- direct Codex integration calls repeat the same body/destination guard;
- existing fake Codex proposer tests remain deterministic and no live model,
  Vault, or retained state is touched.

## Non-goals

This slice does not add `DistillationTrace`, replay cases, a concrete evaluator,
trial artifacts, promotion, SQLite migration, cleanup/reconciliation, or live
Codex dogfood. Those follow the roadmap only after this boundary is verified.

## Ownership and verification

The parent owns this design, review, and final commit. Luna Max owns production
code, tests, and implementation-driven amendments. Run the focused improvement
suite, the full test suite, Ruff, viewer JavaScript syntax, and diff checks.
