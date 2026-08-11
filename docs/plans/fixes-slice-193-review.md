# Slice 193 review fixes

## Review findings

The real proposer run exposed two integration defects that unit fakes did not
exercise:

1. Codex CLI 0.145.0 rejected the locally refreshed model cache because its
   entries omitted the required `base_instructions` field.
2. The structured-output schema generated from the domain model advertised
   Pydantic's `format: path`, which is outside the strict JSON schema subset
   accepted by the Responses API.
3. The CLI model catalog injected the desktop app's full instructions and
   enabled nested tools, so the proposer delegated and polled instead of
   converging on one candidate.

## Fixes

- Retry only the model-cache shape error once with a temporary repaired
  `model_catalog_json`; the user's global cache is never changed.
- Strip Pydantic-only `format` metadata from the wire schema while preserving
  domain validation on the parsed candidate.
- Replace the catalog instruction template for the fallback invocation and
  disable app/plugin, multi-agent, and code-mode surfaces for the proposer.
- Added regression tests for both behaviors and cleanup of the temporary
  catalog.

## Verification

- Focused proposer tests: 20 passed.
- Full AWM test suite: 210 passed.
- Touched Ruff checks: passed.
- Viewer JavaScript syntax check: passed.
- Git diff check: passed.
