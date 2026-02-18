# Implementation Plan

## Scope Classification

- Classification: `Medium`
- Reasoning: cross-cutting backend/runtime policy/install/test/doc updates.

## Upstream Artifacts

- Investigation notes: `tickets/in-progress/tts-mcp-linux-kokoro-cpu-backend/investigation-notes.md`
- Requirements: `tickets/in-progress/tts-mcp-linux-kokoro-cpu-backend/requirements.md` (`Design-ready`)
- Proposed design: `tickets/in-progress/tts-mcp-linux-kokoro-cpu-backend/proposed-design.md` (`v1`)
- Runtime call stack: `tickets/in-progress/tts-mcp-linux-kokoro-cpu-backend/future-state-runtime-call-stack.md` (`v1`)
- Runtime review: `tickets/in-progress/tts-mcp-linux-kokoro-cpu-backend/future-state-runtime-call-stack-review.md` (`Go Confirmed`)

## Plan Maturity

- Current Status: `Ready For Implementation`

## Runtime Call Stack Review Gate Summary

| Round | Review Result | Findings Requiring Write-Back | Write-Back Completed | Round State | Clean Streak |
| --- | --- | --- | --- | --- | --- |
| 1 | Pass | No | N/A | Candidate Go | 1 |
| 2 | Pass | No | N/A | Go Confirmed | 2 |

## Go / No-Go Decision

- Decision: `Go`
- Evidence: review round `2`, clean streak `2`, gate says `Implementation can start: Yes`.

## Dependency And Sequencing Map

| Order | File/Module | Depends On | Why This Order |
| --- | --- | --- | --- |
| 1 | `src/tts_mcp/config.py`, `src/tts_mcp/platform.py` | N/A | Establish backend/runtime policy contract |
| 2 | `src/tts_mcp/runtime_bootstrap.py`, `scripts/install_kokoro_onnx_linux.sh`, `scripts/install_tts_runtime.sh` | 1 | Bootstrap follows policy contract |
| 3 | `src/tts_mcp/version_check.py`, `src/tts_mcp/runner.py`, `src/tts_mcp/server.py` | 1-2 | Add executable backend behavior |
| 4 | `tests/*.py`, `README.md` | 1-3 | Verify and document final behavior |

## Requirement And Design Traceability

| Requirement | Design Section | Use Case | Planned Task IDs | Verification |
| --- | --- | --- | --- | --- |
| R-001 Linux runtime policy routing | Target-State + C-001/C-002 | UC-001 | T-001 | unit tests (`test_config`, `test_platform`) |
| R-002 Kokoro speak path | C-004/C-005/C-006 | UC-002 | T-002 | runner tests + Linux smoke |
| R-003 Auto install Kokoro runtime | C-003/C-007/C-008 | UC-003 | T-003 | bootstrap tests + installer smoke |
| R-004 Preserve llama path | C-002/C-003/C-004 | UC-004 | T-004 | existing tests + regression run |

## Step-By-Step Plan

1. Add config/platform primitives for new backend and Linux runtime policy.
2. Add Linux Kokoro installer + bootstrap routing.
3. Implement Kokoro backend execution and version checks.
4. Update tests.
5. Run full test suite and Linux Kokoro real smoke.
6. Sync README and progress docs.

## Test Strategy

- Unit tests: `uv run python -m pytest`
- Integration tests:
  - Linux installer script smoke (`install_kokoro_onnx_linux.sh`)
  - Linux `run_speak` smoke using `backend=kokoro_onnx`, `play=false`
- E2E feasibility: `Yes` (in-memory MCP session available); run representative tool call if time allows.
