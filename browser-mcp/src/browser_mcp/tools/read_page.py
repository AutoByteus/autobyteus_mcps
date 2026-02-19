from mcp.server.fastmcp import FastMCP

from browser_mcp.cleaning import clean_html
from browser_mcp.tabs import TabManager, get_tab_or_raise
from browser_mcp.types import ReadPageResult


def register(server: FastMCP, tab_manager: TabManager) -> None:
    async def _read_page(
        tab_id: str,
        cleaning_mode: str = "thorough",
    ) -> ReadPageResult:
        tab = await get_tab_or_raise(tab_manager, tab_id)
        page = tab.integrator.page
        if not page:
            raise RuntimeError("Playwright page not initialized")
        if not tab.last_url:
            raise ValueError("Tab has no previous navigation. Call navigate_to first.")

        html_content = await page.content()
        cleaned = clean_html(html_content, cleaning_mode)
        current_url = page.url
        return ReadPageResult(url=current_url, content=cleaned, tab_id=tab_id)

    @server.tool(
        name="read_page",
        title="Read page",
        description="Read and optionally clean HTML from an existing tab.",
        structured_output=True,
    )
    async def read_page(
        tab_id: str,
        cleaning_mode: str = "thorough",
    ) -> ReadPageResult:
        return await _read_page(
            tab_id=tab_id,
            cleaning_mode=cleaning_mode,
        )
