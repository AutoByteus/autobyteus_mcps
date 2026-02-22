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

print_usage() {
  cat <<'EOF'
Usage:
  scripts/install_kokoro_onnx_linux.sh [--lang en|zh] [--profile v1_0|zh_v1_1] [--model-variant int8|fp16|fp16-gpu|full]

Profiles:
  v1_0    Default Kokoro v1.0 setup (English-first defaults).
  zh_v1_1 Kokoro v1.1 Mandarin setup with Misaki Zh phonemizer.

Environment overrides:
  KOKORO_TTS_PROFILE        Same as --profile (highest precedence)
  KOKORO_TTS_DEFAULT_LANG_CODE
                           If profile is not explicitly set, language auto-selects profile:
                             zh/cmn -> zh_v1_1, otherwise v1_0
  KOKORO_TTS_MODEL_VARIANT  Same as --model-variant (default: int8; v1_0 only)
  PYTHON_BIN                Python executable to use for pip/download steps
EOF
}

canonical_lang() {
  local value="$1"
  case "${value,,}" in
    zh|zh-cn|zh_hans|zh-hans|zh_cn|cmn|mandarin)
      printf 'zh\n'
      ;;
    en|en-us|en_us|english|"")
      printf 'en\n'
      ;;
    *)
      printf 'en\n'
      ;;
  esac
}

canonical_profile() {
  local profile="$1"
  case "${profile,,}" in
    v1_0|v1.0|default|en|en_v1_0)
      printf 'v1_0\n'
      ;;
    zh_v1_1|zh-v1.1|zh|cn|cmn)
      printf 'zh_v1_1\n'
      ;;
    *)
      return 1
      ;;
  esac
}

download_assets() {
  local python_bin install_dir
  python_bin="$1"
  install_dir="$2"
  shift 2
  "$python_bin" - "$install_dir" "$@" <<'PY'
import pathlib
import sys
import urllib.request

install_dir = pathlib.Path(sys.argv[1])
args = sys.argv[2:]
if len(args) % 2 != 0:
    raise SystemExit("download_assets expects pairs of: filename url")

install_dir.mkdir(parents=True, exist_ok=True)
for index in range(0, len(args), 2):
    filename = args[index]
    url = args[index + 1]
    target = install_dir / filename
    if target.exists() and target.stat().st_size > 0:
        print(f"Asset present: {target}")
        continue

    print(f"Downloading {filename}...")
    req = urllib.request.Request(url, headers={"User-Agent": "tts-mcp-kokoro-install"})
    with urllib.request.urlopen(req, timeout=180) as source:
        data = source.read()
    target.write_bytes(data)
    print(f"Saved {target} ({len(data)} bytes)")
PY
}

