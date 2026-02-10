# Alexa MCP Server

Python MCP server for controlling Alexa routines and music actions through a bounded local command adapter.

## Tools

- `alexa_run_routine`
  - Runs an allowlisted Alexa routine name.
- `alexa_music_control`
  - Supports bounded `play` / `stop` actions.
- `alexa_health_check`
  - Validates adapter command availability and optional probe command.
- `alexa_get_device_status`
  - Queries playback/queue status for a device.
- `alexa_volume_control`
  - Turns volume up/down by a bounded step.

All tools return structured JSON with:
- `ok`
- `error_type`
- `error_message`
- `stdout` / `stderr`
- `exit_code`
- metadata fields for action context

## Environment Variables

- `ALEXA_COMMAND` (required):
  - Adapter command path or executable name.
- `ALEXA_COMMAND_BASE_ARGS` (optional):
  - Shell-style args string appended to every command.
- `ALEXA_ALLOWED_ROUTINES` (required):
  - Comma-separated routine names.
- `ALEXA_ALLOWED_MUSIC_ACTIONS` (optional, default `play,stop`):
  - Comma-separated allowed actions.
- `ALEXA_DEFAULT_DEVICE` (optional):
  - Default Echo device used when `echo_device` is omitted.
  - Must be a real device name (placeholder values are rejected).
- `ALEXA_TIMEOUT_SECONDS` (optional, default `20`):
  - Positive integer command timeout.
- `ALEXA_EVENT_FLAG` (optional, default `-e`)
- `ALEXA_DEVICE_FLAG` (optional, default `-d`)
- `ALEXA_HEALTH_CHECK_ARGS` (optional):
  - Shell-style args used by `alexa_health_check` probe command.
- `ALEXA_MUSIC_PLAY_ROUTINE` (optional):
  - If set, `play` action runs this routine instead of `textcommand`.
- `ALEXA_MUSIC_STOP_ROUTINE` (optional):
  - If set, `stop` action runs this routine instead of `textcommand`.
- `ALEXA_MAX_QUERY_LENGTH` (optional, default `120`)
- `ALEXA_MCP_NAME` (optional, default `alexa-mcp`)
- `ALEXA_MCP_INSTRUCTIONS` (optional)
- `ALEXA_REMOTE_CONTROL_SCRIPT` (optional):
  - Path to `alexa_remote_control.sh` used by `scripts/alexa_adapter.sh`.
- `ALEXA_REFRESH_TOKEN_FILE` (optional):
  - File path fallback for `REFRESH_TOKEN` when env var is not set.

## Install

```bash
pip install -e .[test]
```

## Run

```bash
python -m alexa_mcp.server
```

## Adapter Bootstrap

This project includes a ready-to-use adapter script:

- `scripts/alexa_adapter.sh`
- `scripts/bootstrap_alexa_adapter.sh`

Bootstrap the underlying `alexa-remote-control` dependency:

```bash
./scripts/bootstrap_alexa_adapter.sh
```

Then set env (recommended: token file fallback):

```bash
export AMAZON='amazon.de'
export ALEXA='alexa.amazon.de'
export ALEXA_REFRESH_TOKEN_FILE='<PATH_TO_AUTOBYTEUS_MCPS>/alexa-mcp/.secrets/refresh_token'
```

Quick local check:

```bash
./scripts/alexa_adapter.sh -e "textcommand:what time is it"
```

## Codex Config (config.toml)

Add this block to `~/.codex/config.toml`.
Replace placeholders with absolute paths and your actual Echo name.

```toml
[mcp_servers.alexa_home]
command = "uv"
args = [
  "--directory",
  "<ABS_PATH_TO_AUTOBYTEUS_MCPS>/alexa-mcp",
  "run",
  "python",
  "-m",
  "alexa_mcp.server",
]

[mcp_servers.alexa_home.env]
ALEXA_COMMAND = "<ABS_PATH_TO_AUTOBYTEUS_MCPS>/alexa-mcp/scripts/alexa_adapter.sh"
ALEXA_COMMAND_BASE_ARGS = ""
ALEXA_REMOTE_CONTROL_SCRIPT = "<ABS_PATH_TO_AUTOBYTEUS_MCPS>/alexa-mcp/scripts/vendor/alexa-remote-control/alexa_remote_control.sh"
ALEXA_REFRESH_TOKEN_FILE = "<ABS_PATH_TO_AUTOBYTEUS_MCPS>/alexa-mcp/.secrets/refresh_token"
AMAZON = "amazon.de"
ALEXA = "alexa.amazon.de"
ALEXA_ALLOWED_ROUTINES = "plug_on,plug_off,play_focus_music,stop_music"
ALEXA_ALLOWED_MUSIC_ACTIONS = "play,stop"
ALEXA_DEFAULT_DEVICE = "<YOUR_ECHO_DEVICE_NAME>"
```

## Tests

```bash
uv run pytest
```
