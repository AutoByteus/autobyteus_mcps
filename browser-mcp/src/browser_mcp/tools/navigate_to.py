from typing import Literal

from mcp.server.fastmcp import Context, FastMCP

from browser_mcp.sessions import SessionManager, resolve_session
from browser_mcp.types import NavigateResult
from browser_mcp.utils import is_valid_url


def register(server: FastMCP, session_manager: SessionManager) -> None:
    @server.tool(
        name="navigate_to",
        title="Navigate to URL",
        description="Navigate a browser session (or ephemeral session) to a URL.",
        structured_output=True,
    )
    async def navigate_to(
        url: str,
        session_id: str | None = None,
        keep_session: bool = False,
        wait_until: Literal["domcontentloaded", "networkidle", "load"] = "domcontentloaded",
        timeout_ms: int = 60000,
        *,
        context: Context,
    ) -> NavigateResult:
        if not is_valid_url(url):
            raise ValueError(f"Invalid URL format: {url}")

        session, ephemeral, resolved_session_id = await resolve_session(
            session_manager,
            session_id=session_id,
            keep_session=keep_session,
            url=url,
            require_url=True,
        )

        try:
            page = session.integrator.page
            if not page:
                raise RuntimeError("Playwright page not initialized")
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            ok = bool(response and response.ok)
            status = response.status if response else None
            session.last_url = url
            await context.report_progress(1, 1, f"Navigated to {url}")
            return NavigateResult(url=url, ok=ok, status=status, session_id=resolved_session_id)
        finally:
            if ephemeral:
                await session.integrator.close()
