# Implementation Progress

## Kickoff Preconditions Checklist

- Scope classification confirmed: `Medium`
- Investigation notes are current: `Yes`
- Requirements status: `Design-ready`
- Runtime review final gate `Implementation can start`: `Yes`
- Runtime review reached `Go Confirmed`: `Yes`
- No unresolved blocking findings: `Yes`

## Progress Log

- 2026-02-18: Implementation kickoff baseline created.
- 2026-02-18: Added `kokoro_onnx` backend and Linux runtime policy config (`TTS_MCP_LINUX_RUNTIME`).
- 2026-02-18: Implemented Linux backend routing updates (`auto` + explicit Kokoro).
- 2026-02-18: Added Kokoro runtime bootstrap/install flow and new installer script.
- 2026-02-18: Implemented Kokoro ONNX generation path in runner and version check support.
- 2026-02-18: Updated server tool backend literal and README docs.
- 2026-02-18: Added/updated tests across config/platform/bootstrap/runner/version_check.
- 2026-02-18: Test suite passed (`47 passed, 4 skipped`).
- 2026-02-18: Real Linux Kokoro smoke checks passed (`run_speak`, MCP tool call, and `play=true`).
- 2026-02-18: `install_tts_runtime.sh` Linux runtime selector verified with `TTS_MCP_LINUX_RUNTIME=kokoro_onnx`.

## File-Level Progress Table

| Change ID | Change Type | File | Depends On | File Status | Unit Test File | Unit Test Status | Integration Test | Integration Status | E2E Scenario | E2E Status | Last Verified | Verification Command | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C-001 | Modify | `tts-mcp/src/tts_mcp/config.py` | N/A | Completed | `tts-mcp/tests/test_config.py` | Passed | N/A | N/A | N/A | N/A | 2026-02-18 | `uv run python -m pytest -q` | Added backend/runtime policy + Kokoro env parsing. |
| C-002 | Modify | `tts-mcp/src/tts_mcp/platform.py` | C-001 | Completed | `tts-mcp/tests/test_platform.py` | Passed | N/A | N/A | N/A | N/A | 2026-02-18 | `uv run python -m pytest -q` | Added Kokoro selection rules for Linux auto/explicit. |
| C-003 | Modify | `tts-mcp/src/tts_mcp/runtime_bootstrap.py` | C-001 | Completed | `tts-mcp/tests/test_runtime_bootstrap.py` | Passed | Linux bootstrap smoke | Passed | N/A | N/A | 2026-02-18 | `PYTHON_BIN=.venv/bin/python ./scripts/install_kokoro_onnx_linux.sh` | Runtime bootstrap now installs Kokoro when selected. |
| C-004 | Modify | `tts-mcp/src/tts_mcp/runner.py` | C-001,C-002,C-003 | Completed | `tts-mcp/tests/test_runner.py` | Passed | Linux Kokoro speak smoke | Passed | MCP speak call | Passed | 2026-02-18 | pytest + smoke scripts | Kokoro generation and Linux playback integrated. |
| C-005 | Modify | `tts-mcp/src/tts_mcp/version_check.py` | C-001 | Completed | `tts-mcp/tests/test_version_check.py` | Passed | N/A | N/A | N/A | N/A | 2026-02-18 | `uv run python -m pytest -q` | Added kokoro-onnx freshness policy checks. |
| C-006 | Add/Modify | `tts-mcp/scripts/install_kokoro_onnx_linux.sh`, `tts-mcp/scripts/install_tts_runtime.sh` | C-001,C-003 | Completed | bootstrap tests + script smoke | Passed | Linux install smoke | Passed | N/A | N/A | 2026-02-18 | script smoke + pytest | Added Linux Kokoro installer and runtime selector. |
| C-007 | Modify | `tts-mcp/README.md` | C-001..C-006 | Completed | N/A | N/A | docs review | Passed | N/A | N/A | 2026-02-18 | manual review | Documented new backend/runtime and env vars. |

## E2E Feasibility Record

- E2E Feasible In Current Environment: `Yes`
- Executed scenario:
  - In-memory MCP session calling `speak` with Linux `auto` backend + `TTS_MCP_LINUX_RUNTIME=kokoro_onnx`.
- Evidence:
  - `payload={'ok': True}` and generated WAV: `outputs/kokoro_mcp_auto_linux.wav`.

## Docs Sync Log

| Date | Docs Impact | Files Updated | Rationale | Status |
| --- | --- | --- | --- | --- |
| 2026-02-18 | Updated | `tts-mcp/README.md` | Added Kokoro backend/runtime policy install and env documentation. | Completed |
