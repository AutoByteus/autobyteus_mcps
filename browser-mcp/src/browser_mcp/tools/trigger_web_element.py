from typing import Literal

from mcp.server.fastmcp import FastMCP

from browser_mcp.sessions import SessionManager, resolve_session
from browser_mcp.types import TriggerElementResult
from browser_mcp.utils import is_valid_url


def register(server: FastMCP, session_manager: SessionManager) -> None:
    @server.tool(
        name="trigger_web_element",
        title="Trigger web element action",
        description="Trigger an action (click/type/select/check/etc.) on an element in the current page.",
        structured_output=True,
    )
    async def trigger_web_element(
        css_selector: str,
        action: Literal[
            "click",
            "type",
            "select",
            "check",
            "uncheck",
            "submit",
            "hover",
            "double_click",
        ],
        params: dict[str, str] | None = None,
        url: str | None = None,
        session_id: str | None = None,
        keep_session: bool = False,
        timeout_ms: int = 10000,
    ) -> TriggerElementResult:
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
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                session.last_url = url
            elif not session.last_url:
                raise ValueError("No URL provided and session has no previous navigation")

            locator = page.locator(css_selector)
            await locator.wait_for(state="visible", timeout=timeout_ms)
            params = params or {}

            if action == "click":
                await locator.click()
            elif action == "type":
                text = params.get("text")
                if text is None:
                    raise ValueError("'text' param is required for 'type' action")
                await locator.fill("")
                await locator.type(text)
            elif action == "select":
                option = params.get("option")
                if option is None:
                    raise ValueError("'option' param is required for 'select' action")
                await locator.select_option(option)
            elif action == "check":
                await locator.check()
            elif action == "uncheck":
                await locator.uncheck()
            elif action == "submit":
                await locator.click()
            elif action == "hover":
                await locator.hover()
            elif action == "double_click":
                await locator.dblclick()
            else:
                raise ValueError(f"Unsupported action: {action}")

            message = f"Action '{action}' executed on selector '{css_selector}'."
            return TriggerElementResult(message=message, session_id=resolved_session_id)
        finally:
            if ephemeral:
                await session.integrator.close()
