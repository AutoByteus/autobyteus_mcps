from typing import Literal

from mcp.server.fastmcp import FastMCP

from browser_mcp.tabs import TabManager
from browser_mcp.types import OpenTabResult
from browser_mcp.utils import is_valid_url


def register(server: FastMCP, tab_manager: TabManager) -> None:
    @server.tool(
        name="open_tab",
        title="Open tab",
        description="Open a persistent tab.",
        structured_output=True,
    )
    async def open_tab(
        url: str | None = None,
        wait_until: Literal["domcontentloaded", "networkidle", "load"] = "domcontentloaded",
        timeout_ms: int = 60000,
    ) -> OpenTabResult:
        if url and not is_valid_url(url):
            raise ValueError(f"Invalid URL format: {url}")

        tab = await tab_manager.open_tab()
        page = tab.integrator.page
        if not page:
            raise RuntimeError("Playwright page not initialized")

        if url:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            tab.last_url = url

        return OpenTabResult(tab_id=tab.tab_id, url=page.url)
