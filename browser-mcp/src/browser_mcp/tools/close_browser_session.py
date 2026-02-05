from mcp.server.fastmcp import FastMCP

from browser_mcp.sessions import SessionManager
from browser_mcp.types import CloseSessionResult


def register(server: FastMCP, session_manager: SessionManager) -> None:
    @server.tool(
        name="close_browser_session",
        title="Close browser session",
        description="Close an existing browser session by session_id.",
        structured_output=True,
    )
    async def close_browser_session(session_id: str, close_browser: bool = False) -> CloseSessionResult:
        closed = await session_manager.close_session(session_id, close_browser=close_browser)
        return CloseSessionResult(session_id=session_id, closed=closed)
