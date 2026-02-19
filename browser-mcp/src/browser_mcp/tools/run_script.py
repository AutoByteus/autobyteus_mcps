from typing import Any

from mcp.server.fastmcp import FastMCP

from browser_mcp.tabs import TabManager, get_tab_or_raise
from browser_mcp.types import RunScriptResult


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


def register(server: FastMCP, tab_manager: TabManager) -> None:
    @server.tool(
        name="run_script",
        title="Run script",
        description="Run a JavaScript snippet in the current page context and return the result.",
        structured_output=True,
    )
    async def run_script(
        tab_id: str,
        script: str,
        arg: Any | None = None,
    ) -> RunScriptResult:
        tab = await get_tab_or_raise(tab_manager, tab_id)
        page = tab.integrator.page
        if not page:
            raise RuntimeError("Playwright page not initialized")
        if not tab.last_url:
            raise ValueError("Tab has no previous navigation. Call navigate_to first.")

        normalized_script = _normalize_script(script)
        result = await page.evaluate(normalized_script, arg)
        return RunScriptResult(url=page.url, result=result, tab_id=tab_id)
