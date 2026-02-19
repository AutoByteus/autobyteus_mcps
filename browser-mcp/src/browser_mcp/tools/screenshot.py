from mcp.server.fastmcp import FastMCP

from browser_mcp.tabs import TabManager, get_tab_or_raise
from browser_mcp.types import ScreenshotResult
from browser_mcp.utils import resolve_output_path


def register(server: FastMCP, tab_manager: TabManager) -> None:
    async def _screenshot(
        tab_id: str,
        file_path: str,
        full_page: bool = True,
        image_format: str = "png",
    ) -> ScreenshotResult:
        if image_format not in {"png", "jpeg"}:
            raise ValueError("image_format must be 'png' or 'jpeg'")

        tab = await get_tab_or_raise(tab_manager, tab_id)
        output_path = resolve_output_path(file_path)

        page = tab.integrator.page
        if not page:
            raise RuntimeError("Playwright page not initialized")
        if not tab.last_url:
            raise ValueError("Tab has no previous navigation. Call navigate_to first.")

        await page.screenshot(path=str(output_path), full_page=full_page, type=image_format)
        return ScreenshotResult(url=page.url, file_path=str(output_path), tab_id=tab_id)

    @server.tool(
        name="screenshot",
        title="Screenshot",
        description="Take a screenshot from an existing tab and save it to a file.",
        structured_output=True,
    )
    async def screenshot(
        tab_id: str,
        file_path: str,
        full_page: bool = True,
        image_format: str = "png",
    ) -> ScreenshotResult:
        return await _screenshot(
            tab_id=tab_id,
            file_path=file_path,
            full_page=full_page,
            image_format=image_format,
        )
