from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from agentworkmemory.services.sessions.distillation import (
    is_distillation_candidate,
    same_workspace,
)
from agentworkmemory.services.sessions.models import (
    AgentEvent,
    AgentEventKind,
    AgentEventMetadata,
    AgentProvider,
    AgentProviderId,
    AgentSession,
    CollectorCursor,
    SessionState,
)
from agentworkmemory.services.sessions.store import SessionsStore


class SessionsService:
    def __init__(self, store: SessionsStore):
        self.store = store

    def remember_discovered(
        self,
        *,
        provider: AgentProviderId,
        provider_session_id: str,
        cwd: Path | None,
        source_path: Path,
        modified_at: datetime,
        started_at: datetime | None = None,
        title: str | None = None,
        ended_at: datetime | None = None,
        state: SessionState = SessionState.OPEN,
    ) -> AgentSession:
        now = datetime.now(UTC)
        session_id = stable_session_id(provider, provider_session_id, source_path)
        existing = self.store.get_session(session_id)
        if existing is None:
            relocated = tuple(
                candidate
                for candidate in self.store.sessions_for_provider_identity(
                    provider,
                    provider_session_id,
                )
                if candidate.source_path is None
                or candidate.source_path == source_path
                or not candidate.source_path.exists()
            )
            if len(relocated) == 1:
                existing = relocated[0]
                session_id = existing.session_id
        return self.store.remember_session(
            AgentSession(
                session_id=session_id,
                provider=provider,
                provider_session_id=provider_session_id,
                title=(
                    title.strip()
                    if title and title.strip()
                    else (
                        existing.title
                        if existing is not None
                        else f"{provider.title()} session {provider_session_id[:12]}"
                    )
                ),
                cwd=cwd,
                source_path=source_path,
                started_at=started_at,
                ended_at=(
                    ended_at
                    if ended_at is not None
                    else (existing.ended_at if existing is not None else None)
                ),
                modified_at=modified_at,
                state=state,
                content_captured=(
                    existing.content_captured if existing is not None else False
                ),
                distilled_at=(existing.distilled_at if existing is not None else None),
                distill_runtime=(
                    existing.distill_runtime if existing is not None else None
                ),
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            )
        )

    def add_manual_note(
        self,
        text: str,
        *,
        title: str | None = None,
        cwd: Path | None = None,
    ) -> AgentSession:
        content = text.strip()
        if not content:
            raise ValueError("note text must not be empty")
        now = datetime.now(UTC)
        provider_session_id = str(uuid4())
        session_id = stable_session_id(
            AgentProvider.MANUAL,
            provider_session_id,
            Path("manual"),
        )
        self.store.remember_session(
            AgentSession(
                session_id=session_id,
                provider=AgentProvider.MANUAL,
                provider_session_id=provider_session_id,
                title=(
                    title.strip()
                    if title and title.strip()
                    else content.splitlines()[0]
                ),
                cwd=cwd.resolve() if cwd is not None else None,
                modified_at=now,
                content_captured=True,
                created_at=now,
                updated_at=now,
            )
        )
        event = AgentEvent(
            event_id=stable_event_id(
                session_id=session_id,
                source_line=1,
                kind=AgentEventKind.NOTE,
                content=content,
            ),
            session_id=session_id,
            sequence=1,
            kind=AgentEventKind.NOTE,
            role="user",
            label="manual note",
            occurred_at=now,
            content=content,
            source_line=1,
            created_at=now,
        )
        self.store.append_events(
            session_id,
            (event,),
            CollectorCursor(
                source_id=f"manual:{session_id}",
                provider=AgentProvider.MANUAL,
                source_path=Path("manual"),
                last_line=1,
                size_bytes=len(content.encode("utf-8")),
                updated_at=now,
            ),
        )
        remembered = self.get(session_id)
        return remembered

    def append_events(
        self,
        session_id: str,
        events: tuple[AgentEvent, ...],
        cursor: CollectorCursor,
    ) -> int:
        return self.store.append_events(session_id, events, cursor)

    def replace_events(
        self,
        session_id: str,
        events: tuple[AgentEvent, ...],
        cursor: CollectorCursor,
    ) -> int:
        self.get(session_id)
        return self.store.replace_events(session_id, events, cursor)

    def get(self, session_id: str) -> AgentSession:
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown work session: {session_id}")
        return session

    def list(self) -> tuple[AgentSession, ...]:
        return self.store.list_sessions()

    def pending_distillation(self, limit: int) -> tuple[AgentSession, ...]:
        if not 1 <= limit <= 20:
            raise ValueError("pending distill limit must be between 1 and 20")
        pending = self.distillation_candidates()
        if not pending:
            return ()
        anchor = pending[0]
        return tuple(
            session
            for session in pending
            if same_workspace(anchor, session)
        )[:limit]

    def distillation_candidates(self) -> tuple[AgentSession, ...]:
        state_root = self.store.database_path.parent
        session_ids_with_events = self.store.session_ids_with_events()
        return tuple(
            session
            for session in self.list()
            if (
                session.session_id in session_ids_with_events
                and is_distillation_candidate(session, state_root)
            )
        )

    def events(self, session_id: str) -> tuple[AgentEvent, ...]:
        return self.store.events_for(session_id)

    def event_metadata(self, session_id: str) -> tuple[AgentEventMetadata, ...]:
        self.get(session_id)
        return self.store.event_metadata_for(session_id)

    def cursor_for(self, source_id: str) -> CollectorCursor | None:
        return self.store.cursor_for(source_id)

    def mark_distilled(
        self,
        session_ids: tuple[str, ...],
        *,
        runtime: str,
        distilled_at: datetime,
    ) -> None:
        for session_id in session_ids:
            self.get(session_id)
        self.store.mark_distilled(
            session_ids,
            runtime=runtime,
            distilled_at=distilled_at,
        )

    def requeue_distillation(self, session_ids: tuple[str, ...]) -> None:
        for session_id in session_ids:
            self.get(session_id)
        self.store.requeue_distillation(session_ids)


def stable_session_id(
    provider: AgentProviderId,
    provider_session_id: str,
    source_path: Path,
) -> str:
    identity = f"{provider}\0{provider_session_id}\0{source_path}"
    return f"ses_{sha256(identity.encode()).hexdigest()[:24]}"


def stable_event_id(
    *,
    session_id: str,
    source_line: int,
    kind: AgentEventKind,
    content: str,
) -> str:
    identity = f"{session_id}\0{source_line}\0{kind.value}\0{content}"
    return f"evt_{sha256(identity.encode()).hexdigest()[:24]}"
