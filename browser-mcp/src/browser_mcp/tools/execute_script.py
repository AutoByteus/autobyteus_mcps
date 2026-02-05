from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from browser_mcp.sessions import SessionManager, resolve_session
from browser_mcp.types import ExecuteScriptResult
from browser_mcp.utils import is_valid_url


def _normalize_script(script: str) -> str:
    normalized = script.strip()
    if not normalized:
        raise ValueError("script must not be empty")

    lowered = normalized.lstrip()
    if lowered.startswith(("function", "async function", "()", "(function", "(async", "(()")):
        return normalized

    if any(token in normalized for token in ("return", ";", "\n")):
        return f"(() => {{ {normalized} }})()"

    return f"(() => ({normalized}))()"


def register(server: FastMCP, session_manager: SessionManager) -> None:
    @server.tool(
        name="execute_script",
        title="Execute script",
        description="Execute a JavaScript snippet in the current page context and return the result.",
        structured_output=True,
    )
    async def execute_script(
        script: str,
        arg: Any | None = None,
        url: str | None = None,
        session_id: str | None = None,
        keep_session: bool = False,
        wait_until: Literal["domcontentloaded", "networkidle", "load"] = "domcontentloaded",
        timeout_ms: int = 60000,
    ) -> ExecuteScriptResult:
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

            normalized_script = _normalize_script(script)
            result = await page.evaluate(normalized_script, arg)
            return ExecuteScriptResult(url=page.url, result=result, session_id=resolved_session_id)
        finally:
            if ephemeral:
                await session.integrator.close()
