# Browser MCP Server

A Python MCP server that exposes browser automation tools backed by `brui_core` (Playwright). It supports both ephemeral calls (one-off actions) and stateful sessions for multi-step navigation.

## Features
- `open_browser_session`: create a persistent browser session.
- `close_browser_session`: close a session by ID.
- `list_browser_sessions`: inspect active sessions.
- `navigate_to`: navigate to a URL (session or ephemeral).
- `read_webpage`: read HTML and return cleaned content.
- `take_webpage_screenshot`: capture a screenshot to disk.
- `trigger_web_element`: click/type/select/check/etc. on a CSS selector.
- `execute_script`: run JavaScript in the page and return the result.

## Installation
```bash
pip install browser-mcp-server
```

For local development:
```bash
pip install -e .[test]
```

## Running the server
By default the server runs over stdio.

```bash
python -m browser_mcp.server
```

Environment variables:
- `BROWSER_MCP_NAME`: override server name (default `browser-mcp`).
- `BROWSER_MCP_INSTRUCTIONS`: override instructions string.
- `AUTOBYTEUS_AGENT_WORKSPACE`: if set, server changes CWD to this path.

## Usage examples

Create a session:
```json
{ "tool": "open_browser_session", "input": {} }
```

Navigate with a session:
```json
{ "tool": "navigate_to", "input": { "session_id": "<id>", "url": "https://example.com" } }
```

Read a page (ephemeral):
```json
{ "tool": "read_webpage", "input": { "url": "https://example.com", "cleaning_mode": "thorough" } }
```

Take a screenshot:
```json
{ "tool": "take_webpage_screenshot", "input": { "url": "https://example.com", "file_path": "./shots/example.png" } }
```

Trigger a click:
```json
{ "tool": "trigger_web_element", "input": { "session_id": "<id>", "css_selector": "#submit", "action": "click" } }
```

Execute a script (expression or statements):
```json
{
  "tool": "execute_script",
  "input": { "session_id": "<id>", "script": "return document.title;" }
}
```

## Cursor MCP configuration example
```json
{
  "mcpServers": [
    {
      "name": "browser",
      "command": "uv",
      "args": [
        "--directory",
        "/home/ryan-ai/SSD/autobyteus_org_workspace/autobyteus_mcps/browser-mcp",
        "run",
        "python",
        "-m",
        "browser_mcp.server"
      ]
    }
  ]
}
```

## Notes
- The server relies on `brui_core` and Playwright. Ensure Chrome is available and can be launched in remote debugging mode as required by `brui_core`.
- On Chrome/Chromium 136+ you must set `CHROME_USER_DATA_DIR` to a non-default path for remote debugging to work.

## Running tests
```bash
python -m pytest
```

To run real browser integration tests (requires Chrome + brui_core setup):
```bash
python -m pytest tests/test_integration_real.py
```
