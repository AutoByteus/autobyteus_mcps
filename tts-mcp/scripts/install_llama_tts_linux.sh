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
  local root_dir tools_dir arch python_bin archive_path install_dir current_link tmp_dir tag url asset_name
  local -a asset_hints

  root_dir="$(cd "$(dirname "$0")/.." && pwd)"
  tools_dir="$root_dir/.tools"
  mkdir -p "$tools_dir"

  if [ "$(uname -s)" != "Linux" ]; then
    echo "This installer is for Linux only." >&2
    exit 1
  fi

  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64)
      asset_hints=("ubuntu-x64")
      ;;
    aarch64|arm64)
      asset_hints=("ubuntu-arm64" "ubuntu-aarch64")
      ;;
    *)
      echo "Unsupported Linux architecture: $arch" >&2
      exit 1
      ;;
  esac

  python_bin="$(resolve_python_bin)"

  echo "Resolving latest llama.cpp release for Linux ($arch)..."
  read -r tag url asset_name < <(
"$python_bin" - "${asset_hints[@]}" <<'PY'
import json
import sys
import urllib.request

hints = sys.argv[1:]
req = urllib.request.Request(
    "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
    headers={"User-Agent": "tts-mcp-install"},
)
with urllib.request.urlopen(req, timeout=30) as r:
    data = json.load(r)

tag = data["tag_name"]
assets = data.get("assets", [])

for hint in hints:
    wanted = f"llama-{tag}-bin-{hint}.tar.gz"
    for asset in assets:
        if asset.get("name") == wanted:
            print(tag, asset.get("browser_download_url"), wanted)
            raise SystemExit(0)

available = [a.get("name", "") for a in assets if "ubuntu" in a.get("name", "")]
raise SystemExit(
    "Could not find a matching Linux asset for this architecture. "
    f"Checked hints={hints}. Available ubuntu assets={available}"
)
PY
)

  archive_path="$tools_dir/$asset_name"
  install_dir="$tools_dir/llama-$tag"
  current_link="$tools_dir/llama-current"

  echo "Downloading $tag from $url"
  curl -L -o "$archive_path" "$url"

  echo "Extracting to $tools_dir"
  tmp_dir="$tools_dir/.tmp-llama-$tag"
  rm -rf "$tmp_dir" "$install_dir"
  mkdir -p "$tmp_dir"
  tar -xzf "$archive_path" -C "$tmp_dir"

  if [ ! -d "$tmp_dir/llama-$tag" ]; then
    echo "Unexpected archive layout: missing llama-$tag directory" >&2
    exit 1
  fi

  mv "$tmp_dir/llama-$tag" "$install_dir"
  rm -rf "$tmp_dir"
  ln -sfn "$install_dir" "$current_link"

  echo
  echo "Installed llama.cpp $tag to:"
  echo "  $install_dir"
  echo
  echo "llama-tts path:"
  echo "  $current_link/llama-tts"
  echo
  echo "Version check:"
  PATH="$current_link:$PATH" "$current_link/llama-tts" --version | sed -n '1,2p'
  echo
  echo "Set this in MCP env:"
  echo "  LLAMA_TTS_COMMAND=\"$current_link/llama-tts\""
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
