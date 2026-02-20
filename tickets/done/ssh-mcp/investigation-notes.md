# Investigation Notes - ssh-mcp

## Date
- 2026-02-20

## Sources Consulted
- `codex-cli-mcp/src/codex_cli_mcp/server.py`
- `codex-cli-mcp/src/codex_cli_mcp/config.py`
- `codex-cli-mcp/src/codex_cli_mcp/runner.py`
- `codex-cli-mcp/tests/test_server.py`
- `codex-cli-mcp/tests/test_runner.py`
- `alexa-mcp/src/alexa_mcp/config.py`
- `alexa-mcp/src/alexa_mcp/runner.py`
- `alexa-mcp/src/alexa_mcp/server.py`
- `README.md`
- Local Docker toolchain:
  - `docker --version` -> Docker version 29.0.1
  - `docker compose version` -> v2.40.3-desktop.1

## Key Findings
- Existing MCP projects in this repo follow a consistent Python package layout: `src/<pkg>/config.py`, `runner.py`, `server.py`, tests under `tests/`, and `pyproject.toml` scripts.
- Existing MCP tools expose strongly typed structured outputs and normalize validation/config errors into `error_type: validation` rather than raising tool-level failures.
- Existing command-wrapper MCPs (Codex CLI, Alexa adapter) centralize command execution and output truncation in `runner.py`.
- Bounded execution patterns already used in this repo include allowlists, timeout settings, and newline rejection for user-provided command fragments.
- Root README maintains a project table that should include newly added MCP folders.

## Entrypoints and Boundaries
- Entrypoint pattern: `main()` in `server.py` runs `FastMCP` with tool decorators.
- Boundary split pattern:
  - `config.py`: environment parsing + validation.
  - `runner.py`: command construction and subprocess execution.
  - `server.py`: MCP tool API, progress reporting, mapping validation errors.

## Constraints
- New MCP must run from local Codex host and invoke local `ssh` binary to execute commands on remote hosts.
- Tool must be non-interactive and bounded (timeouts, host allowlist support, output truncation).
- Remote execution should not rely on legacy compatibility wrappers; a clean implementation is preferred.

## Open Unknowns
- Whether host allowlisting should be hard-required or optional.
- Whether remote command should support structured env injection.

## Decision and Implications
- Use optional host allowlist (`SSH_MCP_ALLOWED_HOSTS`) with strict host/user/port validation so the server remains usable while still supporting bounded deployments.
- Start with one execution tool (`ssh_exec`) and one probe tool (`ssh_health_check`), aligned with codex-cli-mcp ergonomics.
- Keep remote command input as a single string with newline rejection and optional remote `cwd` prefixing.
- Include unit tests for config/runner and MCP session test for server delegation behavior.

## Re-Investigation (Post-Implementation Feedback)

### Trigger
- 2026-02-20: User requested Docker-based end-to-end validation and confirmed local Docker is available.

### New Findings
- Docker is available locally, so deterministic SSH E2E can be executed without external credentials by launching a disposable local SSH daemon container.
- A containerized OpenSSH daemon with an injected test public key can validate real `ssh` transport and command execution path in `runner.run_exec`.

### Requirement/Design Implications
- Previous assumption "E2E infeasible" is invalid in this environment and must be refined.
- Add Docker E2E test artifacts under `ssh-mcp/tests/e2e/` and an executable pytest E2E case gated by an explicit environment variable.
- Update docs with Docker E2E instructions and runtime verification guidance.

### Residual Risks
- Docker-based E2E validates local loopback SSH path, not remote network policies or cloud-host auth configurations.

## Re-Investigation (Session Lifecycle Redesign)

### Trigger
- 2026-02-20: User requested session-based SSH model (`connect -> multiple commands -> disconnect`) for efficiency and workflow usability.

### New Findings
- OpenSSH control socket multiplexing (`ControlMaster` + `ControlPath`) can provide process-local reusable sessions while keeping command execution non-interactive and bounded.
- Session manager can track session metadata (`session_id`, target, cwd, timestamps) and enforce idle expiry without blocking MCP request/response semantics.
- A pure one-shot `ssh_exec` model is simpler but causes repeated handshakes and does not preserve session continuity expectations.

### Decision and Implications
- Move to explicit session lifecycle tools:
  - `ssh_open_session`
  - `ssh_session_exec`
  - `ssh_close_session`
  - retain `ssh_health_check`.
- Treat old one-shot execution path as replaced (no backward-compat wrappers).
- Add configurable idle timeout and max session bounds to avoid resource leaks.

## Re-Investigation (Usability Refinement)

### Trigger
- 2026-02-20: User requested shorter session IDs and optional host input to favor environment-driven secure defaults.

### Findings
- Most practical usage opens only a few concurrent sessions, so 8-char lowercase hex session IDs are sufficient with collision checks.
- Allowing `ssh_open_session(host?)` with `SSH_MCP_DEFAULT_HOST` reduces prompt burden and keeps sensitive routing details in environment configuration.

### Decisions
- Session IDs changed from UUID format to short 8-char lowercase hex with uniqueness checks.
- Added `SSH_MCP_DEFAULT_HOST`; `ssh_open_session` now accepts omitted host and resolves via environment default.
- Updated docs to emphasize best practice: keys and strict SSH options in `SSH_MCP_BASE_ARGS` or `~/.ssh/config`.

## Re-Investigation (Auth Mode Coverage)

### Trigger
- 2026-02-20: User requested broader common SSH usage coverage, especially key-based and username/password modes with end-to-end tests.

### Findings
- Key-based auth path is already covered in Docker E2E.
- Password-based auth can be supported in non-interactive MCP context via OpenSSH `SSH_ASKPASS` workflow and environment-provided secret.
- For secure operation, password should come from environment (`SSH_MCP_PASSWORD` or `SSH_MCP_PASSWORD_FILE`), not tool-call payload.

### Decisions
- Add password auth support while preserving key-based behavior.
- Add Docker E2E coverage for both:
  - key/agent style
  - password style (non-interactive askpass).
- Keep tool input surface free of sensitive secrets; auth material remains environment/config-driven.
