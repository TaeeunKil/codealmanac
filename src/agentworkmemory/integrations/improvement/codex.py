import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError
from yoke.providers.codex_cli import write_schema
from yoke.structured import provider_schema

from agentworkmemory.integrations.curators.hidden_codex import ORIGINATOR_ENV
from agentworkmemory.integrations.curators.yoke import standalone_codex_executable
from agentworkmemory.integrations.improvement.git import (
    GitWorktreeManager,
    sanitized_process_output,
)
from agentworkmemory.integrations.processes import hidden_process_creation_flags
from agentworkmemory.services.improvement.models import (
    ImprovementCandidateProposal,
    ImprovementProposalAttempt,
    ImprovementProposerPolicy,
    ImprovementRun,
    require_paths_inside_surface,
)

CODEX_TIMEOUT_SECONDS = 30 * 60
AWM_ORIGINATOR = "awm_improvement"


class CodexProcess(Protocol):
    def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        policy: ImprovementProposerPolicy,
    ) -> ImprovementCandidateProposal: ...


class CodexProposerError(RuntimeError):
    """A bounded, inspectable failure at the Codex proposer boundary."""


class CodexProcessRunner:
    """Run one structured-output Codex CLI turn with an explicit policy."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_seconds: float = CODEX_TIMEOUT_SECONDS,
        run_process: Callable[..., object] | None = None,
    ) -> None:
        self.executable = executable or standalone_codex_executable()
        self.timeout_seconds = timeout_seconds
        self.run_process = run_process

    def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        policy: ImprovementProposerPolicy,
    ) -> ImprovementCandidateProposal:
        schema = provider_schema(ImprovementCandidateProposal)
        schema_path = write_schema(schema)
        command = codex_command(
            self.executable,
            cwd,
            policy,
            schema_path,
        )
        environment = dict(os.environ)
        environment.setdefault(ORIGINATOR_ENV, AWM_ORIGINATOR)
        try:
            process_runner = self.run_process or subprocess.run
            completed = process_runner(
                command,
                input=prompt.encode("utf-8"),
                cwd=cwd,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self.timeout_seconds,
                creationflags=hidden_process_creation_flags(),
            )
        except subprocess.TimeoutExpired as error:
            raise CodexProposerError("Codex proposer timed out") from error
        except OSError as error:
            raise CodexProposerError("Codex proposer could not start") from error
        finally:
            schema_path.unlink(missing_ok=True)

        returncode = completed.returncode
        if returncode != 0:
            detail = sanitized_process_output(completed.stderr)
            suffix = f": {detail}" if detail else ""
            raise CodexProposerError(
                f"Codex proposer exited with code {returncode}{suffix}"
            )
        return parse_codex_jsonl(completed.stdout)


class CodexImprovementProposer:
    """Create a detached worktree and ask Codex for one candidate proposal."""

    def __init__(
        self,
        *,
        worktree_manager: GitWorktreeManager | None = None,
        process: CodexProcess | None = None,
        executable: str | None = None,
    ) -> None:
        self.worktree_manager = worktree_manager or GitWorktreeManager()
        self.process = process or CodexProcessRunner(executable=executable)

    def propose(
        self,
        run: ImprovementRun,
        attempt: ImprovementProposalAttempt,
        previous_attempts: tuple[ImprovementProposalAttempt, ...],
    ) -> ImprovementCandidateProposal:
        if attempt.run_id != run.run_id:
            raise ValueError("improvement attempt belongs to a different run")
        if attempt.base_revision != run.base_revision:
            raise ValueError("improvement attempt revision differs from its run")
        worktree = self.worktree_manager.create_detached(
            run.repository,
            attempt.worktree,
            attempt.base_revision,
        )
        validate_editable_surface(worktree, run.editable_paths)
        proposal = self.process.run(
            improvement_prompt(run, attempt, previous_attempts),
            cwd=worktree,
            policy=attempt.policy,
        )
        self.worktree_manager.verify_detached_at(worktree, attempt.base_revision)
        changed_paths = self.worktree_manager.changed_paths(worktree)
        if not changed_paths:
            raise CodexProposerError("Codex proposer did not change any files")
        validate_observed_paths(worktree, changed_paths)
        require_paths_inside_surface(changed_paths, run.editable_paths)
        return proposal.model_copy(update={"changed_paths": changed_paths})


def codex_command(
    executable: str,
    cwd: Path,
    policy: ImprovementProposerPolicy,
    schema_path: Path,
) -> tuple[str, ...]:
    return (
        executable,
        "exec",
        "--json",
        "--cd",
        str(cwd),
        "--model",
        policy.model,
        "--sandbox",
        "workspace-write",
        "--config",
        'approval_policy="never"',
        "--config",
        f"model_reasoning_effort={json.dumps(policy.reasoning_effort.value)}",
        "--config",
        "sandbox_workspace_write.network_access=false",
        "--config",
        'web_search="disabled"',
        "--config",
        "mcp_servers={}",
        "--output-schema",
        str(schema_path),
        "-",
    )


def parse_codex_jsonl(raw_output: bytes | str) -> ImprovementCandidateProposal:
    text = (
        raw_output.decode("utf-8", errors="replace")
        if isinstance(raw_output, bytes)
        else raw_output
    )
    structured_output: str | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise CodexProposerError("Codex emitted invalid JSONL") from error
        if not isinstance(event, dict):
            raise CodexProposerError("Codex emitted an invalid JSONL event")
        event_type = event.get("type")
        if event_type in {"error", "turn.failed"}:
            detail = event.get("message")
            if not isinstance(detail, str):
                error_payload = event.get("error")
                detail = (
                    error_payload.get("message")
                    if isinstance(error_payload, dict)
                    else None
                )
            suffix = f": {sanitized_process_output(detail)}" if detail else ""
            raise CodexProposerError(f"Codex turn failed{suffix}")
        if event_type != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        output = item.get("text")
        if not isinstance(output, str):
            raise CodexProposerError("Codex returned a non-text structured proposal")
        structured_output = output

    if structured_output is None or not structured_output.strip():
        raise CodexProposerError("Codex returned no structured candidate proposal")
    try:
        return ImprovementCandidateProposal.model_validate_json(structured_output)
    except ValidationError as error:
        raise CodexProposerError(
            "Codex structured candidate proposal did not match its schema"
        ) from error


def improvement_prompt(
    run: ImprovementRun,
    attempt: ImprovementProposalAttempt,
    previous_attempts: tuple[ImprovementProposalAttempt, ...],
) -> str:
    evidence = tuple(
        selection.model_dump(mode="json") for selection in run.evidence
    )
    previous = tuple(
        {
            "attempt_id": previous_attempt.attempt_id,
            "state": previous_attempt.state.value,
            "model": previous_attempt.policy.model,
            "reasoning_effort": previous_attempt.policy.reasoning_effort.value,
            "failure": previous_attempt.failure,
            "candidate_id": previous_attempt.candidate_id,
        }
        for previous_attempt in previous_attempts
    )
    return f"""You are proposing one controlled Agent Work Memory harness improvement.

