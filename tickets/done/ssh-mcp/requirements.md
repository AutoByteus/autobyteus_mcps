# Requirements - ssh-mcp

## Status
- Refined

## Goal / Problem Statement
- Provide an MCP server that lets Codex run bounded SSH commands efficiently on remote machines using explicit session lifecycle controls.
- Avoid repeated full reconnect overhead by allowing session reuse across multiple commands.

## Scope Classification
- Classification: Medium
- Rationale:
  - Existing MCP must be redesigned from one-shot exec semantics to explicit session lifecycle semantics.
  - Requires coordinated updates across config, runner, server, tests, and docs.
  - Requires Docker-backed E2E validation for both runner and MCP tool paths.

## In-Scope Use Cases
- UC-001: Validate SSH command availability before runtime use.
- UC-002: Open a reusable SSH session for a target host and receive a short session ID.
- UC-003: Execute multiple remote commands against an existing session ID.
- UC-004: Close a session explicitly and release related resources.
- UC-005: Automatically expire idle sessions to prevent indefinite resource retention.
- UC-006: Validate end-to-end session lifecycle using a Dockerized local SSH daemon.
- UC-007: Execute lifecycle with key-based authentication.
- UC-008: Execute lifecycle with username/password authentication (non-interactive).

## Acceptance Criteria
- AC-001: MCP exposes `ssh_health_check` tool returning structured status.
- AC-002: MCP exposes `ssh_open_session` tool returning a session identifier and target metadata.
- AC-003: MCP exposes `ssh_session_exec` tool that executes command against existing session ID.
- AC-004: MCP exposes `ssh_close_session` tool that closes session and returns closure status.
- AC-005: Validation/config failures return structured `error_type: validation` without crashing MCP.
- AC-006: Execution failures/timeouts map to structured `error_type: execution` or `timeout`.
- AC-007: Session idle timeout is configurable and enforced.
- AC-008: Docker-backed E2E test validates real SSH transport for open/exec/close via MCP tools.
- AC-009: `ssh_open_session` accepts omitted `host` when `SSH_MCP_DEFAULT_HOST` is configured.
- AC-010: Session IDs are concise 8-character lowercase hex tokens.
- AC-011: Password auth is supported via environment configuration (no password in tool-call payload).
- AC-012: Docker E2E includes both key-based and password-based lifecycle flows.

## Constraints / Dependencies
- Local runtime dependency: OpenSSH client binary (`ssh`) available on host.
- Python runtime and MCP dependency consistent with existing projects in this repo.
- Non-interactive execution only; no interactive TTY shell session.
- Docker engine availability is required to run E2E verification flow.
- Password auth support in non-interactive mode requires OpenSSH askpass compatibility in runtime environment.

## Assumptions
- Remote hosts are already configured for key-based or non-interactive auth.
- Session lifecycle state is process-local and may be reset when MCP process restarts.

## Open Questions / Risks
- If MCP process restarts, all active session IDs become invalid and must be reopened.
- Session multiplexing requires SSH support for control socket features in deployment environment.
- Docker E2E validates local loopback SSH path, not production network/bastion policy behavior.

## Design-Ready Decisions
- Replace one-shot `ssh_exec` as primary execution path with session lifecycle tools.
- Implement session reuse via OpenSSH control socket (`ControlMaster`/`ControlPath`) per session ID.
- Enforce bounded session lifecycle with configurable idle timeout and explicit close operation.
- Keep host allowlist optional but enforce it when configured through `SSH_MCP_ALLOWED_HOSTS`.
- Allow secure default targeting through `SSH_MCP_DEFAULT_HOST` so tool calls can omit host.
- Use short session IDs for usability while retaining low collision probability for expected session volume.
- Support password auth via environment-driven secret only (`SSH_MCP_PASSWORD` or `SSH_MCP_PASSWORD_FILE`).
