from typing import Literal

from mcp.server.fastmcp import FastMCP

from browser_mcp.cleaning import clean_html
from browser_mcp.sessions import SessionManager, resolve_session
from browser_mcp.types import ReadWebpageResult
from browser_mcp.utils import is_valid_url


def register(server: FastMCP, session_manager: SessionManager) -> None:
    @server.tool(
        name="read_webpage",
        title="Read webpage",
        description="Read and optionally clean HTML from a webpage.",
        structured_output=True,
    )
    async def read_webpage(
        url: str | None = None,
        session_id: str | None = None,
        keep_session: bool = False,
        cleaning_mode: str = "thorough",
        wait_until: Literal["domcontentloaded", "networkidle", "load"] = "domcontentloaded",
        timeout_ms: int = 60000,
    ) -> ReadWebpageResult:
        session, ephemeral, resolved_session_id = await resolve_session(
            session_manager,
            session_id=session_id,
            keep_session=keep_session,
            url=url,
            require_url=not session_id,
        )

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

            html_content = await page.content()
            cleaned = clean_html(html_content, cleaning_mode)
            current_url = page.url
            return ReadWebpageResult(url=current_url, content=cleaned, session_id=resolved_session_id)
        finally:
            if ephemeral:
                await session.integrator.close()
