#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

INSTALL_MAC_LLAMA="false"
LINUX_RUNTIME="${TTS_MCP_LINUX_RUNTIME:-kokoro_onnx}"
KOKORO_PROFILE="${KOKORO_TTS_PROFILE:-}"
KOKORO_LANG="${KOKORO_TTS_DEFAULT_LANG_CODE:-}"
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
    --kokoro-profile)
      shift
      if [ "$#" -eq 0 ]; then
        echo "Missing value for --kokoro-profile (v1_0|zh_v1_1)" >&2
        exit 1
      fi
      KOKORO_PROFILE="$1"
      ;;
    --lang)
      shift
      if [ "$#" -eq 0 ]; then
        echo "Missing value for --lang (en|zh)" >&2
        exit 1
      fi
      KOKORO_LANG="$1"
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  scripts/install_tts_runtime.sh [--with-llama-macos] [--linux-runtime llama_cpp|kokoro_onnx] [--lang en|zh] [--kokoro-profile v1_0|zh_v1_1]

Behavior:
  - macOS arm64: installs latest MLX Audio runtime (required), and optionally llama-tts
  - Linux: installs runtime selected by --linux-runtime (default: TTS_MCP_LINUX_RUNTIME or kokoro_onnx)
  - When Linux runtime is kokoro_onnx:
      - --lang zh auto-selects Mandarin install profile (zh_v1_1)
      - --lang en auto-selects English install profile (v1_0)
      - --kokoro-profile overrides language auto-selection
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
      kokoro_args=()
      if [ -n "$KOKORO_LANG" ]; then
        kokoro_args+=(--lang "$KOKORO_LANG")
      fi
      if [ -n "$KOKORO_PROFILE" ]; then
        kokoro_args+=(--profile "$KOKORO_PROFILE")
      fi
      "$ROOT_DIR/scripts/install_kokoro_onnx_linux.sh" "${kokoro_args[@]}"
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
