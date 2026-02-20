# Proposed Design Document

## Design Version
- Current Version: v5

## Revision History
| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | Initial draft | One-shot bounded SSH MCP (`ssh_exec`) | 1 |
| v2 | Requirement refinement | Add Docker E2E verification artifacts | 3 |
| v3 | Session redesign | Replace one-shot exec model with session lifecycle tools | 5 |
| v4 | Usability refinement | Add `SSH_MCP_DEFAULT_HOST` fallback and short session IDs | 7 |
| v5 | Auth coverage refinement | Add environment-driven password auth and multi-auth E2E | 9 |

## Artifact Basis
- Investigation Notes: `tickets/in-progress/ssh-mcp/investigation-notes.md`
- Requirements: `tickets/in-progress/ssh-mcp/requirements.md`
- Requirements Status: Refined

## Summary
Redesign `ssh-mcp` around explicit reusable session lifecycle (`open` -> `exec` -> `close`) backed by OpenSSH control sockets, with bounded timeout/idle expiry and structured MCP outputs.

## Goals
- Reduce repeated SSH handshake overhead for multi-command workflows.
- Keep MCP request/response bounded and non-interactive.
- Provide deterministic lifecycle semantics and cleanup behavior.

## Legacy Removal Policy (Mandatory)
- Policy: No backward compatibility; remove legacy code paths.
- Required action: replace old one-shot `ssh_exec` as primary execution model with session lifecycle tools.

## Requirements And Use Cases
| Requirement | Description | Acceptance Criteria | Use Case IDs |
| --- | --- | --- | --- |
| R-001 | Validate SSH command availability | AC-001 | UC-001 |
| R-002 | Open reusable session | AC-002 | UC-002 |
| R-003 | Execute command via session ID | AC-003, AC-006 | UC-003 |
| R-004 | Close session and cleanup | AC-004 | UC-004 |
| R-005 | Enforce idle timeout cleanup | AC-007 | UC-005 |
| R-006 | Provide Docker E2E lifecycle proof | AC-008 | UC-006 |
| R-007 | Support env-driven password auth | AC-011 | UC-008 |
| R-008 | Validate key + password auth modes in E2E | AC-012 | UC-007, UC-008 |

## Codebase Understanding Snapshot (Pre-Design Mandatory)
| Area | Findings | Evidence (files/functions) | Open Unknowns |
| --- | --- | --- | --- |
| Entrypoints / Boundaries | FastMCP tool decorators with config/runner/server split | `ssh-mcp/src/ssh_mcp/server.py` | None |
| Current Naming Conventions | `ssh_health_check` + one-shot `ssh_exec` surface | `ssh-mcp/src/ssh_mcp/server.py` | Replace naming for lifecycle APIs |
| Impacted Modules / Responsibilities | `config.py`, `runner.py`, `server.py`, tests, docs impacted by redesign | `ssh-mcp/src/ssh_mcp/*`, `ssh-mcp/tests/*` | None |
| Data / Persistence / External IO | subprocess SSH + Docker E2E already in place | `runner.py`, `tests/test_e2e_docker.py` | Session state persistence scope |

## Current State (As-Is)
- One-shot `ssh_exec` command creates a fresh SSH subprocess per call.
- No persistent session ID or lifecycle tracking.

## Target State (To-Be)
- Session lifecycle tools:
  - `ssh_open_session`
  - `ssh_session_exec`
  - `ssh_close_session`
  - `ssh_health_check`
- Process-local session manager stores bounded metadata and control socket path.
- Idle sessions are cleaned up automatically.

## Change Inventory (Delta)
| Change ID | Change Type (`Add`/`Modify`/`Rename/Move`/`Remove`) | Current Path | Target Path | Rationale | Impacted Areas | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| C-016 | Modify | `ssh-mcp/src/ssh_mcp/config.py` | same | Add session lifecycle settings and validation | Runtime config | Idle timeout + session limits |
| C-017 | Modify | `ssh-mcp/src/ssh_mcp/runner.py` | same | Implement session manager + lifecycle operations | Execution engine | Control socket multiplexing |
| C-018 | Modify | `ssh-mcp/src/ssh_mcp/server.py` | same | Replace one-shot tool with lifecycle tools | MCP surface | Open/exec/close APIs |
| C-019 | Modify | `ssh-mcp/tests/test_runner.py` | same | Cover session open/exec/close + expiry | Testing | Unit behavior |
| C-020 | Modify | `ssh-mcp/tests/test_server.py` | same | Cover lifecycle MCP tools | Testing | Session tool delegation |
| C-021 | Modify | `ssh-mcp/tests/test_e2e_docker.py` | same | Validate open/exec/close via MCP tool path | E2E testing | Real SSH lifecycle |
| C-022 | Modify | `ssh-mcp/README.md` | same | Document lifecycle tools and config | Documentation | User guidance |
| C-023 | Modify | `ssh-mcp/docs/runtime-flow.md` | same | Update runtime flow for session model | Documentation | Canonical behavior |
| C-024 | Modify | `ssh-mcp/src/ssh_mcp/config.py` | same | Add `SSH_MCP_DEFAULT_HOST` and optional host resolution in `open_session` | Runtime config | Safer default targeting |
| C-025 | Modify | `ssh-mcp/src/ssh_mcp/runner.py` | same | Short 8-char session id generation and host-optional open path | Execution engine | Better UX with bounded collision risk |
| C-026 | Modify | `ssh-mcp/src/ssh_mcp/server.py` | same | Allow `ssh_open_session(host?)` with default-host fallback | MCP surface | Reduced required input |
| C-027 | Modify | `ssh-mcp/tests/*` + docs | same | Validate new behavior and document best practices | Testing/docs | E2E includes host omission path |
| C-028 | Modify | `ssh-mcp/src/ssh_mcp/config.py` | same | Add password auth env settings and secret resolution | Runtime config | `SSH_MCP_PASSWORD` or `_FILE` |
| C-029 | Modify | `ssh-mcp/src/ssh_mcp/runner.py` | same | Add non-interactive askpass execution path for password auth | Execution engine | Preserves key-based path |
| C-030 | Modify | `ssh-mcp/tests/test_e2e_docker.py` + fixture | same | Add Docker password-auth lifecycle scenario | E2E testing | Validate common auth modes |

