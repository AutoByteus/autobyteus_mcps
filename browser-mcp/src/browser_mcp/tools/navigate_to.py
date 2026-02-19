from typing import Literal

from mcp.server.fastmcp import Context, FastMCP

from browser_mcp.tabs import TabManager, get_tab_or_raise
from browser_mcp.types import NavigateResult
from browser_mcp.utils import is_valid_url


def register(server: FastMCP, tab_manager: TabManager) -> None:
    @server.tool(
        name="navigate_to",
        title="Navigate to URL",
        description="Navigate an existing tab to a URL.",
        structured_output=True,
    )
    async def navigate_to(
        tab_id: str,
        url: str,
        wait_until: Literal["domcontentloaded", "networkidle", "load"] = "domcontentloaded",
        timeout_ms: int = 60000,
        *,
        context: Context,
    ) -> NavigateResult:
        if not is_valid_url(url):
            raise ValueError(f"Invalid URL format: {url}")

        tab = await get_tab_or_raise(tab_manager, tab_id)
        page = tab.integrator.page
        if not page:
            raise RuntimeError("Playwright page not initialized")
        response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        ok = bool(response and response.ok)
        status = response.status if response else None
        tab.last_url = url
        await context.report_progress(1, 1, f"Navigated to {url}")
        return NavigateResult(url=url, ok=ok, status=status, tab_id=tab_id)
