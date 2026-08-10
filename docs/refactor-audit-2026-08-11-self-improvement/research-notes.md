# Research notes

## Harness evolution

[Lilian Weng's harness-engineering synthesis](https://lilianweng.github.io/posts/2026-07-04-harness/)
organizes self-improving harness work around weakness mining, bounded proposals,
held-in/held-out validation, observability, and fixed permission/evaluation
boundaries. Slices 190 and 191 copied several of these shapes accurately, but
implemented proposal before experience observability and concrete validation.

[Self-Harness](https://arxiv.org/abs/2606.09498) uses weakness mining,
harness proposal, and regression-tested validation. Its relevance to AWM is
sequencing: failures must be mined from verifier-grounded traces before edits
are proposed.

[Agentic Harness Engineering](https://arxiv.org/abs/2604.25850) separates
component, experience, and decision observability. The current AWM component
enum and candidate manifesto resemble its component/decision layers. AWM lacks
the layered experience corpus and trial feedback that make those edits
falsifiable.

[Meta-Harness](https://arxiv.org/abs/2603.28052) lets an outer-loop coding agent
inspect source, scores, and prior traces through the filesystem. The useful
lesson is artifact accessibility, not that lifecycle state itself must be a
custom JSON database.

## NOOA memory

The current [NOOA memory package](https://github.com/NVIDIA-NeMo/labs-OO-Agents/tree/main/packages/nooa-memory/src/nooa_memory)
offers agent-authored memory, deliberate and spontaneous recall, reflection,
forgetting, typed references/edges, hybrid retrieval, and observability.

Selective ideas worth borrowing:

- explicit recall plus bounded passive context;
- passive recall does not reinforce an item merely because it was injected;
- stable references and access/operation counters;
- reflection reports that say what merged, superseded, or pruned;
- benchmark scenarios proving when memory helps or hurts;
- retrieval and reflection as optional policies behind ports.

Ideas to reject or defer for AWM:

- agent-authored memory becoming authoritative without user review;
- automatic event-driven writes into confirmed memory;
- direct per-agent ownership rather than person ownership;
- automatic forgetting of durable decisions/procedures;
- ACT-R scoring, graph spreading, embeddings, and multiple vector backends
  before lexical retrieval has a measured failure set;
- a second independent memory database;
- executing model-generated Python as part of the memory boundary.

Inference: the incomplete memory-reconnection draft is directionally right to
keep AWM provider-neutral and candidate-only for writes. It should absorb
NOOA's measured retrieval/observability ideas, not its ownership or automatic
mutation model.

