# Implementation Progress

## Kickoff Preconditions Checklist

- Scope classification confirmed (`Small`/`Medium`/`Large`): `Small`
- Investigation notes are current (`tickets/in-progress/tts-mcp-linux-speak-enable/investigation-notes.md`): `Yes`
- Requirements status is `Design-ready` or `Refined`: `Design-ready`
- Runtime review final gate is `Implementation can start: Yes`: `Yes`
- Runtime review reached `Go Confirmed` with two consecutive clean deep-review rounds: `Yes`
- No unresolved blocking findings: `Yes`

## Progress Log

- 2026-02-18: Implementation kickoff baseline created.
- 2026-02-18: Patched Linux installer with `resolve_python_bin` helper and `main` guard.
- 2026-02-18: Added installer regression tests in `tests/test_linux_installer.py`.
- 2026-02-18: Unit suite passed (`39 passed, 4 skipped`).
- 2026-02-18: Real Linux installer execution passed and installed llama.cpp `b8088`.
- 2026-02-18: Real Linux generation passed (`run_speak`, `ok=true`, valid WAV produced).
- 2026-02-18: Real MCP `speak` tool invocation passed (`ok=true`, valid WAV produced).
- 2026-02-18: Real MCP `speak` invocation also passed with default `create_server()` auto-backend flow.
- 2026-02-18: README synced with Linux installer Python requirement note.

## File-Level Progress Table

| Change ID | Change Type | File | Depends On | File Status | Unit Test File | Unit Test Status | Integration Test File | Integration Test Status | E2E Scenario | E2E Status | Last Failure Classification | Last Failure Investigation Required | Cross-Reference Smell | Design Follow-Up | Requirement Follow-Up | Last Verified | Verification Command | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C-001 | Modify | `tts-mcp/scripts/install_llama_tts_linux.sh` | N/A | Completed | `tts-mcp/tests/test_linux_installer.py` | Passed | real Linux installer run | Passed | real MCP speak flow (`play=false`) | Passed | N/A | N/A | None | Not Needed | Not Needed | 2026-02-18 | `bash -n scripts/install_llama_tts_linux.sh && ./scripts/install_llama_tts_linux.sh` | Fixed Python executable resolution and preserved installer behavior. |
| C-002 | Add | `tts-mcp/tests/test_linux_installer.py` | C-001 | Completed | `tts-mcp/tests/test_linux_installer.py` | Passed | N/A | N/A | N/A | N/A | N/A | N/A | None | Not Needed | Not Needed | 2026-02-18 | `uv run python -m pytest` | Added coverage for preferred/fallback/error paths. |
| C-003 | Modify | `tts-mcp/README.md` | C-001 | Completed | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | None | Not Needed | Not Needed | 2026-02-18 | doc review | Added Linux installer note for Python executable requirement and override. |

## Failed Integration/E2E Escalation Log (Mandatory)

- None so far.

## E2E Feasibility Record

- E2E Feasible In Current Environment: `Yes`
- Representative E2E scenario executed:
  - In-memory MCP client/server session invoking `speak` with Linux `llama_cpp` backend and explicit WAV output.
- Supporting evidence:
  - `payload={'ok': True}` and output WAV generated (`outputs/linux_mcp_tool_smoke.wav`, size > 44 bytes).
- Residual risk accepted:
  - Playback device behavior for `play=true` is environment-dependent and not required for this fix.

## Docs Sync Log (Mandatory Post-Implementation)

| Date | Docs Impact (`Updated`/`No impact`) | Files Updated | Rationale | Status |
| --- | --- | --- | --- | --- |
| 2026-02-18 | Updated | `tts-mcp/README.md` | Document Linux installer Python executable requirement and `PYTHON_BIN` override. | Completed |
