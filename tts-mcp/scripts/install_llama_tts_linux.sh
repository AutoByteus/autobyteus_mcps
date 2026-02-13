#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/.tools"
mkdir -p "$TOOLS_DIR"

if [ "$(uname -s)" != "Linux" ]; then
  echo "This installer is for Linux only." >&2
  exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64)
    ASSET_HINTS=("ubuntu-x64")
    ;;
  aarch64|arm64)
    ASSET_HINTS=("ubuntu-arm64" "ubuntu-aarch64")
    ;;
  *)
    echo "Unsupported Linux architecture: $ARCH" >&2
    exit 1
    ;;
esac

echo "Resolving latest llama.cpp release for Linux ($ARCH)..."
read -r TAG URL ASSET_NAME < <(
python - "${ASSET_HINTS[@]}" <<'PY'
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

ARCHIVE_PATH="$TOOLS_DIR/$ASSET_NAME"
INSTALL_DIR="$TOOLS_DIR/llama-$TAG"
CURRENT_LINK="$TOOLS_DIR/llama-current"

echo "Downloading $TAG from $URL"
curl -L -o "$ARCHIVE_PATH" "$URL"

echo "Extracting to $TOOLS_DIR"
TMP_DIR="$TOOLS_DIR/.tmp-llama-$TAG"
rm -rf "$TMP_DIR" "$INSTALL_DIR"
mkdir -p "$TMP_DIR"
tar -xzf "$ARCHIVE_PATH" -C "$TMP_DIR"

if [ ! -d "$TMP_DIR/llama-$TAG" ]; then
  echo "Unexpected archive layout: missing llama-$TAG directory" >&2
  exit 1
fi

mv "$TMP_DIR/llama-$TAG" "$INSTALL_DIR"
rm -rf "$TMP_DIR"
ln -sfn "$INSTALL_DIR" "$CURRENT_LINK"

echo
echo "Installed llama.cpp $TAG to:"
echo "  $INSTALL_DIR"
echo
echo "llama-tts path:"
echo "  $CURRENT_LINK/llama-tts"
echo
echo "Version check:"
PATH="$CURRENT_LINK:$PATH" "$CURRENT_LINK/llama-tts" --version | sed -n '1,2p'
echo
echo "Set this in MCP env:"
echo "  LLAMA_TTS_COMMAND=\"$CURRENT_LINK/llama-tts\""
