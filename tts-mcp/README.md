# TTS MCP Server

Python MCP server exposing one tool, `speak`, with backend auto-detection:

- Apple Silicon macOS -> `mlx_audio.tts.generate`
- Linux runtime policy -> `llama-tts` (llama.cpp) or `kokoro_onnx` (CPU ONNX)

If the host is unsupported or required commands are missing, the tool returns `ok=false`.

Model choice is config-driven via MCP environment variables (no per-call model switching).
Runtime freshness is checked automatically before speak generation.

## Tool

- `speak`
  - Input:
    - `text` (required)
    - `output_path` (optional, `.wav`; set this if you want to keep the generated file)
    - `play` (optional, default `true`)
  - Runtime behavior and voice/language/backend/model settings come from MCP environment variables.
  - Output:
    - Success: `{"ok": true}`
    - Failure: `{"ok": false, "reason": "<short failure reason>"}`
    - When `play=true`, success requires confirmed playback; if generation succeeds but playback fails, `speak` returns `ok=false`.
    - If selected runtime is not confirmed latest and `TTS_MCP_ENFORCE_LATEST=true`, `speak` returns `ok=false` with a reason.

## Supported MLX Models

Use one of these three models.

| Preset | Model ID | Quality | Notes |
| --- | --- | --- | --- |
| `kokoro_fast` | `mlx-community/Kokoro-82M-bf16` | Fast | Best latency/default (`en` auto-maps to Kokoro code `a`) |
| `qwen_base_hq` | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | High | Better naturalness |
| `qwen_voicedesign_hq` | `mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16` | High | Requires `instruct` |

Recommended MLX runtime for this matrix: `mlx-audio[tts] >= 0.3.1`.
Older `0.2.x` builds may fail on Qwen3-TTS models.

## Environment Variables

General:
- `TTS_MCP_BACKEND` (`auto` | `mlx_audio` | `llama_cpp` | `kokoro_onnx`, default `auto`)
- `TTS_MCP_LINUX_RUNTIME` (`llama_cpp` | `kokoro_onnx`, default `llama_cpp`; used when `TTS_MCP_BACKEND=auto` on Linux)
- `TTS_MCP_TIMEOUT_SECONDS` (default `180`)
- `TTS_MCP_PROCESS_LOCK_TIMEOUT_SECONDS` (default `30`; max wait time to acquire the global speech lock)
- `TTS_MCP_OUTPUT_DIR` (default `outputs`)
- `TTS_MCP_DELETE_AUTO_OUTPUT` (`true` | `false`, default `true`; deletes auto-generated `speak_*.wav` files after successful playback/generation)
- `TTS_MCP_LINUX_PLAYER` (`auto` | `ffplay` | `aplay` | `paplay` | `none`)
- `TTS_MCP_ENFORCE_LATEST` (`true` | `false`, default `true`)
- `TTS_MCP_VERSION_CHECK_TIMEOUT_SECONDS` (default `6`)
- `TTS_MCP_AUTO_INSTALL_RUNTIME` (`true` | `false`, default `true`)
- `TTS_MCP_AUTO_INSTALL_LLAMA_ON_MACOS` (`true` | `false`, default `false`)
- `TTS_MCP_HF_HUB_OFFLINE_MODE` (`auto` | `true` | `false`, default `auto`)
  - `auto`: if MLX model cache already exists, run MLX command with `HF_HUB_OFFLINE=1` to avoid blocking Hub metadata calls
  - `true`: always force offline Hub mode for MLX command
  - `false`: always allow Hub network calls
- `TTS_MCP_DEFAULT_SPEED` (default `1.0`; tool-level default speed used for generation)
- `TTS_MCP_NAME` (default `tts-mcp`)
- `TTS_MCP_INSTRUCTIONS` (optional)

Concurrency behavior:
- `speak` uses a global cross-process lock (`/tmp/tts_mcp_global_generation.lock`) so only one generation/playback runs at a time across multiple MCP server processes.
- If lock acquisition exceeds `TTS_MCP_PROCESS_LOCK_TIMEOUT_SECONDS`, tool returns `ok=false` with a busy reason.

