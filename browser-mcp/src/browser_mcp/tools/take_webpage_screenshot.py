from typing import Literal

from mcp.server.fastmcp import FastMCP

from browser_mcp.sessions import SessionManager, resolve_session
from browser_mcp.types import ScreenshotResult
from browser_mcp.utils import is_valid_url, resolve_output_path


def register(server: FastMCP, session_manager: SessionManager) -> None:
    @server.tool(
        name="take_webpage_screenshot",
        title="Take webpage screenshot",
        description="Take a screenshot of a webpage and save it to a file.",
        structured_output=True,
    )
    async def take_webpage_screenshot(
        file_path: str,
        url: str | None = None,
        session_id: str | None = None,
        keep_session: bool = False,
        full_page: bool = True,
        image_format: Literal["png", "jpeg"] = "png",
        wait_until: Literal["domcontentloaded", "networkidle", "load"] = "networkidle",
        timeout_ms: int = 60000,
    ) -> ScreenshotResult:
        session, ephemeral, resolved_session_id = await resolve_session(
            session_manager,
            session_id=session_id,
            keep_session=keep_session,
            url=url,
            require_url=not session_id,
        )

        output_path = resolve_output_path(file_path)

        try:
            page = session.integrator.page
            if not page:
                raise RuntimeError("Playwright page not initialized")
            if url:
                if not is_valid_url(url):
                    raise ValueError(f"Invalid URL format: {url}")
                await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                session.last_url = url
            elif not session.last_url:
                raise ValueError("No URL provided and session has no previous navigation")

            await page.screenshot(path=str(output_path), full_page=full_page, type=image_format)
            return ScreenshotResult(url=page.url, file_path=str(output_path), session_id=resolved_session_id)
        finally:
            if ephemeral:
                await session.integrator.close()
