from mcp.server.fastmcp import FastMCP

from browser_mcp.tabs import TabManager
from browser_mcp.types import CloseTabResult


def register(server: FastMCP, tab_manager: TabManager) -> None:
    @server.tool(
        name="close_tab",
        title="Close tab",
        description="Close a tab by tab_id.",
        structured_output=True,
    )
    async def close_tab(tab_id: str, close_browser: bool = False) -> CloseTabResult:
        closed_tab_id, closed = await tab_manager.close_tab(tab_id, close_browser=close_browser)
        return CloseTabResult(tab_id=closed_tab_id, closed=closed)
