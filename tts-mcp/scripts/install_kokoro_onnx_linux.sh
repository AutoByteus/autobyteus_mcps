#!/usr/bin/env bash
set -euo pipefail

resolve_python_bin() {
  if [ -n "${PYTHON_BIN:-}" ]; then
    if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      printf '%s\n' "$PYTHON_BIN"
      return 0
    fi
    echo "Python not found: $PYTHON_BIN" >&2
    return 1
  fi

  if command -v python3 >/dev/null 2>&1; then
    printf 'python3\n'
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    printf 'python\n'
    return 0
  fi

  echo "Python not found: install python3 (preferred) or python, or set PYTHON_BIN." >&2
  return 1
}

main() {
  local root_dir tools_dir install_dir python_bin model_variant model_filename model_path voices_path

  if [ "$(uname -s)" != "Linux" ]; then
    echo "This installer is for Linux only." >&2
    exit 1
  fi

  root_dir="$(cd "$(dirname "$0")/.." && pwd)"
  tools_dir="$root_dir/.tools"
  install_dir="$tools_dir/kokoro-current"
  mkdir -p "$install_dir"

  python_bin="$(resolve_python_bin)"
  model_variant="${KOKORO_TTS_MODEL_VARIANT:-int8}"

  case "$model_variant" in
    int8)
      model_filename="kokoro-v1.0.int8.onnx"
      ;;
    fp16)
      model_filename="kokoro-v1.0.fp16.onnx"
      ;;
    fp16-gpu)
      model_filename="kokoro-v1.0.fp16-gpu.onnx"
      ;;
    full)
      model_filename="kokoro-v1.0.onnx"
      ;;
    *)
      echo "Unsupported KOKORO_TTS_MODEL_VARIANT: $model_variant" >&2
      echo "Allowed: int8, fp16, fp16-gpu, full" >&2
      exit 1
      ;;
  esac

  model_path="$install_dir/$model_filename"
  voices_path="$install_dir/voices-v1.0.bin"

  echo "Installing kokoro-onnx runtime into Python environment: $python_bin"
  if ! "$python_bin" -m pip --version >/dev/null 2>&1; then
    echo "pip not found in selected interpreter. Bootstrapping with ensurepip..."
    "$python_bin" -m ensurepip --upgrade
  fi
  "$python_bin" -m pip install --upgrade pip setuptools wheel
  "$python_bin" -m pip install --upgrade "kokoro-onnx"

  echo "Ensuring Kokoro model assets are present..."
  "$python_bin" - "$install_dir" "$model_filename" <<'PY'
import json
import pathlib
import sys
import urllib.request

install_dir = pathlib.Path(sys.argv[1])
model_filename = sys.argv[2]
voices_filename = "voices-v1.0.bin"

req = urllib.request.Request(
    "https://api.github.com/repos/thewh1teagle/kokoro-onnx/releases/tags/model-files-v1.0",
    headers={"User-Agent": "tts-mcp-kokoro-install"},
)
with urllib.request.urlopen(req, timeout=30) as response:
    release = json.load(response)

assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}

for filename in (model_filename, voices_filename):
    target = install_dir / filename
    if target.exists() and target.stat().st_size > 0:
        print(f"Asset present: {target}")
        continue

    url = assets.get(filename)
    if not url:
        raise SystemExit(f"Missing release asset: {filename}")

    print(f"Downloading {filename}...")
    with urllib.request.urlopen(url, timeout=120) as source:
        data = source.read()
    target.write_bytes(data)
    print(f"Saved {target} ({len(data)} bytes)")
PY

  echo
  echo "Kokoro runtime installed."
  echo "Default model path: $model_path"
  echo "Voices path: $voices_path"
  echo
  echo "Set these in MCP env to use Kokoro on Linux auto backend:"
  echo "  TTS_MCP_LINUX_RUNTIME=kokoro_onnx"
  echo "  KOKORO_TTS_MODEL_PATH=$model_path"
  echo "  KOKORO_TTS_VOICES_PATH=$voices_path"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
