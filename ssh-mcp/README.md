# ssh-mcp

MCP server that wraps local `ssh` for bounded, non-interactive remote command execution with reusable session lifecycle control.

Detailed runtime notes: `docs/runtime-flow.md`.

## Tools

- `ssh_health_check`: validates SSH command availability and runs a configurable probe (default: `ssh -V`).
- `ssh_open_session`: opens one reusable SSH session and returns `session_id`.
- `ssh_session_exec`: runs one command using an existing `session_id`.
- `ssh_close_session`: closes one `session_id` and releases control socket resources.

## Environment

- `SSH_MCP_COMMAND` (default: `ssh`)
- `SSH_MCP_BASE_ARGS` (default: empty)
- `SSH_MCP_TIMEOUT_SECONDS` (default: `60`)
- `SSH_MCP_ALLOWED_HOSTS` (default: empty, no host allowlist)
- `SSH_MCP_DEFAULT_HOST` (optional)
- `SSH_MCP_DEFAULT_USER` (optional)
- `SSH_MCP_DEFAULT_PORT` (optional)
- `SSH_MCP_MAX_COMMAND_CHARS` (default: `4000`)
- `SSH_MCP_MAX_OUTPUT_CHARS` (default: `20000`)
- `SSH_MCP_HEALTH_CHECK_ARGS` (default: `-V`)
- `SSH_MCP_PASSWORD` (optional; prefer secret manager injection)
- `SSH_MCP_PASSWORD_FILE` (optional; path to password file, mutually exclusive with `SSH_MCP_PASSWORD`)
- `SSH_MCP_SESSION_IDLE_TIMEOUT_SECONDS` (default: `300`)
- `SSH_MCP_MAX_SESSIONS` (default: `32`)
- `SSH_MCP_SESSION_DIR` (optional)
- `SSH_MCP_NAME` (default: `ssh-mcp`)
- `SSH_MCP_INSTRUCTIONS` (optional custom instructions)

### What `DEFAULT_HOST` and `ALLOWED_HOSTS` mean

- `SSH_MCP_DEFAULT_HOST`: host used when tool calls omit `host`.
- `SSH_MCP_ALLOWED_HOSTS`: optional allowlist policy. If set, only listed hosts are allowed.

For a single-server setup, using the same value for both is recommended:

```env
SSH_MCP_DEFAULT_HOST=203.0.113.10
SSH_MCP_ALLOWED_HOSTS=203.0.113.10
```

If you do not want the allowlist policy, leave `SSH_MCP_ALLOWED_HOSTS` empty.

### Why env names start with `SSH_MCP_`

- Namespacing avoids collisions with other tools and generic shell environment variables.
- It keeps MCP-specific behavior explicit (policy/timeouts/session limits are MCP concerns, not OpenSSH concerns).
- It allows multiple MCP servers to coexist with separate config safely.

## Run

```bash
python -m pip install -e .
ssh-mcp-server
```

## Docker E2E Test

This project includes real end-to-end SSH tests that start a disposable Dockerized OpenSSH daemon and validate lifecycle calls (`ssh_open_session` -> `ssh_session_exec` -> `ssh_close_session`) over loopback for both:
- key-based auth
- username/password auth

```bash
python -m pip install -e '.[test]'
pytest
SSH_MCP_RUN_DOCKER_E2E=1 pytest tests/test_e2e_docker.py
```

## Security Best Practice

- Put host/user/key settings in environment or `~/.ssh/config`, not per-call tool input.
- Prefer non-interactive SSH args in `SSH_MCP_BASE_ARGS`, for example:
  - `-i /path/to/private_key -o BatchMode=yes -o IdentitiesOnly=yes`
- For password auth, inject `SSH_MCP_PASSWORD` or `SSH_MCP_PASSWORD_FILE` in MCP env (not tool inputs).
- Use `SSH_MCP_ALLOWED_HOSTS` and `SSH_MCP_DEFAULT_HOST` to reduce accidental target drift.
- Keep host-key verification enabled in production (`StrictHostKeyChecking=yes` with managed `known_hosts`).

## MCP Config Example

```json
{
  "mcpServers": {
    "ssh_remote": {
      "command": "python",
      "args": ["-m", "ssh_mcp.server"],
      "cwd": "/Users/normy/autobyteus_org/autobyteus_mcps/ssh-mcp",
      "env": {
        "SSH_MCP_ALLOWED_HOSTS": "prod-admin-1,prod-admin-2",
        "SSH_MCP_DEFAULT_HOST": "prod-admin-1",
        "SSH_MCP_DEFAULT_USER": "ubuntu",
        "SSH_MCP_TIMEOUT_SECONDS": "30",
        "SSH_MCP_SESSION_IDLE_TIMEOUT_SECONDS": "300",
        "SSH_MCP_MAX_SESSIONS": "16"
      }
    }
  }
}
```

## Single Host Password Example

```json
{
  "mcpServers": {
    "ssh_remote": {
      "command": "uv",
      "args": ["--directory", "/Users/normy/autobyteus_org/autobyteus_mcps/ssh-mcp", "run", "python", "-m", "ssh_mcp.server"],
      "env": {
        "SSH_MCP_DEFAULT_HOST": "203.0.113.10",
        "SSH_MCP_ALLOWED_HOSTS": "203.0.113.10",
        "SSH_MCP_DEFAULT_USER": "ubuntu",
        "SSH_MCP_DEFAULT_PORT": "22",
        "SSH_MCP_PASSWORD_FILE": "/Users/normy/.codex/secrets/ssh_remote_password"
      }
    }
  }
}
```
