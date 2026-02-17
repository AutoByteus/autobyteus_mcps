# Browser MCP Server

A Python MCP server that exposes browser automation tools backed by `brui_core` (Playwright). It uses strict tab-scoped APIs for deterministic multi-step automation.

## Features
- `open_tab`: create a persistent tab (optional initial URL).
- `close_tab`: close a tab by explicit `tab_id`.
- `list_tabs`: inspect persistent tab IDs.
- `navigate_to`: navigate an existing tab to a URL (`tab_id` required).
- `read_page`: read HTML from an existing tab (`tab_id` required).
- `screenshot`: capture a screenshot from an existing tab (`tab_id` required).
- `dom_snapshot`: return structured DOM elements from an existing tab (`tab_id` required).
- `run_script`: run JavaScript in an existing tab and return the result (`tab_id` required).

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

Open a tab:
```json
{ "tool": "open_tab", "input": { "url": "https://example.com" } }
```

Navigate an existing tab:
```json
{ "tool": "navigate_to", "input": { "tab_id": "<TAB_ID>", "url": "https://example.com" } }
```

Read a page:
```json
{ "tool": "read_page", "input": { "tab_id": "<TAB_ID>", "cleaning_mode": "thorough" } }
```

Take a screenshot:
```json
{ "tool": "screenshot", "input": { "tab_id": "<TAB_ID>", "file_path": "./shots/example.png" } }
```

Take a DOM snapshot (elements + selectors):
```json
{
  "tool": "dom_snapshot",
  "input": { "tab_id": "<TAB_ID>", "include_bounding_boxes": true, "max_elements": 200 }
}
```

Execute a script (expression or statements):
```json
{
  "tool": "run_script",
  "input": { "tab_id": "<TAB_ID>", "script": "return document.title;" }
}
```

Close tab:
```json
{ "tool": "close_tab", "input": { "tab_id": "<TAB_ID>" } }
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
- `tab_id` values are numeric strings with a maximum of 6 digits for readability.

## Running tests
```bash
python -m pytest
```

To run real browser integration tests (requires Chrome + brui_core setup):
```bash
python -m pytest tests/test_integration_real.py
```
