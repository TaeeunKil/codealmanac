import json
import subprocess
from pathlib import Path

import pytest

from agentworkmemory.app import create_app
from agentworkmemory.cli import build_parser, main
from agentworkmemory.integrations.improvement import GitRevisionReader
from agentworkmemory.services.curators.models import ContentAccess
from agentworkmemory.services.improvement import (
    AcceptanceGate,
    CandidateDecision,
    EvaluationCaseResult,
    EvaluationSuite,
    HarnessComponent,
    ImprovementCandidateProposal,
    ImprovementRunState,
)
from agentworkmemory.services.sessions import *  # noqa: F403
from agentworkmemory.services.sessions.models import (
    AgentEventMetadata as SessionEventMetadata,
)
from agentworkmemory.settings import AgentWorkMemoryConfig
from agentworkmemory.workflows.improve_harness import (
    ImproveHarnessWorkflow,
    PrepareImprovementRun,
)


class FakeRevisionReader:
    def __init__(self, revision: str = "a" * 40):
        self.revision = revision
        self.repositories: list[Path] = []

    def head(self, repository: Path) -> str:
        self.repositories.append(repository)
        return self.revision


def isolated_app(tmp_path: Path):
    return create_app(
        AgentWorkMemoryConfig(
            state_dir=tmp_path / "state",
            vault_path=None,
        )
    )


def workflow_for(app, revision: str = "a" * 40) -> ImproveHarnessWorkflow:
    return ImproveHarnessWorkflow(
        app.sessions,
        app.improvement,
        FakeRevisionReader(revision),
    )


def prepare_request(
    session_ids: tuple[str, ...],
    repository: Path,
    *,
    content_access: ContentAccess = ContentAccess.METADATA_ONLY,
    editable_paths: tuple[Path, ...] = (Path("src"),),
) -> PrepareImprovementRun:
    return PrepareImprovementRun(
        session_ids=session_ids,
        repository=repository.resolve(),
        content_access=content_access,
        editable_paths=editable_paths,
    )


def proposal(*changed_paths: Path) -> ImprovementCandidateProposal:
    return ImprovementCandidateProposal(
        component=HarnessComponent.SYSTEM_PROMPT,
        failure_evidence=("held-in verifier failure",),
        root_cause="The harness omitted the required boundary.",
        targeted_fix="State the boundary in the system prompt.",
        predicted_impact="The held-in verifier should pass without changing tools.",
        regression_risks=("Prompt wording could obscure an existing rule.",),
        changed_paths=changed_paths,
    )


def case(
    suite: EvaluationSuite,
    case_id: str,
    baseline_passed: bool,
    candidate_passed: bool,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        suite=suite,
        case_id=case_id,
        baseline_passed=baseline_passed,
        candidate_passed=candidate_passed,
    )


