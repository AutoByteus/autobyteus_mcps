#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/.tools"
mkdir -p "$TOOLS_DIR"

echo "Resolving latest llama.cpp release..."
read -r TAG URL < <(
python - <<'PY'
import json
import urllib.request

req = urllib.request.Request(
    "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
    headers={"User-Agent": "tts-mcp-install"},
)
with urllib.request.urlopen(req, timeout=30) as r:
    data = json.load(r)

tag = data["tag_name"]
asset_name = f"llama-{tag}-bin-macos-arm64.tar.gz"
url = None
for asset in data.get("assets", []):
    if asset.get("name") == asset_name:
        url = asset.get("browser_download_url")
        break

if not url:
    raise SystemExit(f"Could not find asset {asset_name} in release {tag}")

print(tag, url)
PY
)

ARCHIVE_PATH="$TOOLS_DIR/llama-${TAG}-bin-macos-arm64.tar.gz"
INSTALL_DIR="$TOOLS_DIR/llama-${TAG}"
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
echo "To use it in this shell:"
echo "  export PATH=\"$CURRENT_LINK:\$PATH\""