MLX model selection:
- `TTS_MCP_MLX_MODEL_PRESET` (`kokoro_fast` | `qwen_base_hq` | `qwen_voicedesign_hq`, default `kokoro_fast`)
- `MLX_TTS_MODEL` (optional explicit model ID override; must be one of the supported model IDs above)
- `MLX_TTS_DEFAULT_INSTRUCT` (optional default instruct; useful for `qwen_voicedesign_hq`)

MLX backend:
- `MLX_TTS_COMMAND` (default `mlx_audio.tts.generate`)
- `MLX_TTS_DEFAULT_VOICE` (optional)
- `MLX_TTS_DEFAULT_LANG_CODE` (default `en`)

llama.cpp backend:
- `LLAMA_TTS_COMMAND` (default `llama-tts`)
- `LLAMA_TTS_USE_OUTE_DEFAULT` (default `true`)
- `LLAMA_TTS_MODEL_PATH` (optional)
- `LLAMA_TTS_VOCODER_PATH` (required when `LLAMA_TTS_MODEL_PATH` is set)
- `LLAMA_TTS_N_GPU_LAYERS` (default `-1`)

Kokoro ONNX backend:
- `KOKORO_TTS_MODEL_PATH` (default `.tools/kokoro-current/kokoro-v1.0.int8.onnx`)
- `KOKORO_TTS_VOICES_PATH` (default `.tools/kokoro-current/voices-v1.0.bin`)
- `KOKORO_TTS_DEFAULT_VOICE` (default `af_heart`)
- `KOKORO_TTS_DEFAULT_LANG_CODE` (default `en-us`)
- `KOKORO_TTS_MODEL_VARIANT` (installer-only optional: `int8` | `fp16` | `fp16-gpu` | `full`, default `int8`)

## Install

```bash
pip install -e .[test]
```

By default, runtime bootstrap is automatic on server startup (`TTS_MCP_AUTO_INSTALL_RUNTIME=true`):
- macOS Apple Silicon: installs missing MLX runtime
- Linux: installs runtime selected by `TTS_MCP_LINUX_RUNTIME`

Manual bootstrap scripts (optional):

```bash
# Auto-detect host and install runtime now
scripts/install_tts_runtime.sh

# Linux runtime override for manual installer
scripts/install_tts_runtime.sh --linux-runtime kokoro_onnx
```

Platform-specific installers:

```bash
# Apple Silicon macOS: latest mlx-audio runtime
scripts/install_mlx_audio_macos.sh

# Apple Silicon macOS: latest llama-tts runtime (optional)
scripts/install_llama_tts_macos.sh

# Linux: latest llama-tts runtime
scripts/install_llama_tts_linux.sh

# Linux: Kokoro ONNX runtime + model assets
scripts/install_kokoro_onnx_linux.sh
```

Linux installer note:
- Requires `python3` (preferred) or `python` in `PATH`.
- Optional override: set `PYTHON_BIN` to a specific Python executable.
- `install_kokoro_onnx_linux.sh` installs `kokoro-onnx` in the current Python environment and downloads model assets.

Linux playback routing note:
- For PipeWire/PulseAudio desktops, prefer `TTS_MCP_LINUX_PLAYER=paplay` to follow the default desktop sink.
- In MCP-hosted environments, set these env vars for reliable playback session routing:
  - `XDG_RUNTIME_DIR=/run/user/<uid>`
  - `PULSE_SERVER=unix:/run/user/<uid>/pulse/native`
  - `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus`

## Run

```bash
python -m tts_mcp.server
```

## MCP Config Example (Codex/Cursor style)

```toml
[mcp_servers.tts]
command = "uv"
args = [
  "--directory",
  "/ABS/PATH/autobyteus_mcps/tts-mcp",
  "run",
  "python",
  "-m",
  "tts_mcp.server",
]

[mcp_servers.tts.env]
TTS_MCP_BACKEND = "mlx_audio"
TTS_MCP_MLX_MODEL_PRESET = "qwen_voicedesign_hq"
MLX_TTS_DEFAULT_INSTRUCT = "A warm, clear female narrator voice with calm tone."
```

