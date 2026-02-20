# Implementation Plan

## Scope Classification
- Classification: Medium
- Reasoning: Redesign from one-shot command API to session lifecycle API with state management and end-to-end validation.
- Workflow Depth: Medium -> proposed design -> call stack -> review gate -> implementation plan -> progress tracking.

## Upstream Artifacts (Required)
- Investigation notes: `tickets/in-progress/ssh-mcp/investigation-notes.md`
- Requirements: `tickets/in-progress/ssh-mcp/requirements.md`
  - Current Status: Refined
- Runtime call stacks: `tickets/in-progress/ssh-mcp/future-state-runtime-call-stack.md`
- Runtime review: `tickets/in-progress/ssh-mcp/future-state-runtime-call-stack-review.md`
- Proposed design: `tickets/in-progress/ssh-mcp/proposed-design.md`

## Plan Maturity
- Current Status: Implemented And Verified
- Notes: Implementation completed against design v5 / call stack v5, including key-auth and password-auth Docker E2E coverage.

## Runtime Call Stack Review Gate Summary
| Round | Review Result | Findings Requiring Write-Back | Write-Back Completed | Round State (`Reset`/`Candidate Go`/`Go Confirmed`) | Clean Streak After Round |
| --- | --- | --- | --- | --- | --- |
| 9 | Pass | No | N/A | Candidate Go | 1 |
| 10 | Pass | No | N/A | Go Confirmed | 2 |

## Go / No-Go Decision
- Decision: Go
- Evidence:
  - Final review round: 10
  - Clean streak at final round: 2
  - Final review gate line: `Implementation can start: Yes`

## Dependency And Sequencing Map
| Order | File/Module | Depends On | Why This Order |
| --- | --- | --- | --- |
| 1 | `ssh-mcp/src/ssh_mcp/config.py` | N/A | Add session settings/validators first |
| 2 | `ssh-mcp/src/ssh_mcp/runner.py` | 1 | Implement lifecycle and session manager |
| 3 | `ssh-mcp/src/ssh_mcp/server.py` | 1,2 | Expose lifecycle tools |
| 4 | `ssh-mcp/tests/test_runner.py` | 2 | Validate lifecycle internals |
| 5 | `ssh-mcp/tests/test_server.py` | 3 | Validate MCP tool delegation |
| 6 | `ssh-mcp/tests/test_e2e_docker.py` | 2,3 | Validate open/exec/close on real SSH transport |
| 7 | `ssh-mcp/README.md`, `ssh-mcp/docs/runtime-flow.md` | 1-6 | Sync docs to final behavior |

## Requirement And Design Traceability
| Requirement | Design Section | Use Case / Call Stack | Planned Task ID(s) | Verification |
| --- | --- | --- | --- | --- |
| R-001 | Error handling + UC-001 | UC-001 | T-012,T-014 | unit + server test |
| R-002 | Lifecycle API + UC-002 | UC-002 | T-013,T-014,T-015 | unit + e2e |
| R-003 | Lifecycle API + UC-003 | UC-003 | T-013,T-014,T-015 | unit + e2e |
| R-004 | Lifecycle API + UC-004 | UC-004 | T-013,T-014,T-015 | unit + e2e |
| R-005 | Idle timeout + UC-005 | UC-005 | T-012,T-013,T-015 | unit tests |
| R-006 | Docker E2E + UC-006 | UC-006 | T-016 | docker e2e |
| R-007 | Password auth env config + UC-008 | UC-008 | T-019,T-020,T-021 | unit + e2e |
| R-008 | Multi-auth E2E + UC-007/UC-008 | UC-007,UC-008 | T-021 | docker e2e |

## Design Delta Traceability
| Change ID (from proposed design doc) | Change Type | Planned Task ID(s) | Includes Remove/Rename Work | Verification |
| --- | --- | --- | --- | --- |
| C-016 | Modify | T-012 | No | `tests/test_config.py` |
| C-017 | Modify | T-013 | Yes (legacy one-shot path replacement) | `tests/test_runner.py` |
| C-018 | Modify | T-014 | Yes (tool surface replacement) | `tests/test_server.py` |
| C-019 | Modify | T-015 | No | `tests/test_runner.py` |
| C-020 | Modify | T-015 | No | `tests/test_server.py` |
| C-021 | Modify | T-016 | No | `tests/test_e2e_docker.py` |
| C-022 | Modify | T-017 | No | doc review |
| C-023 | Modify | T-017 | No | doc review |
| C-024 | Modify | T-018 | No | `tests/test_config.py` |
| C-025 | Modify | T-018 | No | `tests/test_runner.py`, Docker E2E |
| C-026 | Modify | T-018 | No | `tests/test_server.py` |
| C-027 | Modify | T-018 | No | `pytest`, Docker E2E, doc review |
| C-028 | Modify | T-019 | No | `tests/test_config.py` |
| C-029 | Modify | T-020 | No | `tests/test_runner.py`, Docker E2E |
| C-030 | Modify | T-021 | No | `tests/test_e2e_docker.py` |

## Step-By-Step Plan
1. T-012: Extend config with session-related settings and validation helpers.
2. T-013: Implement session manager and lifecycle runner functions (`open`, `session_exec`, `close`).
3. T-014: Replace MCP one-shot tool registration with lifecycle tools.
4. T-015: Rewrite/extend unit and MCP session tests for lifecycle APIs.
5. T-016: Rewrite Docker E2E test for open/exec/close lifecycle through MCP.
6. T-017: Update README/runtime docs for lifecycle model and env vars.
7. T-018: Run verification and sync `implementation-progress.md` + docs log.
8. T-019: Add password secret env/file parsing + validation in config layer.
9. T-020: Add askpass-based non-interactive password auth path in runner.
10. T-021: Extend Docker fixture and E2E tests to validate key-auth + password-auth flows.
11. T-022: Fix command assembly ordering bug for open-session password options.
12. T-023: Extend unit coverage for password resolution and password-mode command/env behavior.
13. T-024: Final verification (`pytest` + Docker E2E) and artifact sync.

## Test Strategy
- Unit tests: `tests/test_config.py`, `tests/test_runner.py`
- MCP integration tests: `tests/test_server.py`
- E2E feasibility: Feasible
- E2E command: `SSH_MCP_RUN_DOCKER_E2E=1 pytest tests/test_e2e_docker.py`
- Residual risk notes: process-local session IDs reset on server restart; production networking constraints remain environment-specific.
