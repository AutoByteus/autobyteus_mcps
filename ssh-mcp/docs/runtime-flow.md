# SSH MCP Runtime Flow

## Tool Surface
- `ssh_health_check`
- `ssh_open_session`
- `ssh_session_exec`
- `ssh_close_session`

## Runtime Layers
1. `ssh_mcp.server`: MCP tool entrypoints and progress reporting.
2. `ssh_mcp.config`: input and environment validation.
3. `ssh_mcp.runner`: session lifecycle management and subprocess execution.

## Session Lifecycle
1. `ssh_open_session` validates target input (uses `SSH_MCP_DEFAULT_HOST` when `host` is omitted) and opens an SSH control master using a control socket.
2. If `SSH_MCP_PASSWORD` or `SSH_MCP_PASSWORD_FILE` is configured, `ssh_open_session` enables non-interactive password auth via `SSH_ASKPASS`.
3. `ssh_session_exec` validates `session_id`, reuses control socket, runs one remote command, and updates last-used timestamp.
4. `ssh_close_session` closes the SSH control master (`-O exit`) and removes local session metadata.
5. Idle sessions are expired automatically based on configured timeout.
6. Session IDs are short 8-character lowercase hex tokens for easier manual use.

## Error Mapping
- Validation failures: `error_type = validation`
- Missing command binary: `error_type = config`
- Timeout: `error_type = timeout`
- Non-zero exit or missing/expired session: `error_type = execution`

## Bounded Controls
- `SSH_MCP_ALLOWED_HOSTS`
- `SSH_MCP_DEFAULT_HOST`
- `SSH_MCP_TIMEOUT_SECONDS`
- `SSH_MCP_MAX_COMMAND_CHARS`
- `SSH_MCP_MAX_OUTPUT_CHARS`
- `SSH_MCP_PASSWORD` / `SSH_MCP_PASSWORD_FILE`
- `SSH_MCP_SESSION_IDLE_TIMEOUT_SECONDS`
- `SSH_MCP_MAX_SESSIONS`

## Verification
- Unit and integration-style MCP tests run with `pytest`.
- Docker-backed E2E lifecycle test runs with:
  - `SSH_MCP_RUN_DOCKER_E2E=1 pytest tests/test_e2e_docker.py`