## Architecture Overview
`server.py` handles MCP API lifecycle calls and delegates to `runner.py`, where a process-local `SessionManager` tracks control-socket-backed sessions and enforces cleanup.

## File And Module Breakdown
| File/Module | Change Type | Concern / Responsibility | Public APIs | Inputs/Outputs | Dependencies |
| --- | --- | --- | --- | --- | --- |
| `ssh_mcp/config.py` | Modify | Parse env and validate lifecycle tool inputs | `load_settings`, target/command/session validators | env + tool args -> validated settings | stdlib |
| `ssh_mcp/runner.py` | Modify | Manage session state and execute lifecycle actions | `run_health_check`, `run_open_session`, `run_session_exec`, `run_close_session` | validated inputs -> structured results | subprocess, tempfile, shutil |
| `ssh_mcp/server.py` | Modify | MCP tool registration and validation mapping | `create_server`, `main` | MCP args -> structured results | mcp, config, runner |
| `ssh-mcp/tests/*` | Modify | Unit, session integration, Docker E2E | pytest tests | assertions | pytest/anyio/docker |

## Layer-Appropriate Separation Of Concerns Check
- Non-UI scope: lifecycle state lives in runner layer only.
- Integration scope: SSH control socket lifecycle isolated in runner helper methods.

## Naming Decisions (Natural And Implementation-Friendly)
| Item Type (`File`/`Module`/`API`) | Current Name | Proposed Name | Reason | Notes |
| --- | --- | --- | --- | --- |
| API | `ssh_exec` | `ssh_session_exec` | Clarifies session-bound execution | Lifecycle explicit |
| API | N/A | `ssh_open_session` | Explicit start action | Returns session ID |
| API | N/A | `ssh_close_session` | Explicit close action | Deterministic cleanup |

## Naming Drift Check (Mandatory)
| Item | Current Responsibility | Does Name Still Match? (`Yes`/`No`) | Corrective Action (`Rename`/`Split`/`Move`/`N/A`) | Mapped Change ID |
| --- | --- | --- | --- | --- |
| `runner.py` | command execution only | No | Split behavior into lifecycle manager within runner | C-017 |
| `ssh_exec` tool naming | one-shot command | No | Rename/replace with session lifecycle tool names | C-018 |

## Dependency Flow And Cross-Reference Risk
| Module/File | Upstream Dependencies | Downstream Dependents | Cross-Reference Risk | Mitigation / Boundary Strategy |
| --- | --- | --- | --- | --- |
| `config.py` | stdlib | `runner.py`, `server.py` | Low | Keep pure validators |
| `runner.py` | `config.py`, stdlib | `server.py` | Medium | Encapsulate session table with lock + cleanup |
| `server.py` | `config.py`, `runner.py` | MCP clients | Low | No subprocess/state logic in server layer |

## Decommission / Cleanup Plan
| Item To Remove/Rename | Cleanup Actions | Legacy Removal Notes | Verification |
| --- | --- | --- | --- |
| Old one-shot `ssh_exec` path | Replace tool and tests with lifecycle equivalents | No dual tool paths retained | `pytest`, Docker E2E |

## Error Handling And Edge Cases
- Missing command binary -> `error_type: config`
- Invalid target/session/command input -> `error_type: validation`
- Command timeout -> `error_type: timeout`
- Session missing/expired -> `error_type: execution`
- Cleanup failure should still clear local session record with warning output.

## Use-Case Coverage Matrix (Design Gate)
| use_case_id | Requirement | Use Case | Primary Path Covered (`Yes`/`No`) | Fallback Path Covered (`Yes`/`No`/`N/A`) | Error Path Covered (`Yes`/`No`/`N/A`) | Runtime Call Stack Section |
| --- | --- | --- | --- | --- | --- | --- |
| UC-001 | R-001 | Run SSH health check | Yes | N/A | Yes | UC-001 |
| UC-002 | R-002 | Open session and get ID | Yes | N/A | Yes | UC-002 |
| UC-003 | R-003 | Execute command via session | Yes | Yes | Yes | UC-003 |
| UC-004 | R-004 | Close session | Yes | N/A | Yes | UC-004 |
| UC-005 | R-005 | Expire idle sessions | Yes | N/A | Yes | UC-005 |
| UC-006 | R-006 | Docker E2E lifecycle | Yes | N/A | Yes | UC-006 |
| UC-007 | R-008 | Docker E2E lifecycle (key auth) | Yes | N/A | Yes | UC-007 |
| UC-008 | R-007, R-008 | Docker E2E lifecycle (password auth) | Yes | N/A | Yes | UC-008 |

## Performance / Security Considerations
- Performance: reuse SSH control master to reduce repeated handshakes.
- Security: allowlist + bounded output + idle timeout + explicit close.

## Change Traceability To Implementation Plan
| Change ID | Implementation Plan Task(s) | Verification (Unit/Integration/E2E/Manual) | Status |
| --- | --- | --- | --- |
| C-016..C-030 | T-012..T-024 | Unit + MCP session tests + Docker E2E (key + password) | Implemented |
