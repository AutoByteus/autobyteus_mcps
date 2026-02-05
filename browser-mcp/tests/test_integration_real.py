from __future__ import annotations

import anyio
import logging
import os
from pathlib import Path
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from browser_mcp.server import create_server


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: N802
        return


def _start_http_server(directory: Path) -> tuple[ThreadingHTTPServer, str]:
    handler = partial(QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


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


async def _call_tool(session: ClientSession, name: str, args: dict, timeout: float = 60.0):
    logging.info("Calling tool %s", name)
    with anyio.fail_after(timeout):
        result = await session.call_tool(name, args)
    logging.info("Tool %s completed (error=%s)", name, result.isError)
    return result


def _ensure_chrome_profile_env() -> None:
    if not os.environ.get("CHROME_USER_DATA_DIR"):
        raise RuntimeError("CHROME_USER_DATA_DIR must be set (via .env.test) for integration tests")


def _write_test_page(tmp_path: Path) -> Path:
    html = """
    <html>
      <head><title>Integration Test</title></head>
      <body>
        <h1 id="title">Browser MCP Integration</h1>
        <input id="name" />
        <div id="output"></div>
        <script>
          const input = document.getElementById('name');
          const output = document.getElementById('output');
          input.addEventListener('input', () => {
            output.textContent = input.value;
          });
        </script>
      </body>
    </html>
    """
    page_path = tmp_path / "index.html"
    page_path.write_text(html, encoding="utf-8")
    return page_path


@pytest.mark.anyio
async def test_open_list_close_session_real(tmp_path):
    server = create_server()
    _ensure_chrome_profile_env()

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_browser_session", {})
        assert not opened.isError
        session_id = opened.structuredContent["session_id"]

        listed = await _call_tool(session, "list_browser_sessions", {})
        assert session_id in listed.structuredContent["session_ids"]

        closed = await _call_tool(
            session,
            "close_browser_session",
            {"session_id": session_id, "close_browser": False},
        )
        assert closed.structuredContent["closed"] is True

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_navigate_and_read_local_page(tmp_path):
    server = create_server()
    _ensure_chrome_profile_env()
    _write_test_page(tmp_path)
    httpd, base_url = _start_http_server(tmp_path)
    url = f"{base_url}/index.html"

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_browser_session", {})
        session_id = opened.structuredContent["session_id"]

        nav = await _call_tool(session, "navigate_to", {"session_id": session_id, "url": url})
        assert nav.structuredContent["ok"] is True

        result = await _call_tool(
            session,
            "read_webpage",
            {"session_id": session_id, "cleaning_mode": "text"},
        )
        assert "Browser MCP Integration" in result.structuredContent["content"]

        await _call_tool(session, "close_browser_session", {"session_id": session_id, "close_browser": False})

    try:
        await _run_with_session(server, run_client)
    finally:
        httpd.shutdown()


@pytest.mark.anyio
async def test_trigger_web_element_type(tmp_path):
    server = create_server()
    _ensure_chrome_profile_env()
    _write_test_page(tmp_path)
    httpd, base_url = _start_http_server(tmp_path)
    url = f"{base_url}/index.html"

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_browser_session", {})
        session_id = opened.structuredContent["session_id"]

        await _call_tool(session, "navigate_to", {"session_id": session_id, "url": url})

        await _call_tool(
            session,
            "trigger_web_element",
            {
                "session_id": session_id,
                "css_selector": "#name",
                "action": "type",
                "params": {"text": "Hello Browser MCP"},
            },
        )

        result = await _call_tool(
            session,
            "read_webpage",
            {"session_id": session_id, "cleaning_mode": "text"},
        )
        content = result.structuredContent["content"]
        assert "Hello Browser MCP" in content

        await _call_tool(session, "close_browser_session", {"session_id": session_id, "close_browser": False})

    try:
        await _run_with_session(server, run_client)
    finally:
        httpd.shutdown()


@pytest.mark.anyio
async def test_execute_script_real(tmp_path):
    server = create_server()
    _ensure_chrome_profile_env()
    _write_test_page(tmp_path)
    httpd, base_url = _start_http_server(tmp_path)
    url = f"{base_url}/index.html"

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_browser_session", {})
        session_id = opened.structuredContent["session_id"]

        await _call_tool(session, "navigate_to", {"session_id": session_id, "url": url})

        result = await _call_tool(
            session,
            "execute_script",
            {
                "session_id": session_id,
                "script": (
                    "const el = document.getElementById('output');"
                    "el.textContent = 'Executed!';"
                    "return el.textContent;"
                ),
            },
        )
        assert result.structuredContent["result"] == "Executed!"

        await _call_tool(session, "close_browser_session", {"session_id": session_id, "close_browser": False})

    try:
        await _run_with_session(server, run_client)
    finally:
        httpd.shutdown()


@pytest.mark.anyio
async def test_take_webpage_screenshot_real(tmp_path):
    server = create_server()
    _ensure_chrome_profile_env()
    _write_test_page(tmp_path)
    httpd, base_url = _start_http_server(tmp_path)
    url = f"{base_url}/index.html"
    output_path = tmp_path / "shot.png"

    async def run_client(session: ClientSession) -> None:
        result = await _call_tool(
            session,
            "take_webpage_screenshot",
            {"url": url, "file_path": str(output_path)},
            timeout=120.0,
        )
        assert not result.isError
        assert Path(result.structuredContent["file_path"]).is_file()

    try:
        await _run_with_session(server, run_client)
    finally:
        httpd.shutdown()


@pytest.mark.anyio
async def test_read_medium_article_real_browser():
    server = create_server()
    _ensure_chrome_profile_env()
    url = (
        "https://medium.com/reimagining-the-civic-commons/"
        "why-americans-fortify-their-lives-and-the-public-places-that-can-heal-the-divide-36a3e3991752"
    )

    async def run_client(session: ClientSession) -> None:
        result = await _call_tool(
            session,
            "read_webpage",
            {
                "url": url,
                "cleaning_mode": "text",
                "timeout_ms": 120000,
                "wait_until": "networkidle",
            },
            timeout=150.0,
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        content = structured["content"]
        assert isinstance(content, str)
        assert len(content) > 500
        normalized = content.lower()
        assert "why americans fortify their lives" in normalized

    await _run_with_session(server, run_client)
