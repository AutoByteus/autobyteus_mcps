#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This installer is for macOS only." >&2
  exit 1
fi

if [ "$(uname -m)" != "arm64" ]; then
  echo "This installer supports Apple Silicon only (arm64)." >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON_BIN" >&2
  exit 1
fi

VENV_DIR="$ROOT_DIR/.venv-mlx"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "Installing latest MLX Audio runtime..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install --upgrade "mlx-audio[tts]" "mcp>=1.13.1"

echo
echo "MLX audio command:"
echo "  $VENV_DIR/bin/mlx_audio.tts.generate"

echo
echo "MLX Audio version:"
"$VENV_DIR/bin/python" - <<'PY'
import importlib.metadata as m
print(m.version("mlx-audio"))
PY

if command -v ffplay >/dev/null 2>&1; then
  echo
  echo "Playback tool found: $(command -v ffplay)"
else
  echo
  echo "ffplay not found (recommended for manual playback checks)." >&2
  if command -v brew >/dev/null 2>&1; then
    echo "Installing ffmpeg via Homebrew..."
    brew install ffmpeg
  else
    echo "Install ffmpeg manually to get ffplay." >&2
  fi
fi

echo
echo "Set this in MCP env:"
echo "  MLX_TTS_COMMAND=\"$VENV_DIR/bin/mlx_audio.tts.generate\""