## Tests

Unit tests:

```bash
uv run python -m pytest
```

Real MLX integration smoke test (runs `speak` against all 3 MLX models):

```bash
PATH="/ABS/PATH/autobyteus_mcps/tts-mcp/.venv-mlx/bin:$PATH" \
TTS_MCP_RUN_REAL_MLX_SMOKE=1 \
uv run python -m pytest -q tests/test_real_mlx_models.py
```

This validates the practical success criterion: `speak` returns `ok=true` and a real WAV is generated for each model.

Real MCP tool-level playback test (calls MCP `speak` tool via MCP client session, with default `play=true`):

```bash
PATH="/ABS/PATH/autobyteus_mcps/tts-mcp/.venv-mlx/bin:$PATH" \
TTS_MCP_RUN_REAL_MCP_SPEAK=1 \
uv run python -m pytest -q tests/test_real_mcp_speak_tool.py
```

This verifies end-to-end MCP tool invocation and confirms a real WAV is produced in `TTS_MCP_OUTPUT_DIR`.

## Runtime Version Policy

- `mlx_audio` backend:
  - Local version is read from the Python environment behind `MLX_TTS_COMMAND`.
  - Latest version is fetched from PyPI (`mlx-audio`).
- `llama_cpp` backend:
  - Local version is read from `LLAMA_TTS_COMMAND --version`.
  - Latest version is fetched from GitHub releases (`ggml-org/llama.cpp`).
- `kokoro_onnx` backend:
  - Local version is read from installed Python package metadata (`kokoro-onnx`).
  - Latest version is fetched from PyPI (`kokoro-onnx`).

When `TTS_MCP_ENFORCE_LATEST=true`, `speak` is blocked unless runtime freshness is confirmed.

## Performance Benchmark

Measured on **February 13, 2026** on:
- Apple M1 Max (`arm64`)
- macOS `26.2`
- Python `3.13.9`
- `mlx-audio 0.3.1`

Command used:

```bash
PATH="/ABS/PATH/autobyteus_mcps/tts-mcp/.venv-mlx/bin:$PATH" \
PYTHONPATH="/ABS/PATH/autobyteus_mcps/tts-mcp/src" \
python /ABS/PATH/autobyteus_mcps/tts-mcp/scripts/benchmark_mlx_models.py \
  --warmup-runs 1 \
  --measure-runs 3 \
  --output-json /ABS/PATH/autobyteus_mcps/tts-mcp/benchmark/mlx_performance_latest.json \
  --output-dir /ABS/PATH/autobyteus_mcps/tts-mcp/benchmark/audio_outputs
```

Results (`run_speak(play=false)` internal benchmark path):

| Model | Text | Mean Latency (s) | Median (s) | Approx P95 (s) | Mean Audio (s) | Mean RTF |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `kokoro_fast` | short | 4.73 | 4.72 | 4.78 | 3.08 | 1.54 |
| `qwen_base_hq` | short | 7.40 | 7.50 | 8.11 | 2.91 | 2.68 |
| `qwen_voicedesign_hq` | short | 7.46 | 7.42 | 7.59 | 3.01 | 2.48 |
| `kokoro_fast` | medium | 5.00 | 5.01 | 5.02 | 11.60 | 0.43 |
| `qwen_base_hq` | medium | 13.14 | 13.14 | 13.51 | 9.76 | 1.35 |
| `qwen_voicedesign_hq` | medium | 14.22 | 14.10 | 14.73 | 10.99 | 1.30 |

Recommendation:
- If your UX requirement is "< 6 seconds wait", use **`kokoro_fast`**.
- Use **`qwen_base_hq`** when higher quality is more important than short-turn latency.
- Use **`qwen_voicedesign_hq`** only when you need custom voice design via `instruct`.

Raw benchmark artifact:
- `benchmark/mlx_performance_latest.json`
