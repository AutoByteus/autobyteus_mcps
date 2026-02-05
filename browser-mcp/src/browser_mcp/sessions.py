import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from brui_core.ui_integrator import UIIntegrator


def create_integrator() -> UIIntegrator:
    return UIIntegrator()


async def prepare_integrator(keep_alive: bool) -> UIIntegrator:
    integrator = create_integrator()
    await integrator.initialize()
    if keep_alive:
        await integrator.start_keep_alive()
    return integrator


@dataclass(slots=True)
class BrowserSession:
    session_id: str
    integrator: UIIntegrator
    created_at: datetime
    last_url: Optional[str] = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(self) -> BrowserSession:
        integrator = await prepare_integrator(keep_alive=True)
        session_id = str(uuid.uuid4())
        session = BrowserSession(
            session_id=session_id,
            integrator=integrator,
            created_at=datetime.utcnow(),
        )
        async with self._lock:
            self._sessions[session_id] = session
        return session

    async def close_session(self, session_id: str, close_browser: bool = False) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if not session:
            return False
        await session.integrator.close(close_browser=close_browser)
        return True

    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[str]:
        return sorted(self._sessions.keys())


async def get_session_or_raise(session_manager: SessionManager, session_id: str) -> BrowserSession:
    session = session_manager.get_session(session_id)
    if not session:
        raise ValueError(f"Unknown session_id: {session_id}")
    return session


async def create_ephemeral_session() -> BrowserSession:
    integrator = await prepare_integrator(keep_alive=False)
    return BrowserSession(
        session_id="ephemeral",
        integrator=integrator,
        created_at=datetime.utcnow(),
    )


async def resolve_session(
    session_manager: SessionManager,
    session_id: Optional[str],
    keep_session: bool,
    url: Optional[str],
    require_url: bool,
) -> tuple[BrowserSession, bool, Optional[str]]:
    if session_id:
        session = await get_session_or_raise(session_manager, session_id)
        return session, False, session.session_id
    if keep_session:
        session = await session_manager.create_session()
        return session, False, session.session_id
    if require_url and not url:
        raise ValueError("url is required when no session_id is provided")
    session = await create_ephemeral_session()
    return session, True, None
