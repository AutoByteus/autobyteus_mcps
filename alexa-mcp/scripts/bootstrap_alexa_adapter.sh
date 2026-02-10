#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="${SCRIPT_DIR}/vendor/alexa-remote-control"
REPO_URL="${ALEXA_REMOTE_CONTROL_REPO:-https://github.com/thorsten-gehrig/alexa-remote-control.git}"

echo "Bootstrapping alexa-remote-control into:"
echo "  $VENDOR_DIR"

mkdir -p "${SCRIPT_DIR}/vendor"

if [[ -d "$VENDOR_DIR/.git" ]]; then
  echo "Existing checkout found; pulling latest changes..."
  git -C "$VENDOR_DIR" pull --ff-only
else
  echo "Cloning repository..."
  git clone "$REPO_URL" "$VENDOR_DIR"
fi

chmod +x "$VENDOR_DIR/alexa_remote_control.sh"

echo
echo "Bootstrap complete."
echo
echo "Next required setup (one-time):"
echo "1) Create Alexa refresh token and export it:"
echo "   export REFRESH_TOKEN='YOUR_TOKEN'"
echo "2) Set region/app domains if needed:"
echo "   export AMAZON='amazon.de'"
echo "   export ALEXA='alexa.amazon.de'"
echo "3) Test command:"
echo "   $SCRIPT_DIR/alexa_adapter.sh -e \"textcommand:what time is it\""
echo
echo "Then use this as ALEXA_COMMAND in MCP config:"
echo "  $SCRIPT_DIR/alexa_adapter.sh"
