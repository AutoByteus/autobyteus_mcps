from __future__ import annotations

import anyio
from pathlib import Path
import pytest

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

import browser_mcp.server as browser_server
import browser_mcp.sessions as browser_sessions


async def _run_with_session(server, client_callable):
    client_to_server_send, server_read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    server_to_client_send, client_read_stream = anyio.create_memory_object_stream[SessionMessage](0)

    async def server_task():
        await server._mcp_server.run(  # type: ignore[attr-defined]
            server_read_stream,
            server_to_client_send,
            server._mcp_server.create_initialization_options(),  # type: ignore[attr-defined]
            raise_exceptions=True,
        )

    async with anyio.create_task_group() as tg:
        tg.start_soon(server_task)
        async with ClientSession(client_read_stream, client_to_server_send) as session:
            await session.initialize()
            await client_callable(session)
        await client_to_server_send.aclose()
        await server_to_client_send.aclose()
        tg.cancel_scope.cancel()


class FakeResponse:
    def __init__(self, ok: bool = True, status: int = 200) -> None:
        self.ok = ok
        self.status = status


class FakeLocator:
    def __init__(self) -> None:
        self.actions: list[tuple[str, object | None]] = []

    async def wait_for(self, **_kwargs):
        return None

    async def click(self):
        self.actions.append(("click", None))

    async def type(self, text: str):
        self.actions.append(("type", text))

    async def fill(self, text: str):
        self.actions.append(("fill", text))

    async def select_option(self, value: str):
        self.actions.append(("select", value))

    async def check(self):
        self.actions.append(("check", None))

    async def uncheck(self):
        self.actions.append(("uncheck", None))

    async def hover(self):
        self.actions.append(("hover", None))

    async def dblclick(self):
        self.actions.append(("double_click", None))


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self._content = "<html><body><h1>Test</h1><script>bad()</script></body></html>"
        self.locators: list[FakeLocator] = []
        self.last_script: str | None = None
        self.last_arg: object | None = None

    async def goto(self, url: str, **_kwargs):
        self.url = url
        return FakeResponse()

    async def content(self):
        return self._content

    async def evaluate(self, script: str, arg: object | None = None):
        self.last_script = script
        self.last_arg = arg
        return {"script": script, "arg": arg}

    async def screenshot(self, path: str, **_kwargs):
        Path(path).write_bytes(b"fake")

    def locator(self, _selector: str):
        locator = FakeLocator()
        self.locators.append(locator)
        return locator


class FakeUIIntegrator:
    def __init__(self) -> None:
        self.page = FakePage()

    async def initialize(self):
        return None

    async def start_keep_alive(self):
        return None

    async def close(self, **_kwargs):
        return None


def _create_server_with_fake_ui():
    browser_sessions.create_integrator = lambda: FakeUIIntegrator()
    return browser_server.create_server()


@pytest.mark.anyio
async def test_list_sessions_empty():
    server = _create_server_with_fake_ui()

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("list_browser_sessions", {})
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["session_ids"] == []

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_open_and_close_session():
    server = _create_server_with_fake_ui()

    async def run_client(session: ClientSession) -> None:
        opened = await session.call_tool("open_browser_session", {})
        assert not opened.isError
        session_id = opened.structuredContent["session_id"]

        listed = await session.call_tool("list_browser_sessions", {})
        assert session_id in listed.structuredContent["session_ids"]

        closed = await session.call_tool("close_browser_session", {"session_id": session_id})
        assert closed.structuredContent["closed"] is True

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_read_webpage_ephemeral():
    server = _create_server_with_fake_ui()

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("read_webpage", {"url": "https://example.com", "cleaning_mode": "text"})
        assert not result.isError
        structured = result.structuredContent
        assert structured["url"] == "https://example.com"
        assert "Test" in structured["content"]

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_read_webpage_with_session():
    server = _create_server_with_fake_ui()

    async def run_client(session: ClientSession) -> None:
        opened = await session.call_tool("open_browser_session", {})
        session_id = opened.structuredContent["session_id"]

        nav = await session.call_tool("navigate_to", {"session_id": session_id, "url": "https://example.com"})
        assert nav.structuredContent["ok"] is True

        result = await session.call_tool("read_webpage", {"session_id": session_id, "cleaning_mode": "text"})
        assert not result.isError
        assert result.structuredContent["url"] == "https://example.com"

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_take_screenshot(tmp_path):
    server = _create_server_with_fake_ui()
    output_path = tmp_path / "shot.png"

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "take_webpage_screenshot",
            {"url": "https://example.com", "file_path": str(output_path)},
        )
        assert not result.isError
        assert Path(result.structuredContent["file_path"]).is_file()

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_trigger_web_element_type_requires_text():
    server = _create_server_with_fake_ui()

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "trigger_web_element",
            {"url": "https://example.com", "css_selector": "#name", "action": "type"},
        )
        assert result.isError

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_execute_script_ephemeral():
    server = _create_server_with_fake_ui()

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "execute_script",
            {
                "url": "https://example.com",
                "script": "return 1 + 1;",
                "arg": {"x": 1},
            },
        )
        assert not result.isError
        structured = result.structuredContent
        assert "return 1 + 1;" in structured["result"]["script"]
        assert structured["result"]["arg"] == {"x": 1}

    await _run_with_session(server, run_client)
