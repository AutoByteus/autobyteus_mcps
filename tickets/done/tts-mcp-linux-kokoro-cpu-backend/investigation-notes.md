# Investigation Notes

## Ticket

- Name: `tts-mcp-linux-kokoro-cpu-backend`
- Date: 2026-02-18
- Objective: Add Linux CPU Kokoro ONNX backend to `tts-mcp`, selectable via env/runtime policy, with auto-install behavior.

## Sources Consulted

- Local code:
  - `tts-mcp/src/tts_mcp/config.py`
  - `tts-mcp/src/tts_mcp/platform.py`
  - `tts-mcp/src/tts_mcp/runtime_bootstrap.py`
  - `tts-mcp/src/tts_mcp/runner.py`
  - `tts-mcp/src/tts_mcp/version_check.py`
  - `tts-mcp/scripts/install_tts_runtime.sh`
  - `tts-mcp/scripts/install_llama_tts_linux.sh`
  - `tts-mcp/tests/test_config.py`
  - `tts-mcp/tests/test_platform.py`
  - `tts-mcp/tests/test_runtime_bootstrap.py`
  - `tts-mcp/tests/test_runner.py`
- Web references:
  - `kokoro-onnx` API source (`Kokoro.create`): https://raw.githubusercontent.com/thewh1teagle/kokoro-onnx/main/kokoro_onnx/__init__.py
  - `kokoro-onnx` latest package metadata (`0.5.0`, dependencies): https://pypi.org/pypi/kokoro-onnx/json
  - `kokoro-onnx` model release assets (`model-files-v1.0`): https://api.github.com/repos/thewh1teagle/kokoro-onnx/releases/tags/model-files-v1.0

## Key Findings

- Existing backend model is command-centric (`mlx_audio` command on macOS, `llama-tts` on Linux).
- Linux path currently assumes `llama_cpp` runtime for auto-install and backend routing.
- `kokoro-onnx` provides Python API (`Kokoro(model_path, voices_path).create(...)`) and can run CPU without NVIDIA.
- Official model assets are available and compact enough for runtime bootstrap:
  - `kokoro-v1.0.int8.onnx`
  - `voices-v1.0.bin`
- User request needs Linux runtime selection via env and automatic installer behavior.

## Constraints

- Keep Linux path stable for existing `llama_cpp` users.
- Avoid hard coupling tests to real `kokoro-onnx` installation.
- Preserve current `speak` tool contract (`ok=true/false`, reason on failure).

## Unknowns

- Minor API behavior differences across `kokoro-onnx` versions; mitigated via runtime version check + explicit model files.
- Voice/language defaults may need later tuning for target UX.

## Implications For Design

- Introduce explicit Linux runtime policy env (default keeps current behavior; opt-in to Kokoro).
- Add first-class `kokoro_onnx` backend with in-process generation path and existing Linux playback flow.
- Add Linux Kokoro installer script and wire bootstrap selection to runtime policy.
- Extend tests across config/platform/bootstrap/runner/version checks.

## Validation Results (2026-02-18)

- `uv run python -m pytest -q`: `47 passed, 4 skipped`.
- Kokoro installer smoke:
  - `PYTHON_BIN=.venv/bin/python ./scripts/install_kokoro_onnx_linux.sh` succeeded.
  - Installed `kokoro-onnx` + assets in `.tools/kokoro-current/`.
- Real Linux Kokoro generation:
  - `run_speak(... backend='kokoro_onnx', play=false)` -> `ok=true`, WAV generated (`outputs/kokoro_linux_cpu_smoke.wav`).
- Real MCP tool-level test:
  - `create_server()` with `TTS_MCP_BACKEND=auto`, `TTS_MCP_LINUX_RUNTIME=kokoro_onnx` -> `payload={'ok': True}`, WAV generated (`outputs/kokoro_mcp_auto_linux.wav`).
- Linux playback check:
  - `run_speak(... play=true)` on Kokoro -> `ok=true`, `played=true`, no warnings.
