import json
import subprocess
from pathlib import Path

import pytest

from agentworkmemory.app import create_app
from agentworkmemory.cli import build_parser, main
from agentworkmemory.integrations.improvement import (
    CodexImprovementProposer,
    CodexProcessRunner,
    GitRevisionReader,
)
from agentworkmemory.services.curators.models import ReasoningEffort
from agentworkmemory.services.improvement import (
    HarnessComponent,
    ImprovementCandidateProposal,
    ImprovementProposalAttemptState,
    ImprovementProposerPolicy,
    ImprovementRunState,
)
from agentworkmemory.settings import (
    AgentWorkMemoryConfig,
    ImprovementProposerSettings,
    configure_improvement_proposer,
    load_config,
    save_config,
)
from agentworkmemory.workflows.improve_harness import (
    PrepareImprovementRun,
    ProposeImprovement,
)


def test_old_and_round_tripped_config_use_durable_luna_defaults(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    vault = (tmp_path / "vault").resolve()
    (state / "config.json").write_text(
        json.dumps({"vault_path": str(vault)}) + "\n",
        encoding="utf-8",
    )

    old = load_config(state)
    assert old.vault_path == vault
    assert old.improvement_proposer == ImprovementProposerSettings()

    configured = configure_improvement_proposer(
        old,
        model="custom-model",
        reasoning_effort=ReasoningEffort.MAX,
    )
    persisted = load_config(state)
    assert persisted.vault_path == vault
    assert persisted.improvement_proposer.model == "custom-model"
    assert persisted.improvement_proposer.reasoning_effort is ReasoningEffort.MAX
    assert not tuple(state.glob(".config.json.*.tmp"))
    assert configured.config_path.read_text(encoding="utf-8") == (
        state / "config.json"
    ).read_text(encoding="utf-8")


def test_configure_changes_only_explicit_proposer_fields(tmp_path: Path) -> None:
    config = AgentWorkMemoryConfig(
        state_dir=tmp_path / "state",
        vault_path=(tmp_path / "vault").resolve(),
        improvement_proposer=ImprovementProposerSettings(
            model="first-model",
            reasoning_effort=ReasoningEffort.HIGH,
        ),
    )
    save_config(config)

    model_only = configure_improvement_proposer(config, model="second-model")
    assert model_only.improvement_proposer.model == "second-model"
    assert model_only.improvement_proposer.reasoning_effort is ReasoningEffort.HIGH
    effort_only = configure_improvement_proposer(
        model_only,
        reasoning_effort=ReasoningEffort.MAX,
    )
    assert effort_only.improvement_proposer.model == "second-model"
    assert effort_only.improvement_proposer.reasoning_effort is ReasoningEffort.MAX
    assert effort_only.vault_path == config.vault_path

    with pytest.raises(ValueError, match="must not be blank"):
        configure_improvement_proposer(effort_only, model="   ")


def test_model_strings_are_nonblank_and_cli_propose_effort_is_typed() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        ImprovementProposerSettings(model="   ")

    args = build_parser().parse_args(
        ("improve", "propose", "imp_run", "--model", "new-model", "--effort", "max")
    )
    assert args.model == "new-model"
    assert args.effort is ReasoningEffort.MAX


def test_improve_settings_and_configure_are_canonical_cli_operations(
    tmp_path: Path,
    capsys,
) -> None:
    state = tmp_path / "state"
    assert main(("--state-dir", str(state), "improve", "settings")) == 0
    initial = capsys.readouterr().out
    assert "model: gpt-5.6-luna" in initial
    assert "reasoning effort: xhigh" in initial

    assert main(
        (
            "--state-dir",
            str(state),
            "improve",
            "configure",
            "--model",
            "cli-model",
            "--effort",
            "max",
        )
    ) == 0
    configured = capsys.readouterr().out
    assert "model: cli-model" in configured
    assert "reasoning effort: max" in configured
    persisted = load_config(state)
    assert persisted.improvement_proposer.model == "cli-model"
    assert persisted.improvement_proposer.reasoning_effort is ReasoningEffort.MAX


class RecordingProposer:
    def __init__(self, *, failure: Exception | None = None):
        self.failure = failure
        self.calls: list[tuple[str, ImprovementProposerPolicy, tuple[str, ...]]] = []

    def propose(self, run, attempt, previous_attempts):
        self.calls.append(
            (
                attempt.attempt_id,
                attempt.policy,
                tuple(item.attempt_id for item in previous_attempts),
            )
        )
        if self.failure is not None:
            raise self.failure
        return proposal(Path("src/model-claimed.py"))


def test_one_attempt_policy_override_is_recorded_without_mutating_defaults(
    tmp_path: Path,
) -> None:
    proposer = RecordingProposer()
    repository, _ = isolated_git_repository(tmp_path)
    app = create_app(
        AgentWorkMemoryConfig(
            state_dir=tmp_path / "state",
            improvement_proposer=ImprovementProposerSettings(
                model="durable-model",
                reasoning_effort=ReasoningEffort.HIGH,
            ),
        ),
        improvement_proposer=proposer,
    )
    session = app.sessions.add_manual_note("metadata", title="policy")
    run = app.improve_harness.prepare(
        PrepareImprovementRun(
            session_ids=(session.session_id,),
            repository=repository,
            editable_paths=(Path("src"),),
        )
    )

    candidate = app.improve_harness.propose(
        ProposeImprovement(
            run_id=run.run_id,
            model="one-shot-model",
            reasoning_effort=ReasoningEffort.MAX,
        )
    )

    assert candidate.changed_paths == (Path("src/model-claimed.py"),)
    assert proposer.calls[0][1] == ImprovementProposerPolicy(
        model="one-shot-model",
        reasoning_effort=ReasoningEffort.MAX,
    )
    assert app.config.improvement_proposer.model == "durable-model"
    assert app.config.improvement_proposer.reasoning_effort is ReasoningEffort.HIGH
    attempt = app.improvement.attempts(run.run_id)[0]
    assert attempt.policy.model == "one-shot-model"
    assert attempt.policy.reasoning_effort is ReasoningEffort.MAX
    assert attempt.state is ImprovementProposalAttemptState.SUCCEEDED


def test_failed_attempt_is_persisted_and_retry_receives_history(tmp_path: Path) -> None:
    proposer = RecordingProposer(failure=RuntimeError("model rejected request"))
    repository, _ = isolated_git_repository(tmp_path)
    app = create_app(
        AgentWorkMemoryConfig(state_dir=tmp_path / "state"),
        improvement_proposer=proposer,
    )
    session = app.sessions.add_manual_note("metadata", title="retry")
    run = app.improve_harness.prepare(
        PrepareImprovementRun(
            session_ids=(session.session_id,),
            repository=repository,
            editable_paths=(Path("src"),),
        )
    )

    with pytest.raises(RuntimeError, match="model rejected"):
        app.improve_harness.propose(ProposeImprovement(run_id=run.run_id))

    failed = app.improvement.attempts(run.run_id)
    assert len(failed) == 1
    assert failed[0].state is ImprovementProposalAttemptState.FAILED
    assert failed[0].failure == "model rejected request"
    assert app.improvement.get(run.run_id).state is ImprovementRunState.PREPARED

    proposer.failure = None
    app.improve_harness.propose(ProposeImprovement(run_id=run.run_id))
    assert proposer.calls[1][2] == (failed[0].attempt_id,)
    assert len(app.improvement.attempts(run.run_id)) == 2


def test_completion_failure_does_not_fail_persisted_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposer = RecordingProposer()
    repository, _ = isolated_git_repository(tmp_path)
    app = create_app(
        AgentWorkMemoryConfig(state_dir=tmp_path / "state"),
        improvement_proposer=proposer,
    )
    session = app.sessions.add_manual_note("metadata", title="completion")
    run = app.improve_harness.prepare(
        PrepareImprovementRun(
            session_ids=(session.session_id,),
            repository=repository,
            editable_paths=(Path("src"),),
        )
    )
    completion_candidate_ids: list[str] = []

    def raising_complete(attempt_id: str, candidate_id: str) -> None:
        completion_candidate_ids.append(candidate_id)
        assert len(app.improvement.candidates(run.run_id)) == 1
        raise RuntimeError("attempt completion failed")

    fail_calls: list[tuple[str, str]] = []
    original_fail_attempt = app.improvement.fail_attempt

    def recording_fail(attempt_id: str, failure: str):
        fail_calls.append((attempt_id, failure))
        return original_fail_attempt(attempt_id, failure)

    monkeypatch.setattr(app.improvement, "complete_attempt", raising_complete)
    monkeypatch.setattr(app.improvement, "fail_attempt", recording_fail)

    with pytest.raises(RuntimeError, match="attempt completion failed"):
        app.improve_harness.propose(ProposeImprovement(run_id=run.run_id))

    candidates = app.improvement.candidates(run.run_id)
    attempts = app.improvement.attempts(run.run_id)
    assert len(candidates) == 1
    assert len(completion_candidate_ids) == 1
    assert fail_calls == []
    assert attempts[0].state is ImprovementProposalAttemptState.STARTED
    assert (
        app.improvement.get(run.run_id).state
        is ImprovementRunState.CANDIDATE_RECORDED
    )


def test_attempt_manifest_keeps_identity_and_effective_policy_immutable(
    tmp_path: Path,
) -> None:
    repository, _ = isolated_git_repository(tmp_path)
    app = create_app(AgentWorkMemoryConfig(state_dir=tmp_path / "state"))
    session = app.sessions.add_manual_note("metadata", title="manifest")
    run = app.improve_harness.prepare(
        PrepareImprovementRun(
            session_ids=(session.session_id,),
            repository=repository,
            editable_paths=(Path("src"),),
        )
    )
    policy = ImprovementProposerPolicy(
        model="manifest-model",
        reasoning_effort=ReasoningEffort.XHIGH,
    )
    attempt = app.improvement.start_attempt(run.run_id, policy)
    manifest_path = (
        app.config.state_dir
        / "improvement"
        / "runs"
        / run.run_id
        / "attempts"
        / attempt.attempt_id
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["policy"] == {
        "runtime": "codex",
        "model": "manifest-model",
        "reasoning_effort": "xhigh",
    }
    assert Path(manifest["worktree"]) == attempt.worktree

    with pytest.raises(ValueError, match="policy is immutable"):
        app.improvement.store.update_attempt(
            attempt.model_copy(
                update={
                    "policy": ImprovementProposerPolicy(
                        model="other-model",
                        reasoning_effort=ReasoningEffort.MAX,
                    )
                }
            )
        )


def proposal(changed_path: Path) -> ImprovementCandidateProposal:
    return ImprovementCandidateProposal(
        component=HarnessComponent.SYSTEM_PROMPT,
        failure_evidence=("held-in failure",),
        root_cause="The boundary was omitted.",
        targeted_fix="State the boundary.",
        predicted_impact="The held-in case passes.",
        regression_risks=("Wording could become unclear.",),
        changed_paths=(changed_path,),
    )


def isolated_git_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = (tmp_path / "repository").resolve()
    repository.mkdir()
    run_git(repository, "init")
    (repository / "src").mkdir()
    (repository / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    run_git(repository, "add", ".")
    run_git(
        repository,
        "-c",
        "user.email=awm-test@example.com",
        "-c",
        "user.name=AWM Test",
        "commit",
        "-m",
        "base",
    )
    return repository, GitRevisionReader().head(repository)


def run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", *arguments),
        cwd=repository,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
    )


def test_codex_proposer_uses_explicit_sandbox_policy_and_observed_paths(
    tmp_path: Path,
) -> None:
    repository, base_revision = isolated_git_repository(tmp_path)
    app = create_app(AgentWorkMemoryConfig(state_dir=tmp_path / "state"))
    session = app.sessions.add_manual_note("prepared evidence", title="Codex")
    run = app.improve_harness.prepare(
        PrepareImprovementRun(
            session_ids=(session.session_id,),
            repository=repository,
            editable_paths=(Path("src"),),
        )
    )
    attempt = app.improvement.start_attempt(
        run.run_id,
        ImprovementProposerPolicy(
            model="experiment-model",
            reasoning_effort=ReasoningEffort.MAX,
        ),
    )
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def fake_codex(command, **kwargs):
        calls.append((tuple(command), kwargs))
        candidate_path = Path(kwargs["cwd"]) / "src" / "app.py"
        candidate_path.write_text("VALUE = 2\n", encoding="utf-8")
        output = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": json.dumps(
                        proposal(Path("model-claimed.py")).model_dump(mode="json")
                    ),
                },
            }
        ).encode("utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")

    proposer = CodexImprovementProposer(
        process=CodexProcessRunner(
            executable="codex-test",
            run_process=fake_codex,
        )
    )
    result = proposer.propose(run, attempt, ())

    command, kwargs = calls[0]
    assert command[0:4] == ("codex-test", "exec", "--json", "--cd")
    assert "--model" in command
    assert command[command.index("--model") + 1] == "experiment-model"
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    config_values = [
        command[index + 1]
        for index, value in enumerate(command[:-1])
        if value == "--config"
    ]
    assert 'approval_policy="never"' in config_values
    assert 'model_reasoning_effort="max"' in config_values
    assert "sandbox_workspace_write.network_access=false" in config_values
    assert 'web_search="disabled"' in config_values
    assert "mcp_servers={}" in config_values
    assert "--output-schema" in command
    assert kwargs["cwd"] == attempt.worktree
    assert "--add-dir" not in command
    assert "--skip-git-repo-check" not in command
    assert result.changed_paths == (Path("src/app.py"),)
    assert GitRevisionReader().head(attempt.worktree) == base_revision
    assert (repository / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not tuple(repository.glob("*.py"))


def test_codex_proposer_allows_baseline_to_advance_during_call(
    tmp_path: Path,
) -> None:
    repository, base_revision = isolated_git_repository(tmp_path)
    app = create_app(AgentWorkMemoryConfig(state_dir=tmp_path / "state"))
    session = app.sessions.add_manual_note("prepared evidence", title="Codex")
    run = app.improve_harness.prepare(
        PrepareImprovementRun(
            session_ids=(session.session_id,),
            repository=repository,
            editable_paths=(Path("src"),),
        )
    )
    attempt = app.improvement.start_attempt(
        run.run_id,
        ImprovementProposerPolicy(
            model="experiment-model",
            reasoning_effort=ReasoningEffort.MAX,
        ),
    )

    def fake_codex(command, **kwargs):
        candidate_path = Path(kwargs["cwd"]) / "src" / "app.py"
        candidate_path.write_text("VALUE = 2\n", encoding="utf-8")
        baseline_path = repository / "src" / "app.py"
        baseline_path.write_text("VALUE = 99\n", encoding="utf-8")
        run_git(repository, "add", ".")
        run_git(
            repository,
            "-c",
            "user.email=awm-test@example.com",
            "-c",
            "user.name=AWM Test",
            "commit",
            "-m",
            "advance baseline",
        )
        output = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": json.dumps(
                        proposal(Path("model-claimed.py")).model_dump(mode="json")
                    ),
                },
            }
        ).encode("utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")

    proposer = CodexImprovementProposer(
        process=CodexProcessRunner(
            executable="codex-test",
            run_process=fake_codex,
        )
    )
    result = proposer.propose(run, attempt, ())

    assert result.changed_paths == (Path("src/app.py"),)
    assert GitRevisionReader().head(attempt.worktree) == base_revision
    assert (attempt.worktree / "src" / "app.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert (repository / "src" / "app.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 99\n"
    assert GitRevisionReader().head(repository) != base_revision


def test_escaping_observed_change_fails_attempt_without_candidate(
    tmp_path: Path,
) -> None:
    repository, _ = isolated_git_repository(tmp_path)

    def fake_codex(command, **kwargs):
        escaped = Path(kwargs["cwd"]) / "tests" / "escape.py"
        escaped.parent.mkdir()
        escaped.write_text("ESCAPED = True\n", encoding="utf-8")
        output = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": json.dumps(
                        proposal(Path("src/claimed.py")).model_dump(mode="json")
                    ),
                },
            }
        ).encode("utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")

    proposer = CodexImprovementProposer(
        process=CodexProcessRunner(run_process=fake_codex)
    )
    app = create_app(
        AgentWorkMemoryConfig(state_dir=tmp_path / "state"),
        improvement_proposer=proposer,
    )
    session = app.sessions.add_manual_note("prepared evidence", title="Escape")
    run = app.improve_harness.prepare(
        PrepareImprovementRun(
            session_ids=(session.session_id,),
            repository=repository,
            editable_paths=(Path("src"),),
        )
    )

    with pytest.raises(ValueError, match="prepared editable surface"):
        app.improve_harness.propose(ProposeImprovement(run_id=run.run_id))

    attempt = app.improvement.attempts(run.run_id)[0]
    assert attempt.state is ImprovementProposalAttemptState.FAILED
    assert app.improvement.candidates(run.run_id) == ()
    assert app.improvement.get(run.run_id).state is ImprovementRunState.PREPARED
    assert attempt.worktree.is_dir()


def test_codex_failure_is_bounded_and_does_not_retry(tmp_path: Path) -> None:
    calls = 0

    def failed_codex(command, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            command,
            17,
            stdout=b"",
            stderr=(
                b"fatal: https://user:secret@example.test/rejected "
                + b"x" * 10000
            ),
        )

    runner = CodexProcessRunner(
        executable="codex-test",
        run_process=failed_codex,
    )
    with pytest.raises(RuntimeError) as error:
        runner.run(
            "Do not use a real model.",
            cwd=tmp_path,
            policy=ImprovementProposerPolicy(
                model="no-fallback",
                reasoning_effort=ReasoningEffort.XHIGH,
            ),
        )
    assert calls == 1
    assert "secret" not in str(error.value)
    assert "***@" in str(error.value)
    assert len(str(error.value)) < 4200
