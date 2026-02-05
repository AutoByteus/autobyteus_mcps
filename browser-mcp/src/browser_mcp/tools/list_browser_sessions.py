from mcp.server.fastmcp import FastMCP

from browser_mcp.sessions import SessionManager
from browser_mcp.types import ListSessionsResult


def register(server: FastMCP, session_manager: SessionManager) -> None:
    @server.tool(
        name="list_browser_sessions",
        title="List browser sessions",
        description="List active browser session IDs.",
        structured_output=True,
    )
    async def list_browser_sessions() -> ListSessionsResult:
        return ListSessionsResult(session_ids=session_manager.list_sessions())