main() {
  local root_dir tools_dir install_dir python_bin model_variant model_filename model_path voices_path
  local profile profile_raw model_url voices_url vocab_config_path vocab_config_url
  local lang_raw lang

  if [ "$(uname -s)" != "Linux" ]; then
    echo "This installer is for Linux only." >&2
    exit 1
  fi

  profile_raw="${KOKORO_TTS_PROFILE:-}"
  profile="$profile_raw"
  lang_raw="${KOKORO_TTS_DEFAULT_LANG_CODE:-}"
  lang="$(canonical_lang "$lang_raw")"
  model_variant="${KOKORO_TTS_MODEL_VARIANT:-int8}"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --lang)
        shift
        if [ "$#" -eq 0 ]; then
          echo "Missing value for --lang (en|zh)" >&2
          exit 1
        fi
        lang_raw="$1"
        lang="$(canonical_lang "$1")"
        ;;
      --profile)
        shift
        if [ "$#" -eq 0 ]; then
          echo "Missing value for --profile (v1_0|zh_v1_1)" >&2
          exit 1
        fi
        profile_raw="$1"
        profile="$1"
        ;;
      --model-variant)
        shift
        if [ "$#" -eq 0 ]; then
          echo "Missing value for --model-variant (int8|fp16|fp16-gpu|full)" >&2
          exit 1
        fi
        model_variant="$1"
        ;;
      -h|--help)
        print_usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        print_usage >&2
        exit 1
        ;;
    esac
    shift
  done

  if [ -n "$profile" ]; then
    if ! profile="$(canonical_profile "$profile")"; then
      echo "Unsupported Kokoro profile: $profile_raw" >&2
      echo "Allowed profiles: v1_0, zh_v1_1" >&2
      exit 1
    fi
  else
    if [ "$lang" = "zh" ]; then
      profile="zh_v1_1"
    else
      profile="v1_0"
    fi
  fi

  root_dir="$(cd "$(dirname "$0")/.." && pwd)"
  tools_dir="$root_dir/.tools"
  mkdir -p "$tools_dir"

  python_bin="$(resolve_python_bin)"

  echo "Installing kokoro-onnx runtime into Python environment: $python_bin (profile=$profile)"
  if ! "$python_bin" -m pip --version >/dev/null 2>&1; then
    echo "pip not found in selected interpreter. Bootstrapping with ensurepip..."
    "$python_bin" -m ensurepip --upgrade
  fi
  "$python_bin" -m pip install --upgrade pip setuptools wheel
  "$python_bin" -m pip install --upgrade "kokoro-onnx"

  case "$profile" in
    v1_0)
      install_dir="$tools_dir/kokoro-current"
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
          echo "Unsupported model variant for v1_0 profile: $model_variant" >&2
          echo "Allowed: int8, fp16, fp16-gpu, full" >&2
          exit 1
          ;;
      esac
      model_url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$model_filename"
      voices_url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
      echo "Ensuring Kokoro v1.0 assets are present..."
      download_assets \
        "$python_bin" \
        "$install_dir" \
        "$model_filename" "$model_url" \
        "voices-v1.0.bin" "$voices_url"

      model_path="$install_dir/$model_filename"
      voices_path="$install_dir/voices-v1.0.bin"

      echo
      echo "Kokoro runtime installed."
      echo "Default model path: $model_path"
      echo "Voices path: $voices_path"
      echo
      echo "Set these in MCP env (minimal):"
      echo "  TTS_MCP_LINUX_RUNTIME=kokoro_onnx"
      echo "  KOKORO_TTS_DEFAULT_LANG_CODE=en"
      echo
      echo "Optional explicit paths:"
      echo "  KOKORO_TTS_MODEL_PATH=$model_path"
      echo "  KOKORO_TTS_VOICES_PATH=$voices_path"
      ;;
    zh_v1_1)
      if [ "$model_variant" != "int8" ]; then
        echo "Ignoring --model-variant=$model_variant for zh_v1_1 profile (fixed model asset)." >&2
      fi
      "$python_bin" -m pip install --upgrade "misaki-fork[zh]"

      install_dir="$tools_dir/kokoro-v1.1-zh"
      model_filename="kokoro-v1.1-zh.onnx"
      model_url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/$model_filename"
      voices_url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.1-zh.bin"
      vocab_config_url="https://huggingface.co/onnx-community/Kokoro-82M-v1.1-zh-ONNX/resolve/main/config.json"

      echo "Ensuring Kokoro v1.1 Mandarin assets are present..."
      download_assets \
        "$python_bin" \
        "$install_dir" \
        "$model_filename" "$model_url" \
        "voices-v1.1-zh.bin" "$voices_url" \
        "config.json" "$vocab_config_url"

      model_path="$install_dir/$model_filename"
      voices_path="$install_dir/voices-v1.1-zh.bin"
      vocab_config_path="$install_dir/config.json"

      echo
      echo "Kokoro Mandarin runtime installed."
      echo "Model path: $model_path"
      echo "Voices path: $voices_path"
      echo "Vocab config path: $vocab_config_path"
      echo
      echo "Set these in MCP env (minimal Mandarin setup):"
      echo "  TTS_MCP_LINUX_RUNTIME=kokoro_onnx"
      echo "  KOKORO_TTS_DEFAULT_LANG_CODE=zh"
      echo
      echo "Optional explicit overrides:"
      echo "  KOKORO_TTS_MODEL_PATH=$model_path"
      echo "  KOKORO_TTS_VOICES_PATH=$voices_path"
      echo "  KOKORO_TTS_VOCAB_CONFIG_PATH=$vocab_config_path"
      echo "  KOKORO_TTS_DEFAULT_VOICE=zf_001"
      echo "  KOKORO_TTS_MISAKI_ZH_VERSION=1.1"
      ;;
  esac

}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
