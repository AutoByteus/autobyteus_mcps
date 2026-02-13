#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LLAMA_DIR="$ROOT_DIR/.tools/llama-current"

if [ ! -x "$LLAMA_DIR/llama-tts" ]; then
  echo "llama-tts not found at $LLAMA_DIR/llama-tts" >&2
  echo "Run: scripts/install_llama_tts_macos.sh" >&2
  exit 1
fi

OUT_DIR="$ROOT_DIR/real_smoke_outputs"
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/llama_tts_macos_smoke.wav"
rm -f "$OUT_FILE"

echo "Generating speech with llama-tts..."
PATH="$LLAMA_DIR:$PATH" "$LLAMA_DIR/llama-tts" \
  --tts-oute-default \
  -p "Hello from llama TTS running on Apple Silicon Mac." \
  -o "$OUT_FILE"

echo "Generated: $OUT_FILE"
wc -c "$OUT_FILE"

if command -v ffplay >/dev/null 2>&1; then
  echo "Playing generated audio via ffplay..."
  ffplay -nodisp -autoexit "$OUT_FILE"
else
  echo "ffplay not found; skipped playback."
fi
