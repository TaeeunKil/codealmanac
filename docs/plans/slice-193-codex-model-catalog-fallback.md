# Slice 193: Codex model catalog compatibility fallback

## Goal

Allow the experimental Codex proposer to recover from the Codex CLI 0.145
model-cache shape mismatch where `models_cache.json` entries omit the now
required `base_instructions` field.

## Scope

- Detect only the specific model-cache deserialization failure.
- Build a temporary `model_catalog_json` override from the local Codex cache,
  filling missing `base_instructions` with a stable minimal instruction.
- Remove Pydantic-only string `format` metadata from the structured-output
  schema before passing it to Codex strict JSON schema validation.
- Run the proposer with user config, app/plugin connectors, multi-agent
  collaboration, and code mode disabled; the proposer needs only its bounded
  shell/worktree surface.
- Retry the same bounded Codex invocation at most once, then preserve the
  normal sanitized failure behavior.
- Remove the temporary catalog after the invocation.
- Leave the user's global Codex cache and AWM repository untouched.

## Non-goals

- Do not mutate or repair `%USERPROFILE%\\.codex\\models_cache.json`.
- Do not retry arbitrary Codex failures.
- Do not change the selected model, reasoning effort, sandbox, or network
  policy.

## Verification

- Unit-test the command override and one-time retry behavior.
- Run the focused improvement proposer tests and the full AWM suite.
- Run one real `awm improve propose` against the prepared run and inspect the
  detached candidate before reporting it.
