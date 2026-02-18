#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

INSTALL_MAC_LLAMA="false"
LINUX_RUNTIME="${TTS_MCP_LINUX_RUNTIME:-llama_cpp}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --with-llama-macos)
      INSTALL_MAC_LLAMA="true"
      ;;
    --linux-runtime)
      shift
      if [ "$#" -eq 0 ]; then
        echo "Missing value for --linux-runtime (llama_cpp|kokoro_onnx)" >&2
        exit 1
      fi
      LINUX_RUNTIME="$1"
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  scripts/install_tts_runtime.sh [--with-llama-macos] [--linux-runtime llama_cpp|kokoro_onnx]

Behavior:
  - macOS arm64: installs latest MLX Audio runtime (required), and optionally llama-tts
  - Linux: installs runtime selected by --linux-runtime (default: TTS_MCP_LINUX_RUNTIME or llama_cpp)
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

OS="$(uname -s)"
ARCH="$(uname -m)"

if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
  echo "Detected Apple Silicon macOS."
  "$ROOT_DIR/scripts/install_mlx_audio_macos.sh"
  if [ "$INSTALL_MAC_LLAMA" = "true" ]; then
    "$ROOT_DIR/scripts/install_llama_tts_macos.sh"
  fi
  exit 0
fi

if [ "$OS" = "Linux" ]; then
  echo "Detected Linux."
  case "$LINUX_RUNTIME" in
    llama_cpp)
      "$ROOT_DIR/scripts/install_llama_tts_linux.sh"
      ;;
    kokoro_onnx)
      "$ROOT_DIR/scripts/install_kokoro_onnx_linux.sh"
      ;;
    *)
      echo "Unsupported Linux runtime: $LINUX_RUNTIME (allowed: llama_cpp, kokoro_onnx)" >&2
      exit 1
      ;;
  esac
  exit 0
fi

echo "Unsupported platform for automatic runtime install: $OS/$ARCH" >&2
exit 1