The current candidate worktree is already checked out at the prepared base
revision. Work only in that worktree and only within the editable paths below.
Do not access the AWM state directory, Vault, baseline checkout, or any other
workspace.

Prepared run: {run.run_id}
Attempt: {attempt.attempt_id}
Base revision: {run.base_revision}
Editable paths: {json.dumps(tuple(path.as_posix() for path in run.editable_paths))}

Prepared evidence:
{json.dumps(evidence, indent=2, ensure_ascii=False)}

Previous attempt summaries:
{json.dumps(previous, indent=2, ensure_ascii=False)}

Acceptance rules:
- Address a concrete failure shown by the prepared evidence.
- Preserve passing behavior and existing safety boundaries.
- Make the smallest coherent change within the editable surface.
- Do not commit, create branches, change worktrees, or alter Git metadata.
- Do not claim a path that was not actually changed; AWM will verify Git paths.
- Return a complete semantic candidate manifesto through the structured output
  schema, including failure evidence, root cause, targeted fix, predicted impact,
  regression risks, and claimed changed paths.
""".rstrip()


def validate_editable_surface(worktree: Path, editable_paths: tuple[Path, ...]) -> None:
    root = worktree.resolve(strict=False)
    for relative in editable_paths:
        target = (root / relative).resolve(strict=False)
        if not target.is_relative_to(root):
            raise CodexProposerError(
                "prepared editable surface resolves outside the candidate worktree"
            )


def validate_observed_paths(
    worktree: Path,
    changed_paths: tuple[Path, ...],
) -> None:
    root = worktree.resolve(strict=False)
    for relative in changed_paths:
        target = (root / relative).resolve(strict=False)
        if not target.is_relative_to(root):
            raise CodexProposerError(
                "Codex changed a path outside the candidate worktree"
            )


CodexProposer = CodexImprovementProposer

__all__ = [
    "CodexImprovementProposer",
    "CodexProcessRunner",
    "CodexProposer",
    "CodexProposerError",
    "codex_command",
    "improvement_prompt",
    "parse_codex_jsonl",
]
