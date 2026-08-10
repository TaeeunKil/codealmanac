from agentworkmemory.services.curators.models import ContentAccess, ReasoningEffort
from agentworkmemory.services.improvement.models import (
    EvaluationCaseResult,
    EvaluationReport,
    ImprovementCandidate,
    ImprovementCandidateProposal,
    ImprovementEvidence,
    ImprovementEvidenceEvent,
    ImprovementProposerPolicy,
    ImprovementRun,
)
from agentworkmemory.services.improvement.ports import (
    ImprovementEvaluator,
    ImprovementProposer,
    RepositoryRevisionReader,
)
from agentworkmemory.services.improvement.service import ImprovementService
from agentworkmemory.services.sessions.models import AgentEventMetadata, AgentSession
from agentworkmemory.services.sessions.service import SessionsService
from agentworkmemory.settings import ImprovementProposerSettings
from agentworkmemory.workflows.improve_harness.models import (
    ImprovementCandidateSummary,
    ImprovementRunDetails,
    PrepareImprovementRun,
    ProposeImprovement,
)


class ImproveHarnessWorkflow:
    """Coordinate explicit session selection with improvement lifecycle services."""

    def __init__(
        self,
        sessions: SessionsService,
        improvement: ImprovementService,
        revision_reader: RepositoryRevisionReader,
        proposer: ImprovementProposer | None = None,
        proposer_settings: ImprovementProposerSettings | None = None,
    ):
        self.sessions = sessions
        self.improvement = improvement
        self.revision_reader = revision_reader
        self.proposer = proposer
        self.proposer_settings = proposer_settings or ImprovementProposerSettings()

    def prepare(self, request: PrepareImprovementRun) -> ImprovementRun:
        selected = tuple(
            self.sessions.get(session_id) for session_id in request.session_ids
        )
        if request.content_access is ContentAccess.SELECTED_REMOTE:
            raise ValueError(
                "improvement preparation supports metadata-only or selected-local "
                "content access"
            )
        evidence = tuple(
            improvement_evidence(session, request.content_access, self.sessions)
            for session in selected
        )
        base_revision = self.revision_reader.head(request.repository)
        return self.improvement.prepare(
            repository=request.repository,
            base_revision=base_revision,
            content_access=request.content_access,
            editable_paths=request.editable_paths,
            evidence=evidence,
        )

    def list(self) -> tuple[ImprovementRun, ...]:
        return self.improvement.list()

    def show(self, run_id: str) -> ImprovementRunDetails:
        run = self.improvement.get(run_id)
        summaries = tuple(
            ImprovementCandidateSummary(
                candidate=candidate,
                evaluation=self.improvement.evaluation(run_id, candidate.candidate_id),
            )
            for candidate in self.improvement.candidates(run_id)
        )
        return ImprovementRunDetails(run=run, candidates=summaries)

    def propose(self, request: ProposeImprovement) -> ImprovementCandidate:
        if self.proposer is None:
            raise RuntimeError("improvement proposer is not configured")
        run = self.improvement.get(request.run_id)
        previous_attempts = self.improvement.attempts(request.run_id)
        policy = resolve_policy(
            self.proposer_settings,
            model=request.model,
            effort=request.reasoning_effort,
        )
        attempt = self.improvement.start_attempt(run.run_id, policy)
        try:
            proposal = self.proposer.propose(run, attempt, previous_attempts)
            candidate = self.improvement.record_candidate(run.run_id, proposal)
        except Exception as error:
            self.improvement.fail_attempt(attempt.attempt_id, str(error))
            raise
        self.improvement.complete_attempt(
            attempt.attempt_id,
            candidate.candidate_id,
        )
        return candidate

    def record_candidate(
        self,
        run_id: str,
        proposal: ImprovementCandidateProposal | ImprovementCandidate,
    ) -> ImprovementCandidate:
        return self.improvement.record_candidate(run_id, proposal)

    def evaluate(
        self,
        run_id: str,
        candidate_id: str,
        cases: tuple[EvaluationCaseResult, ...],
    ) -> EvaluationReport:
        return self.improvement.evaluate(run_id, candidate_id, cases)

    def evaluate_with(
        self,
        run_id: str,
        candidate_id: str,
        evaluator: ImprovementEvaluator,
    ) -> EvaluationReport:
        run = self.improvement.get(run_id)
        candidate = self.improvement.candidate(run_id, candidate_id)
        cases = evaluator.compare(run, candidate)
        return self.improvement.evaluate(run_id, candidate_id, cases)


def improvement_evidence(
    session: AgentSession,
    content_access: ContentAccess,
    sessions: SessionsService,
) -> ImprovementEvidence:
    if content_access is ContentAccess.SELECTED_LOCAL:
        events = tuple(
            ImprovementEvidenceEvent(
                event_id=event.event_id,
                sequence=event.sequence,
                kind=event.kind,
                role=event.role,
                label=event.label,
                occurred_at=event.occurred_at,
                source_line=event.source_line,
                created_at=event.created_at,
                content=event.content,
            )
            for event in sessions.events(session.session_id)
        )
    else:
        events = tuple(
            metadata_event(event)
            for event in sessions.event_metadata(session.session_id)
        )
    return ImprovementEvidence(
        session_id=session.session_id,
        provider=session.provider,
        title=session.title,
        workspace=session.cwd,
        events=events,
    )


def resolve_policy(
    defaults: ImprovementProposerSettings,
    *,
    model: str | None = None,
    effort: ReasoningEffort | None = None,
) -> ImprovementProposerPolicy:
    return ImprovementProposerPolicy(
        model=defaults.model if model is None else model,
        reasoning_effort=(
            defaults.reasoning_effort if effort is None else effort
        ),
    )


def metadata_event(event: AgentEventMetadata) -> ImprovementEvidenceEvent:
    return ImprovementEvidenceEvent(
        event_id=event.event_id,
        sequence=event.sequence,
        kind=event.kind,
        role=event.role,
        label=event.label,
        occurred_at=event.occurred_at,
        source_line=event.source_line,
        created_at=event.created_at,
    )