def test_metadata_only_run_persists_event_metadata_without_bodies(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note(
        "PRIVATE EVENT BODY: never copy this in metadata mode",
        title="Metadata selection",
    )
    workflow = workflow_for(app)

    run = workflow.prepare(
        prepare_request((session.session_id,), tmp_path / "repository")
    )

    evidence_path = (
        app.config.state_dir / "improvement" / "runs" / run.run_id / "evidence.json"
    )
    persisted = evidence_path.read_text(encoding="utf-8")
    evidence = json.loads(persisted)
    assert "PRIVATE EVENT BODY" not in persisted
    assert evidence[0]["events"]
    assert all(event.get("content") is None for event in evidence[0]["events"])
    assert run.evidence[0].events[0].content is None


def test_selected_local_run_copies_only_explicit_session_events(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    first = app.sessions.add_manual_note(
        "EXPLICIT LOCAL BODY", title="Selected local session"
    )
    second = app.sessions.add_manual_note(
        "UNSELECTED LOCAL BODY", title="Unselected local session"
    )
    workflow = workflow_for(app)

    run = workflow.prepare(
        prepare_request(
            (first.session_id,),
            tmp_path / "repository",
            content_access=ContentAccess.SELECTED_LOCAL,
        )
    )

    assert [evidence.session_id for evidence in run.evidence] == [first.session_id]
    assert [event.content for event in run.evidence[0].events] == [
        "EXPLICIT LOCAL BODY"
    ]
    evidence_path = (
        app.config.state_dir / "improvement" / "runs" / run.run_id / "evidence.json"
    )
    persisted = evidence_path.read_text(encoding="utf-8")
    assert "EXPLICIT LOCAL BODY" in persisted
    assert "UNSELECTED LOCAL BODY" not in persisted
    assert second.session_id not in persisted


def test_unknown_session_creates_no_partial_run_directory(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    known = app.sessions.add_manual_note("known body", title="Known")
    workflow = workflow_for(app)

    with pytest.raises(KeyError, match="unknown work session"):
        workflow.prepare(
            prepare_request(
                (known.session_id, "ses_unknown"),
                tmp_path / "repository",
            )
        )

    assert not (app.config.state_dir / "improvement" / "runs").exists()


def test_run_and_candidate_files_are_atomic_and_inside_improvement_root(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note("metadata", title="Atomic run")
    workflow = workflow_for(app)
    run = workflow.prepare(
        prepare_request((session.session_id,), tmp_path / "repository")
    )
    candidate = workflow.record_candidate(run.run_id, proposal(Path("src/app.py")))

    improvement_root = app.config.state_dir / "improvement"
    run_root = improvement_root / "runs" / run.run_id
    candidate_root = run_root / "candidates" / candidate.candidate_id
    assert run_root.is_relative_to(improvement_root)
    assert candidate_root.is_relative_to(improvement_root)
    assert (run_root / "manifest.json").is_file()
    assert (run_root / "evidence.json").is_file()
    assert (candidate_root / "manifest.json").is_file()
    assert not tuple(improvement_root.rglob("*.tmp"))
    assert not tuple(improvement_root.rglob(".run-*"))
    assert not tuple(improvement_root.rglob(".candidate-*"))


def test_atomic_publication_discards_failed_run_and_candidate_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agentworkmemory.services.improvement.store as store_module

    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note("metadata", title="Atomic failure")
    workflow = workflow_for(app)

    def fail_atomic_write(*args, **kwargs):
        raise OSError("simulated atomic write failure")

    monkeypatch.setattr(store_module, "atomic_write_text", fail_atomic_write)
    with pytest.raises(OSError, match="simulated atomic write failure"):
        workflow.prepare(
            prepare_request((session.session_id,), tmp_path / "repository")
        )
    runs_root = app.config.state_dir / "improvement" / "runs"
    assert not tuple(runs_root.iterdir())

    monkeypatch.undo()
    run = workflow.prepare(
        prepare_request((session.session_id,), tmp_path / "repository")
    )
    monkeypatch.setattr(store_module, "atomic_write_text", fail_atomic_write)
    with pytest.raises(OSError, match="simulated atomic write failure"):
        workflow.record_candidate(run.run_id, proposal(Path("src/app.py")))
    candidates_root = runs_root / run.run_id / "candidates"
    assert not tuple(candidates_root.iterdir())
    assert workflow.improvement.get(run.run_id).state is ImprovementRunState.PREPARED



def test_candidate_outside_editable_surface_is_rejected_before_persistence(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note("metadata", title="Candidate path")
    workflow = workflow_for(app)
    run = workflow.prepare(
        prepare_request(
            (session.session_id,),
            tmp_path / "repository",
            editable_paths=(Path("src"),),
        )
    )

    with pytest.raises(ValueError, match="inside the prepared editable surface"):
        workflow.record_candidate(run.run_id, proposal(Path("tests/test_app.py")))

    assert workflow.improvement.candidates(run.run_id) == ()
    assert workflow.improvement.get(run.run_id).state is ImprovementRunState.PREPARED


def test_evaluation_revalidates_changed_paths_before_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note("metadata", title="Evaluation paths")
    workflow = workflow_for(app)
    run = workflow.prepare(
        prepare_request((session.session_id,), tmp_path / "repository")
    )
    candidate = workflow.record_candidate(run.run_id, proposal(Path("src/app.py")))
    stored_candidate = app.improvement.store.get_candidate(
        run.run_id,
        candidate.candidate_id,
    )
    assert stored_candidate is not None
    outside = stored_candidate.model_copy(
        update={"changed_paths": (Path("tests"),)}
    )
    monkeypatch.setattr(
        app.improvement.store,
        "get_candidate",
        lambda run_id, candidate_id: outside,
    )

    with pytest.raises(ValueError, match="inside the prepared editable surface"):
        workflow.evaluate(
            run.run_id,
            candidate.candidate_id,
            (
                case(EvaluationSuite.HELD_IN, "target", False, True),
                case(EvaluationSuite.HELD_OUT, "guard", True, True),
            ),
        )

    assert not (
        app.config.state_dir
        / "improvement"
        / "runs"
        / run.run_id
        / "candidates"
        / candidate.candidate_id
        / "evaluation.json"
    ).exists()



def test_acceptance_gate_qualifies_held_in_fix_without_regressions() -> None:
    report = AcceptanceGate().evaluate(
        "cand_qualified",
        (
            case(EvaluationSuite.HELD_IN, "target-failure", False, True),
            case(EvaluationSuite.HELD_IN, "preserved-in", True, True),
            case(EvaluationSuite.HELD_OUT, "preserved-out", True, True),
        ),
    )

    assert report.decision is CandidateDecision.QUALIFIED
    assert report.reasons == ()


def test_service_evaluation_persists_qualified_lifecycle(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note("metadata", title="Evaluate")
    workflow = workflow_for(app)
    run = workflow.prepare(
        prepare_request((session.session_id,), tmp_path / "repository")
    )
    candidate = workflow.record_candidate(run.run_id, proposal(Path("src/app.py")))

    report = workflow.evaluate(
        run.run_id,
        candidate.candidate_id,
        (
            case(EvaluationSuite.HELD_IN, "target", False, True),
            case(EvaluationSuite.HELD_OUT, "guard", True, True),
        ),
    )

    assert report.decision is CandidateDecision.QUALIFIED
    assert workflow.improvement.get(run.run_id).state is ImprovementRunState.QUALIFIED
    assert workflow.improvement.evaluation(run.run_id, candidate.candidate_id) == report


@pytest.mark.parametrize(
    ("cases", "expected_reason"),
    (
        (
            (case(EvaluationSuite.HELD_OUT, "out", True, True),),
            "held-in evaluation suite is required",
        ),
        (
            (case(EvaluationSuite.HELD_IN, "in", False, True),),
            "held-out evaluation suite is required",
        ),
        (
            (
                case(EvaluationSuite.HELD_IN, "in", False, False),
                case(EvaluationSuite.HELD_OUT, "out", True, True),
            ),
            "failing to passing",
        ),
        (
            (
                case(EvaluationSuite.HELD_IN, "fix", False, True),
                case(EvaluationSuite.HELD_IN, "regression", True, False),
                case(EvaluationSuite.HELD_OUT, "out", True, True),
            ),
            "held-in regression",
        ),
        (
            (
                case(EvaluationSuite.HELD_IN, "fix", False, True),
                case(EvaluationSuite.HELD_OUT, "regression", True, False),
            ),
            "held-out regression",
        ),
    ),
)
def test_acceptance_gate_rejects_unsafe_evaluation(
    cases: tuple[EvaluationCaseResult, ...],
    expected_reason: str,
) -> None:
    report = AcceptanceGate().evaluate("cand_rejected", cases)

    assert report.decision is CandidateDecision.REJECTED
    assert any(expected_reason in reason for reason in report.reasons)


def test_sessions_star_export_binds_event_metadata() -> None:
    assert globals()["AgentEventMetadata"] is SessionEventMetadata


def test_update_run_rejects_all_immutable_prepared_fields(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note("metadata", title="Immutable run")
    workflow = workflow_for(app)
    run = workflow.prepare(
        prepare_request((session.session_id,), tmp_path / "repository")
    )
    original = app.improvement.get(run.run_id)
    changed_evidence = original.evidence[0].model_copy(update={"title": "changed"})
    mutations = (
        ("repository", (tmp_path / "other-repository").resolve()),
        ("base_revision", "b" * 40),
        ("content_access", ContentAccess.SELECTED_LOCAL),
        ("editable_paths", (Path("tests"),)),
        ("evidence", (changed_evidence,)),
        ("created_at", original.created_at.replace(year=original.created_at.year - 1)),
    )

    for field_name, value in mutations:
        mutated = original.model_copy(update={field_name: value})
        with pytest.raises(ValueError, match=field_name):
            app.improvement.store.update_run(mutated)
        assert app.improvement.get(run.run_id) == original


def test_record_candidate_allows_only_one_candidate_per_run(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note("metadata", title="One candidate")
    workflow = workflow_for(app)
    run = workflow.prepare(
        prepare_request((session.session_id,), tmp_path / "repository")
    )
    first = workflow.record_candidate(run.run_id, proposal(Path("src/app.py")))

    with pytest.raises(ValueError, match="already has a candidate"):
        workflow.record_candidate(run.run_id, proposal(Path("src/other.py")))

    assert workflow.improvement.candidates(run.run_id) == (first,)
    assert (
        workflow.improvement.get(run.run_id).state
        is ImprovementRunState.CANDIDATE_RECORDED
    )


def test_duplicate_evaluation_identities_cannot_be_qualified(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note("metadata", title="Duplicate cases")
    workflow = workflow_for(app)
    run = workflow.prepare(
        prepare_request((session.session_id,), tmp_path / "repository")
    )
    candidate = workflow.record_candidate(run.run_id, proposal(Path("src/app.py")))

    report = workflow.evaluate(
        run.run_id,
        candidate.candidate_id,
        (
            case(EvaluationSuite.HELD_IN, "target", False, True),
            case(EvaluationSuite.HELD_IN, "target", False, True),
            case(EvaluationSuite.HELD_OUT, "guard", True, True),
        ),
    )

    assert report.decision is CandidateDecision.REJECTED
    assert report.reasons == (
        "duplicate evaluation case identity: held-in:target",
    )
    with pytest.raises(ValueError, match="qualified evaluation report"):
        app.improvement.store.save_evaluation(
            run.run_id,
            candidate.candidate_id,
            report.model_copy(update={"decision": CandidateDecision.QUALIFIED}),
        )
    assert (
        app.improvement.evaluation(run.run_id, candidate.candidate_id) == report
    )
    assert workflow.improvement.get(run.run_id).state is ImprovementRunState.REJECTED


def test_cli_list_and_show_do_not_print_event_bodies(tmp_path: Path, capsys) -> None:
    app = isolated_app(tmp_path)
    session = app.sessions.add_manual_note(
        "CLI PRIVATE EVENT BODY", title="CLI evidence"
    )
    workflow = workflow_for(app)
    run = workflow.prepare(
        prepare_request(
            (session.session_id,),
            tmp_path / "repository",
            content_access=ContentAccess.SELECTED_LOCAL,
        )
    )
    candidate = workflow.record_candidate(run.run_id, proposal(Path("src/app.py")))
    capsys.readouterr()

    assert main(("--state-dir", str(app.config.state_dir), "improve", "list")) == 0
    assert main(
        ("--state-dir", str(app.config.state_dir), "improve", "show", run.run_id)
    ) == 0
    output = capsys.readouterr().out

    assert run.run_id in output
    assert candidate.candidate_id in output
    assert "CLI PRIVATE EVENT BODY" not in output
    assert "event metadata record" in output


def test_improve_prepare_parser_requires_explicit_editable_surface() -> None:
    args = build_parser().parse_args(
        (
            "improve",
            "prepare",
            "ses_one",
            "--repo",
            "repository",
            "--editable",
            "src",
            "tests",
            "--allow-local-content",
        )
    )

    assert args.command == "improve"
    assert args.improve_command == "prepare"
    assert args.session_ids == ["ses_one"]
    assert args.editable == [[Path("src"), Path("tests")]]
    assert args.allow_local_content


def test_git_revision_reader_uses_read_only_head_and_sanitizes_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agentworkmemory.integrations.improvement.git as git_module

    calls: list[tuple[tuple[str, ...], Path]] = []

    def successful_run(arguments, *, cwd, **kwargs):
        calls.append((tuple(arguments), cwd))
        return subprocess.CompletedProcess(arguments, 0, stdout=b"b" * 40, stderr=b"")

    monkeypatch.setattr(git_module.subprocess, "run", successful_run)
    reader = GitRevisionReader(executable="git")
    repository = (tmp_path / "repository").resolve()
    repository.mkdir()

    assert reader.head(repository) == "b" * 40
    assert calls == [(('git', 'rev-parse', 'HEAD'), repository)]

    def failed_run(*arguments, **kwargs):
        raise subprocess.CalledProcessError(
            128,
            "git",
            stderr=b"fatal: https://user:secret@example.test/repo.git was rejected",
        )

    monkeypatch.setattr(git_module.subprocess, "run", failed_run)
    with pytest.raises(RuntimeError) as error:
        reader.head(repository)
    assert "secret" not in str(error.value)
    assert "***@" in str(error.value)
