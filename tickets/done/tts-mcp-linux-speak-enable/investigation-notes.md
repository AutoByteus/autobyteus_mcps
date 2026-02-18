# Investigation Notes

## Ticket

- Name: `tts-mcp-linux-speak-enable`
- Date: 2026-02-18
- Objective: Make `tts-mcp` work on current Ubuntu Linux host and verify `speak` tool end-to-end.

## Sources Consulted

- `tts-mcp/README.md`
- `tts-mcp/src/tts_mcp/platform.py`
- `tts-mcp/src/tts_mcp/runtime_bootstrap.py`
- `tts-mcp/src/tts_mcp/runner.py`
- `tts-mcp/scripts/install_llama_tts_linux.sh`
- `tts-mcp/scripts/install_tts_runtime.sh`
- `tts-mcp/scripts/install_llama_tts_macos.sh`
- `tts-mcp/tests/test_runtime_bootstrap.py`
- `tts-mcp/tests/test_platform.py`
- `tts-mcp/tests/test_runner.py`
- Runtime checks on host:
  - `uname -a`
  - `nvidia-smi -L`
  - `./scripts/install_llama_tts_linux.sh`

## Key Findings

- Host is Linux `x86_64` with NVIDIA GPU detected (`nvidia-smi` works).
- Unit test suite passes locally on Linux (`34 passed, 4 skipped`).
- Real Linux installer currently fails immediately:
  - `./scripts/install_llama_tts_linux.sh`
  - failure: `python: command not found`
- Root cause: installer shell script hardcodes `python` executable instead of resolving `python3` fallback.
- This prevents auto-install bootstrap in `runtime_bootstrap.py` from working on Ubuntu systems that only ship `python3`.

## Constraints

- Need real runtime install and real speech generation verification on this machine.
- Keep `tts-mcp` behavior clean without compatibility shims unrelated to this issue.

## Open Unknowns

- Whether playback binary availability affects success when `play=true`; for validation we used `play=false` for deterministic smoke coverage.

## Implications For Design

- Small-scope change centered on runtime installer command resolution.
- Add focused unit test coverage for installer executable selection to prevent regressions.
- Validate with actual runtime install + real `run_speak()` execution on this Linux machine.

## Validation Results (2026-02-18)

- `uv run python -m pytest`: `39 passed, 4 skipped`.
- `./scripts/install_llama_tts_linux.sh`: succeeded; installed llama.cpp `b8088` and exposed `llama-tts`.
- Real generation check (`run_speak`, Linux llama backend): succeeded with `ok=true` and valid WAV output (`outputs/linux_speak_smoke.wav`).
- Real MCP tool-level check (in-memory client/server, `speak`): succeeded with payload `{'ok': True}` and valid WAV output (`outputs/linux_mcp_tool_smoke.wav`).
- Real MCP default auto-backend check (`create_server()` with env backend `auto`): succeeded with payload `{'ok': True}` and valid WAV output (`outputs/linux_mcp_tool_auto_env.wav`).
