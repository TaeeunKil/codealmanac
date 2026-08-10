from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import StringConstraints, field_validator

from agentworkmemory.core import AgentWorkMemoryModel

type AgentProviderId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[a-z0-9._-]+$"),
]


class AgentProvider:
    MANUAL = "manual"
    CODEX = "codex"
    CLAUDE = "claude"
    CURSOR = "cursor"


LOCAL_TRANSCRIPT_PROVIDERS = (
    AgentProvider.CODEX,
    AgentProvider.CLAUDE,
    AgentProvider.CURSOR,
)

SSH_REMOTE_TRANSCRIPT_PROVIDERS = (
    AgentProvider.CODEX,
    AgentProvider.CLAUDE,
)


class SessionState(StrEnum):
    OPEN = "open"
    COMPLETE = "complete"
    PAUSED = "paused"
    ABANDONED = "abandoned"


class AgentEventKind(StrEnum):
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    EVENT = "event"
    RAW = "raw"
    NOTE = "note"


class AgentSession(AgentWorkMemoryModel):
    session_id: str
    provider: AgentProviderId
    provider_session_id: str
    title: str
    cwd: Path | None = None
    source_path: Path | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    modified_at: datetime
    state: SessionState = SessionState.OPEN
    content_captured: bool = False
    distilled_at: datetime | None = None
    distill_runtime: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("session_id", "provider_session_id", "title")
    @classmethod
    def required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("session text fields must not be empty")
        return text


class AgentEvent(AgentWorkMemoryModel):
    event_id: str
    session_id: str
    sequence: int
    kind: AgentEventKind
    role: str | None = None
    label: str
    occurred_at: datetime | None = None
    content: str
    source_line: int
    created_at: datetime

    @field_validator("sequence", "source_line")
    @classmethod
    def non_negative_number(cls, value: int) -> int:
        if value < 0:
            raise ValueError("event positions must be non-negative")
        return value


class AgentEventMetadata(AgentWorkMemoryModel):
    event_id: str
    session_id: str
    sequence: int
    kind: AgentEventKind
    role: str | None = None
    label: str
    occurred_at: datetime | None = None
    source_line: int
    created_at: datetime

    @field_validator("event_id", "session_id", "label")
    @classmethod
    def required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("event metadata text fields must not be empty")
        return text

    @field_validator("sequence", "source_line")
    @classmethod
    def non_negative_number(cls, value: int) -> int:
        if value < 0:
            raise ValueError("event positions must be non-negative")
        return value


class CollectorCursor(AgentWorkMemoryModel):
    source_id: str
    provider: AgentProviderId
    source_path: Path
    last_line: int
    size_bytes: int
    updated_at: datetime
    normalizer_version: str = "legacy"


class SearchResult(AgentWorkMemoryModel):
    kind: str
    identity: str
    title: str
    excerpt: str
