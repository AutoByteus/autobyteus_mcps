#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

INSTALL_MAC_LLAMA="false"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --with-llama-macos)
      INSTALL_MAC_LLAMA="true"
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  scripts/install_tts_runtime.sh [--with-llama-macos]

Behavior:
  - macOS arm64: installs latest MLX Audio runtime (required), and optionally llama-tts
  - Linux: installs latest llama-tts runtime
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
  "$ROOT_DIR/scripts/install_llama_tts_linux.sh"
  exit 0
fi

echo "Unsupported platform for automatic runtime install: $OS/$ARCH" >&2
exit 1
