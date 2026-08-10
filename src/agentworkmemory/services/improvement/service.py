import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agentworkmemory.services.curators.models import ContentAccess
from agentworkmemory.services.improvement.gate import AcceptanceGate
from agentworkmemory.services.improvement.models import (
    CandidateDecision,
    EvaluationCaseResult,
    EvaluationReport,
    ImprovementCandidate,
    ImprovementCandidateProposal,
    ImprovementEvidence,
    ImprovementProposalAttempt,
    ImprovementProposalAttemptState,
    ImprovementProposerPolicy,
    ImprovementRun,
    ImprovementRunState,
    require_paths_inside_surface,
)
from agentworkmemory.services.improvement.store import ImprovementStore

MAX_ATTEMPT_FAILURE_LENGTH = 4096
URL_CREDENTIALS = re.compile(r"(?i)(https?://)([^/\s@]+)@")


class ImprovementService:
    """Own improvement-run lifecycle and keep the acceptance gate trusted."""

    def __init__(self, store: ImprovementStore, gate: AcceptanceGate | None = None):
        self.store = store
        self.gate = gate or AcceptanceGate()

    def prepare(
        self,
        repository: Path,
        base_revision: str,
        content_access: ContentAccess,
        editable_paths: tuple[Path, ...],
        evidence: tuple[ImprovementEvidence, ...],
    ) -> ImprovementRun:
        if content_access is ContentAccess.SELECTED_REMOTE:
            raise ValueError(
                "improvement preparation does not support remote content access"
            )
        now = datetime.now(UTC)
        run = ImprovementRun(
            run_id=f"imp_{uuid4().hex[:24]}",
            repository=repository,
            base_revision=base_revision,
            content_access=content_access,
            editable_paths=editable_paths,
            evidence=evidence,
            state=ImprovementRunState.PREPARED,
            created_at=now,
            updated_at=now,
        )
        self.store.save_run(run)
        return run

    def get(self, run_id: str) -> ImprovementRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"unknown improvement run: {run_id}")
        return run

    def list(self) -> tuple[ImprovementRun, ...]:
        return self.store.list_runs()

    def start_attempt(
        self,
        run_id: str,
        policy: ImprovementProposerPolicy,
        worktree: Path | None = None,
    ) -> ImprovementProposalAttempt:
        run = self.get(run_id)
        if run.state is not ImprovementRunState.PREPARED:
            raise ValueError(
                f"improvement run {run_id} cannot start an attempt in state "
                f"{run.state.value}"
            )
        attempt_id = f"att_{uuid4().hex[:24]}"
        expected_worktree = self.store.worktree_directory(run_id, attempt_id)
        selected_worktree = expected_worktree if worktree is None else worktree
        attempt = ImprovementProposalAttempt(
            attempt_id=attempt_id,
            run_id=run_id,
            policy=policy,
            base_revision=run.base_revision,
            worktree=selected_worktree,
            state=ImprovementProposalAttemptState.STARTED,
            started_at=datetime.now(UTC),
        )
        self.store.save_attempt(attempt)
        return attempt

    def attempts(self, run_id: str) -> tuple[ImprovementProposalAttempt, ...]:
        self.get(run_id)
        return self.store.list_attempts(run_id)

    def attempt(self, attempt_id: str) -> ImprovementProposalAttempt:
        attempt = self.store.find_attempt(attempt_id)
        if attempt is None:
            raise KeyError(f"unknown improvement attempt: {attempt_id}")
        return attempt

    def complete_attempt(self, attempt_id: str, candidate_id: str) -> None:
        attempt = self.attempt(attempt_id)
        if attempt.state is not ImprovementProposalAttemptState.STARTED:
            raise ValueError(f"improvement attempt {attempt_id} is already terminal")
        self.candidate(attempt.run_id, candidate_id)
        self.store.update_attempt(
            attempt.model_copy(
                update={
                    "state": ImprovementProposalAttemptState.SUCCEEDED,
                    "completed_at": datetime.now(UTC),
                    "candidate_id": candidate_id,
                }
            )
        )

    def fail_attempt(self, attempt_id: str, failure: str) -> None:
        attempt = self.attempt(attempt_id)
        if attempt.state is not ImprovementProposalAttemptState.STARTED:
            raise ValueError(f"improvement attempt {attempt_id} is already terminal")
        self.store.update_attempt(
            attempt.model_copy(
                update={
                    "state": ImprovementProposalAttemptState.FAILED,
                    "completed_at": datetime.now(UTC),
                    "failure": sanitize_attempt_failure(failure),
                }
            )
        )

    def record_candidate(
        self,
        run_id: str,
        proposal: ImprovementCandidateProposal | ImprovementCandidate,
    ) -> ImprovementCandidate:
        run = self.get(run_id)
        if run.state is not ImprovementRunState.PREPARED:
            raise ValueError(
                f"improvement run {run_id} already has a candidate or is terminal: "
                f"{run.state.value}"
            )
        candidate = candidate_for_run(run_id, proposal)
        require_paths_inside_surface(candidate.changed_paths, run.editable_paths)
        self.store.save_candidate(run, candidate)
        updated = run.model_copy(
            update={
                "state": ImprovementRunState.CANDIDATE_RECORDED,
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.update_run(updated)
        return candidate

    def candidate(self, run_id: str, candidate_id: str) -> ImprovementCandidate:
        self.get(run_id)
        candidate = self.store.get_candidate(run_id, candidate_id)
        if candidate is None:
            raise KeyError(f"unknown improvement candidate: {candidate_id}")
        return candidate

    def candidates(self, run_id: str) -> tuple[ImprovementCandidate, ...]:
        self.get(run_id)
        return self.store.list_candidates(run_id)

    def evaluation(
        self,
        run_id: str,
        candidate_id: str,
    ) -> EvaluationReport | None:
        self.get(run_id)
        self.candidate(run_id, candidate_id)
        return self.store.get_evaluation(run_id, candidate_id)

    def evaluate(
        self,
        run_id: str,
        candidate_id: str,
        cases: tuple[EvaluationCaseResult, ...],
    ) -> EvaluationReport:
        run = self.get(run_id)
        candidate = self.candidate(run_id, candidate_id)
        if run.state is not ImprovementRunState.CANDIDATE_RECORDED:
            raise ValueError(
                f"improvement run {run_id} cannot evaluate in state {run.state.value}"
            )
        require_paths_inside_surface(candidate.changed_paths, run.editable_paths)
        report = self.gate.evaluate(candidate_id, tuple(cases))
        self.store.save_evaluation(run_id, candidate_id, report)
        state = (
            ImprovementRunState.QUALIFIED
            if report.decision is CandidateDecision.QUALIFIED
            else ImprovementRunState.REJECTED
        )
        self.store.update_run(
            run.model_copy(
                update={
                    "state": state,
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        return report


def candidate_for_run(
    run_id: str,
    proposal: ImprovementCandidateProposal | ImprovementCandidate,
) -> ImprovementCandidate:
    if isinstance(proposal, ImprovementCandidate):
        if proposal.run_id != run_id:
            raise ValueError("improvement candidate belongs to a different run")
        return proposal
    if not isinstance(proposal, ImprovementCandidateProposal):
        raise TypeError("improvement candidate must use its typed proposal model")
    return ImprovementCandidate(
        candidate_id=f"cand_{uuid4().hex[:24]}",
        run_id=run_id,
        component=proposal.component,
        failure_evidence=proposal.failure_evidence,
        root_cause=proposal.root_cause,
        targeted_fix=proposal.targeted_fix,
        predicted_impact=proposal.predicted_impact,
        regression_risks=proposal.regression_risks,
        changed_paths=proposal.changed_paths,
    )


def sanitize_attempt_failure(error: BaseException | str) -> str:
    text = str(error).strip()
    if not text:
        text = type(error).__name__ if isinstance(error, BaseException) else "unknown"
    sanitized = URL_CREDENTIALS.sub(r"\1***@", text)
    return sanitized[:MAX_ATTEMPT_FAILURE_LENGTH]
