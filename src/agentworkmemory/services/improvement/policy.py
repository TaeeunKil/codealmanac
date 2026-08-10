from agentworkmemory.services.curators.models import ContentAccess
from agentworkmemory.services.improvement.models import (
    ImprovementEvidence,
    ImprovementProposerPolicy,
    ImprovementRun,
)


def evidence_has_content(
    evidence: tuple[ImprovementEvidence, ...],
) -> bool:
    return any(
        event.content is not None
        for selection in evidence
        for event in selection.events
    )


def require_codex_content_policy(
    run: ImprovementRun,
    policy: ImprovementProposerPolicy,
) -> None:
    """Require a safe per-attempt content grant for the remote Codex destination."""
    if run.content_access is ContentAccess.SELECTED_LOCAL:
        raise ValueError(
            "Codex proposer rejects selected-local evidence: a local-only grant "
            "cannot be upgraded to the remote Codex destination"
        )
    if evidence_has_content(run.evidence) and not policy.allow_remote_content:
        raise ValueError(
            "Codex proposer requires allow_remote_content=True for body-bearing "
            "evidence"
        )
