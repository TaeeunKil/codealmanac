from pathlib import Path

from pydantic import field_validator

from agentworkmemory.core import AgentWorkMemoryModel
from agentworkmemory.services.curators.models import ContentAccess, ReasoningEffort
from agentworkmemory.services.improvement.models import (
    EvaluationReport,
    ImprovementCandidate,
    ImprovementIdentifier,
    ImprovementRun,
    normalize_relative_paths,
)


class PrepareImprovementRun(AgentWorkMemoryModel):
    session_ids: tuple[str, ...]
    repository: Path
    content_access: ContentAccess = ContentAccess.METADATA_ONLY
    editable_paths: tuple[Path, ...]

    @field_validator("session_ids")
    @classmethod
    def selected_sessions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        session_ids = tuple(
            dict.fromkeys(item.strip() for item in value if item.strip())
        )
        if not session_ids:
            raise ValueError("improvement preparation needs at least one session id")
        return session_ids

    @field_validator("repository")
    @classmethod
    def absolute_repository(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("improvement repository must be absolute")
        return value

    @field_validator("editable_paths")
    @classmethod
    def selected_editable_paths(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        paths = normalize_relative_paths(value, "editable")
        if not paths:
            raise ValueError("improvement preparation needs editable paths")
        return paths


class ProposeImprovement(AgentWorkMemoryModel):
    run_id: ImprovementIdentifier
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None

    @field_validator("model")
    @classmethod
    def nonblank_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        model = value.strip()
        if not model:
            raise ValueError("improvement proposer model must not be blank")
        return model


class ImprovementCandidateSummary(AgentWorkMemoryModel):
    candidate: ImprovementCandidate
    evaluation: EvaluationReport | None = None


class ImprovementRunDetails(AgentWorkMemoryModel):
    run: ImprovementRun
    candidates: tuple[ImprovementCandidateSummary, ...]
