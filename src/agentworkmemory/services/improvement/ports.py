from pathlib import Path
from typing import Protocol

from agentworkmemory.services.improvement.models import (
    EvaluationCaseResult,
    ImprovementCandidate,
    ImprovementCandidateProposal,
    ImprovementProposalAttempt,
    ImprovementRun,
)


class RepositoryRevisionReader(Protocol):
    def head(self, repository: Path) -> str: ...


class ImprovementProposer(Protocol):
    def propose(
        self,
        run: ImprovementRun,
        attempt: ImprovementProposalAttempt,
        previous_attempts: tuple[ImprovementProposalAttempt, ...],
    ) -> ImprovementCandidateProposal: ...


class ImprovementEvaluator(Protocol):
    def compare(
        self,
        run: ImprovementRun,
        candidate: ImprovementCandidate,
    ) -> tuple[EvaluationCaseResult, ...]: ...
