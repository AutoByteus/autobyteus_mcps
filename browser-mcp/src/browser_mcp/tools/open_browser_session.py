from mcp.server.fastmcp import FastMCP

from browser_mcp.sessions import SessionManager
from browser_mcp.types import SessionResult


def register(server: FastMCP, session_manager: SessionManager) -> None:
    @server.tool(
        name="open_browser_session",
        title="Open browser session",
        description="Create a persistent browser session for multi-step workflows.",
        structured_output=True,
    )
    async def open_browser_session() -> SessionResult:
        session = await session_manager.create_session()
        return SessionResult(session_id=session.session_id)
