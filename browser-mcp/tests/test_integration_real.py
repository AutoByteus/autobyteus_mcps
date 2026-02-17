from __future__ import annotations

import anyio
import json
import logging
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from browser_mcp.server import create_server

REAL_TEST_URL = "https://example.com"


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


def _is_google_url(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return (
        hostname == "google"
        or hostname.startswith("google.")
        or hostname.endswith(".google")
        or ".google." in hostname
    )


def _is_transient_navigation_error(result) -> bool:
    if not result.isError:
        return False
    parts = [getattr(item, "text", "") for item in (result.content or [])]
    text = " ".join(parts)
    return "Execution context was destroyed" in text or "navigating to" in text


def _ensure_chrome_profile_env() -> None:
    if not os.environ.get("CHROME_USER_DATA_DIR"):
        raise RuntimeError("CHROME_USER_DATA_DIR must be set (via .env.test) for integration tests")

    debug_port = int(os.environ.get("CHROME_REMOTE_DEBUGGING_PORT", "9222"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        debug_open = sock.connect_ex(("127.0.0.1", debug_port)) == 0

    if debug_open:
        return

    if not Path("/usr/bin/google-chrome").exists():
        pytest.skip(
            "Skipping real integration tests: no Chrome debug endpoint on localhost "
            f"port {debug_port} and '/usr/bin/google-chrome' is unavailable."
        )


@pytest.mark.anyio
async def test_open_list_close_tab_real():
    server = create_server()
    _ensure_chrome_profile_env()

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_tab", {"url": REAL_TEST_URL, "wait_until": "domcontentloaded"})
        assert not opened.isError
        tab_id = opened.structuredContent["tab_id"]
        assert "example.com" in opened.structuredContent["url"]

        listed = await _call_tool(session, "list_tabs", {})
        assert tab_id in listed.structuredContent["tab_ids"]

        closed = await _call_tool(session, "close_tab", {"tab_id": tab_id, "close_browser": False})
        assert closed.structuredContent["closed"] is True
        assert closed.structuredContent["tab_id"] == tab_id
        listed_after = await _call_tool(session, "list_tabs", {})
        assert tab_id not in listed_after.structuredContent["tab_ids"]

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_navigate_to_requires_tab_id():
    server = create_server()
    _ensure_chrome_profile_env()

    async def run_client(session: ClientSession) -> None:
        nav = await _call_tool(
            session,
            "navigate_to",
            {"url": REAL_TEST_URL, "wait_until": "domcontentloaded", "timeout_ms": 90000},
        )
        assert nav.isError
        text = " ".join(getattr(item, "text", "") for item in (nav.content or []))
        assert "tab_id" in text

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_navigate_to_real_with_explicit_tab_id():
    server = create_server()
    _ensure_chrome_profile_env()

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_tab", {})
        tab_id = opened.structuredContent["tab_id"]
        nav = await _call_tool(
            session,
            "navigate_to",
            {"tab_id": tab_id, "url": REAL_TEST_URL, "wait_until": "domcontentloaded"},
        )
        assert not nav.isError
        assert nav.structuredContent["tab_id"] == tab_id
        assert nav.structuredContent["ok"] is True

        read = await _call_tool(
            session,
            "read_page",
            {"tab_id": tab_id, "cleaning_mode": "text"},
        )
        assert not read.isError
        assert read.structuredContent["tab_id"] == tab_id
        assert "Example Domain" in read.structuredContent["content"]

        script = await _call_tool(
            session,
            "run_script",
            {
                "tab_id": tab_id,
                "script": (
                    "const firstLink = document.querySelector('a');"
                    "return { title: document.title, href: firstLink ? firstLink.href : null };"
                ),
            },
            timeout=90.0,
        )
        assert not script.isError
        payload = script.structuredContent["result"]
        assert payload["title"] == "Example Domain"
        assert isinstance(payload["href"], str) and "iana.org" in payload["href"]
        assert script.structuredContent["tab_id"] == tab_id

        await _call_tool(session, "close_tab", {"tab_id": tab_id, "close_browser": False})

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_read_page_real_with_explicit_tab_id():
    server = create_server()
    _ensure_chrome_profile_env()

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_tab", {"url": REAL_TEST_URL, "wait_until": "domcontentloaded"})
        tab_id = opened.structuredContent["tab_id"]

        result = await _call_tool(
            session,
            "read_page",
            {"tab_id": tab_id, "cleaning_mode": "text"},
            timeout=90.0,
        )
        assert not result.isError
        content = result.structuredContent["content"]
        assert "Example Domain" in content
        assert result.structuredContent["tab_id"] == tab_id

        await _call_tool(session, "close_tab", {"tab_id": tab_id, "close_browser": False})

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_screenshot_real_with_explicit_tab_id(tmp_path):
    server = create_server()
    _ensure_chrome_profile_env()
    output_path = tmp_path / "shot.png"

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_tab", {"url": REAL_TEST_URL, "wait_until": "domcontentloaded"})
        tab_id = opened.structuredContent["tab_id"]

        result = await _call_tool(
            session,
            "screenshot",
            {
                "tab_id": tab_id,
                "file_path": str(output_path),
            },
            timeout=120.0,
        )
        assert not result.isError
        file_path = Path(result.structuredContent["file_path"])
        assert file_path.is_file()
        assert file_path.stat().st_size > 0
        assert result.structuredContent["tab_id"] == tab_id

        await _call_tool(session, "close_tab", {"tab_id": tab_id, "close_browser": False})

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_dom_snapshot_real_with_explicit_tab_id():
    server = create_server()
    _ensure_chrome_profile_env()

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_tab", {"url": REAL_TEST_URL, "wait_until": "domcontentloaded"})
        tab_id = opened.structuredContent["tab_id"]

        result = await _call_tool(
            session,
            "dom_snapshot",
            {
                "tab_id": tab_id,
                "include_bounding_boxes": True,
                "max_elements": 25,
            },
            timeout=90.0,
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["returned_elements"] >= 1
        assert len(structured["elements"]) >= 1
        first = structured["elements"][0]
        assert isinstance(first["element_id"], str)
        assert isinstance(first["css_selector"], str)
        assert structured["tab_id"] == tab_id

        await _call_tool(session, "close_tab", {"tab_id": tab_id, "close_browser": False})

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_dom_snapshot_and_screenshot_real_with_explicit_tab_id(tmp_path):
    server = create_server()
    _ensure_chrome_profile_env()
    output_path = tmp_path / "active-shot.png"

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_tab", {"url": REAL_TEST_URL, "wait_until": "domcontentloaded"})
        tab_id = opened.structuredContent["tab_id"]

        dom = await _call_tool(
            session,
            "dom_snapshot",
            {
                "tab_id": tab_id,
                "include_bounding_boxes": True,
                "max_elements": 25,
            },
            timeout=90.0,
        )
        assert not dom.isError
        assert dom.structuredContent["tab_id"] == tab_id
        assert dom.structuredContent["returned_elements"] >= 1

        shot = await _call_tool(
            session,
            "screenshot",
            {
                "tab_id": tab_id,
                "file_path": str(output_path),
            },
            timeout=120.0,
        )
        assert not shot.isError
        assert shot.structuredContent["tab_id"] == tab_id
        file_path = Path(shot.structuredContent["file_path"])
        assert file_path.is_file()
        assert file_path.stat().st_size > 0

        await _call_tool(session, "close_tab", {"tab_id": tab_id, "close_browser": False})

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_run_script_real_with_explicit_tab_id():
    server = create_server()
    _ensure_chrome_profile_env()

    async def run_client(session: ClientSession) -> None:
        opened = await _call_tool(session, "open_tab", {"url": REAL_TEST_URL, "wait_until": "domcontentloaded"})
        tab_id = opened.structuredContent["tab_id"]

        result = await _call_tool(
            session,
            "run_script",
            {
                "tab_id": tab_id,
                "script": (
                    "const firstLink = document.querySelector('a');"
                    "return { title: document.title, href: firstLink ? firstLink.href : null };"
                ),
            },
            timeout=90.0,
        )
        assert not result.isError
        payload = result.structuredContent["result"]
        assert payload["title"] == "Example Domain"
        assert isinstance(payload["href"], str) and "iana.org" in payload["href"]
        assert result.structuredContent["tab_id"] == tab_id

        await _call_tool(session, "close_tab", {"tab_id": tab_id, "close_browser": False})

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_google_search_and_click_result_real_with_explicit_tab_id(tmp_path):
    server = create_server()
    _ensure_chrome_profile_env()

    async def run_client(session: ClientSession) -> None:
        search_url = "https://www.google.com/search?q=Elon+Musk&hl=en"
        opened = await _call_tool(
            session,
            "open_tab",
            {"url": search_url, "wait_until": "domcontentloaded"},
            timeout=90.0,
        )
        assert not opened.isError
        tab_id = opened.structuredContent["tab_id"]

        target_href: str | None = None
        for _ in range(3):
            consent_probe = await _call_tool(
                session,
                "run_script",
                {
                    "tab_id": tab_id,
                    "script": """
const resultsCount = document.querySelectorAll("#search a[href]").length;
if (resultsCount > 0) {
  return { resultsCount, consentClicked: false, status: "results-ready", url: window.location.href };
}

const normalize = (s) => String(s || "").trim().toLowerCase();
const labels = [
  "accept all",
  "i agree",
  "agree",
  "consent",
  "accept",
  "alle akzeptieren",
  "tout accepter",
  "aceptar todo",
];

const candidates = Array.from(document.querySelectorAll("button, input[type='submit'], input[type='button']"));
for (const el of candidates) {
  const text = normalize(el.innerText || el.value || el.getAttribute("aria-label"));
  if (!text) continue;
  if (labels.some((label) => text.includes(label))) {
    el.click();
    return { resultsCount: 0, consentClicked: true, status: "clicked-consent", url: window.location.href };
  }
}

return { resultsCount: 0, consentClicked: false, status: "no-results-no-consent", url: window.location.href };
""",
                },
                timeout=60.0,
            )
            assert not consent_probe.isError
            info = consent_probe.structuredContent["result"]
            if isinstance(info, dict) and int(info.get("resultsCount", 0)) > 0:
                break
            await anyio.sleep(1.0)
            reload_search = await _call_tool(
                session,
                "navigate_to",
                {"tab_id": tab_id, "url": search_url, "wait_until": "domcontentloaded"},
                timeout=90.0,
            )
            assert not reload_search.isError

        for _ in range(3):
            find_result = await _call_tool(
                session,
                "run_script",
                {
                    "tab_id": tab_id,
                    "script": """
const isGoogleHost = (host) =>
  host === "google" ||
  host.startsWith("google.") ||
  host.endsWith(".google") ||
  host.includes(".google.");

const normalizeHref = (href) => {
  try {
    const u = new URL(href, window.location.href);
    if (isGoogleHost(u.hostname) && u.pathname === "/url") {
      return u.searchParams.get("q") || u.searchParams.get("url") || u.href;
    }
    return u.href;
  } catch {
    return null;
  }
};

const anchors = Array.from(document.querySelectorAll("#search a[href]"));
for (const a of anchors) {
  const normalizedHref = normalizeHref(a.href);
  if (!normalizedHref) continue;
  try {
    const u = new URL(normalizedHref);
    if (!/^https?:$/.test(u.protocol)) continue;
    if (isGoogleHost(u.hostname)) continue;
    return {
      rawHref: a.href,
      normalizedHref,
      text: (a.innerText || "").trim().slice(0, 140)
    };
  } catch {
    continue;
  }
}
return { rawHref: null, normalizedHref: null, text: null };
""",
                },
                timeout=90.0,
            )
            assert not find_result.isError
            assert find_result.structuredContent["tab_id"] == tab_id
            chosen = find_result.structuredContent["result"]
            if isinstance(chosen, dict):
                maybe_href = chosen.get("normalizedHref")
                if isinstance(maybe_href, str) and maybe_href.startswith(("http://", "https://")):
                    target_href = maybe_href
                    break

            reload_search = await _call_tool(
                session,
                "navigate_to",
                {"tab_id": tab_id, "url": search_url, "wait_until": "domcontentloaded"},
                timeout=90.0,
            )
            assert not reload_search.isError
            await anyio.sleep(0.5)

        if target_href is None:
            failure_shot = tmp_path / "google-search-no-result.png"
            debug_shot = await _call_tool(
                session,
                "screenshot",
                {"tab_id": tab_id, "file_path": str(failure_shot)},
                timeout=120.0,
            )
            assert not debug_shot.isError
            assert Path(debug_shot.structuredContent["file_path"]).is_file()

        assert isinstance(target_href, str) and target_href.startswith(("http://", "https://"))
        assert not _is_google_url(target_href)

        click_result = await _call_tool(
            session,
            "run_script",
            {
                "tab_id": tab_id,
                "script": f"""
const targetHref = {json.dumps(target_href)};
const isGoogleHost = (host) =>
  host === "google" ||
  host.startsWith("google.") ||
  host.endsWith(".google") ||
  host.includes(".google.");
const normalizeHref = (href) => {{
  try {{
    const u = new URL(href, window.location.href);
    if (isGoogleHost(u.hostname) && u.pathname === "/url") {{
      return u.searchParams.get("q") || u.searchParams.get("url") || u.href;
    }}
    return u.href;
  }} catch {{
    return null;
  }}
}};

const anchors = Array.from(document.querySelectorAll("#search a[href]"));
const target = anchors.find((a) => normalizeHref(a.href) === targetHref);
if (target) {{
  target.target = "_self";
  target.rel = "";
  target.click();
  return {{ clicked: true, method: "dom-click", targetHref }};
}}

window.location.href = targetHref;
return {{ clicked: true, method: "location-assign", targetHref }};
""",
            },
            timeout=60.0,
        )
        assert not click_result.isError
        assert click_result.structuredContent["tab_id"] == tab_id
        assert click_result.structuredContent["result"]["clicked"] is True

        destination_url: str | None = None
        for _ in range(30):
            url_check = await _call_tool(
                session,
                "run_script",
                {"tab_id": tab_id, "script": "return window.location.href;"},
                timeout=30.0,
            )
            if _is_transient_navigation_error(url_check):
                await anyio.sleep(0.4)
                continue
            assert not url_check.isError
            assert url_check.structuredContent["tab_id"] == tab_id
            maybe_url = url_check.structuredContent["result"]
            if isinstance(maybe_url, str):
                destination_url = maybe_url
                if maybe_url.startswith(("http://", "https://")) and not _is_google_url(maybe_url):
                    break
            await anyio.sleep(0.4)

        assert isinstance(destination_url, str) and destination_url.startswith(("http://", "https://"))
        assert not _is_google_url(destination_url)

        page = await _call_tool(
            session,
            "read_page",
            {"tab_id": tab_id, "cleaning_mode": "text"},
            timeout=90.0,
        )
        assert not page.isError
        assert page.structuredContent["tab_id"] == tab_id
        content = page.structuredContent["content"]
        assert isinstance(content, str) and len(content.strip()) > 0

        # Some destinations (e.g., compact profile pages) may have very short cleaned text.
        # In that case, verify page state using document title as additional evidence.
        if len(content.strip()) < 20:
            title_check = await _call_tool(
                session,
                "run_script",
                {"tab_id": tab_id, "script": "return document.title;"},
                timeout=30.0,
            )
            assert not title_check.isError
            title = title_check.structuredContent["result"]
            assert isinstance(title, str) and len(title.strip()) > 0

        screenshot_path = tmp_path / "google-elon-result.png"
        shot = await _call_tool(
            session,
            "screenshot",
            {"tab_id": tab_id, "file_path": str(screenshot_path)},
            timeout=120.0,
        )
        assert not shot.isError
        assert shot.structuredContent["tab_id"] == tab_id
        shot_path = Path(shot.structuredContent["file_path"])
        assert shot_path.is_file()
        assert shot_path.stat().st_size > 0

        await _call_tool(session, "close_tab", {"tab_id": tab_id, "close_browser": False})

    await _run_with_session(server, run_client)
