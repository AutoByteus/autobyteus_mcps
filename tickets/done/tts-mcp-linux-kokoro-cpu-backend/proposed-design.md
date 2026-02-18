# Proposed Design

## Version

- `v1`

## Scope Classification

- `Medium`

## Current-State Summary (As-Is)

- Linux backend path is effectively `llama_cpp` only.
- Auto backend chooses llama only for Linux+NVIDIA; no CPU Linux TTS backend exists.
- Runtime bootstrap on Linux installs only `llama-tts` runtime.
- `run_speak` has branches for `mlx_audio` and `llama_cpp` only.

## Target-State Summary (To-Be)

- Add Linux CPU-capable backend `kokoro_onnx`.
- Add Linux runtime policy env `TTS_MCP_LINUX_RUNTIME` to choose `llama_cpp` or `kokoro_onnx` for `auto` backend and bootstrap.
- Add Kokoro runtime bootstrap installer (`pip install kokoro-onnx` + model assets).
- Extend `run_speak` with Kokoro generation path while preserving existing Linux playback behavior.

## Change Inventory

| Change ID | Type | File | Summary |
| --- | --- | --- | --- |
| C-001 | Modify | `tts-mcp/src/tts_mcp/config.py` | Add backend/runtime policy/env parsing and Kokoro settings |
| C-002 | Modify | `tts-mcp/src/tts_mcp/platform.py` | Add `kokoro_onnx` backend selection rules on Linux |
| C-003 | Modify | `tts-mcp/src/tts_mcp/runtime_bootstrap.py` | Add Linux bootstrap flow for Kokoro runtime/assets |
| C-004 | Modify | `tts-mcp/src/tts_mcp/runner.py` | Add Kokoro generation branch and WAV emission |
| C-005 | Modify | `tts-mcp/src/tts_mcp/version_check.py` | Add runtime freshness checks for `kokoro-onnx` |
| C-006 | Modify | `tts-mcp/src/tts_mcp/server.py` | Update tool backend literal/options text |
| C-007 | Add | `tts-mcp/scripts/install_kokoro_onnx_linux.sh` | Linux Kokoro installer script |
| C-008 | Modify | `tts-mcp/scripts/install_tts_runtime.sh` | Linux runtime selection for manual installer |
| C-009 | Modify | `tts-mcp/README.md` | Document backend/runtime policy and Kokoro env/install |
| C-010 | Modify | `tts-mcp/tests/*.py` | Add/update automated coverage for new backend/policy |

## Module Responsibilities And APIs

| File | Responsibility | Key API/Entry | Inputs/Outputs | Dependencies | Change Type |
| --- | --- | --- | --- | --- | --- |
| `tts-mcp/src/tts_mcp/config.py` | Canonical env parsing and validation | `load_settings()` | env -> `TtsSettings` | stdlib | Modify |
| `tts-mcp/src/tts_mcp/platform.py` | Host/runtime backend selection | `select_backend()` | settings + host -> backend selection | config + host probes | Modify |
| `tts-mcp/src/tts_mcp/runtime_bootstrap.py` | Runtime auto-install orchestration | `bootstrap_runtime()` | settings -> install notes | install scripts + env | Modify |
| `tts-mcp/src/tts_mcp/runner.py` | `speak` execution orchestration | `run_speak()` | tool args -> `SpeakResult` | backend runtime + version check | Modify |
| `tts-mcp/src/tts_mcp/version_check.py` | Runtime freshness checks | `check_backend_runtime_version()` | backend + command -> status | PyPI/GitHub APIs | Modify |
| `tts-mcp/scripts/install_kokoro_onnx_linux.sh` | Kokoro runtime and asset installation | shell script `main` | env + network -> local runtime files | pip + GitHub API | Add |

## Naming Decisions

- `kokoro_onnx` backend name: explicit about model/runtime family and matches package naming.
- `TTS_MCP_LINUX_RUNTIME`: conveys Linux-only runtime policy for `auto` flow.
- `install_kokoro_onnx_linux.sh`: aligned with existing installer naming scheme.

## Naming Drift Check

- No drift introduced in existing module names.
- New names map directly to responsibilities; no rename required.

## Dependency Flow

- `server.speak` -> `runner.run_speak` -> `platform.select_backend` + `version_check` + backend execution.
- Linux bootstrap path from `create_server` startup:
  - `runtime_bootstrap.bootstrap_runtime` -> runtime policy decision -> selected installer script.
- No new cyclic dependency introduced.

## Error Handling

- Kokoro missing dependency/assets -> `dependency` error type with clear reason.
- Invalid policy/backend values -> `ConfigError`/`validation` path.
- Version check enforcement unchanged (`enforce_latest_runtime`).

## Use-Case Coverage Matrix

| use_case_id | Primary | Fallback | Error | Runtime Call Stack Section |
| --- | --- | --- | --- | --- |
| UC-001 | Yes | Yes | Yes | `future-state-runtime-call-stack.md` UC-001 |
| UC-002 | Yes | Yes | Yes | `future-state-runtime-call-stack.md` UC-002 |
| UC-003 | Yes | Yes | Yes | `future-state-runtime-call-stack.md` UC-003 |
| UC-004 | Yes | Yes | Yes | `future-state-runtime-call-stack.md` UC-004 |
