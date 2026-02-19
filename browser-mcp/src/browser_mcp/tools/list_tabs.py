from mcp.server.fastmcp import FastMCP

from browser_mcp.tabs import TabManager
from browser_mcp.types import ListTabsResult


def register(server: FastMCP, tab_manager: TabManager) -> None:
    @server.tool(
        name="list_tabs",
        title="List tabs",
        description="List persistent tab IDs.",
        structured_output=True,
    )
    async def list_tabs() -> ListTabsResult:
        return ListTabsResult(tab_ids=tab_manager.list_tabs())
