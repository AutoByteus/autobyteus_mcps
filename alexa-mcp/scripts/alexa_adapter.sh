#!/usr/bin/env bash
set -euo pipefail

# Thin adapter that maps Alexa MCP command calls onto alexa_remote_control.sh.
# Expected invocation shape from MCP runner:
#   alexa_adapter.sh [-d "<echo device>"] -e "<event>"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_VENDOR_SCRIPT="${SCRIPT_DIR}/vendor/alexa-remote-control/alexa_remote_control.sh"

REMOTE_SCRIPT="${ALEXA_REMOTE_CONTROL_SCRIPT:-$DEFAULT_VENDOR_SCRIPT}"

if [[ ! -f "$REMOTE_SCRIPT" ]]; then
  echo "alexa_adapter: remote script not found: $REMOTE_SCRIPT" >&2
  echo "Run scripts/bootstrap_alexa_adapter.sh or set ALEXA_REMOTE_CONTROL_SCRIPT." >&2
  exit 2
fi

if [[ ! -x "$REMOTE_SCRIPT" ]]; then
  chmod +x "$REMOTE_SCRIPT"
fi

if [[ -z "${REFRESH_TOKEN:-}" ]] && [[ -n "${ALEXA_REFRESH_TOKEN_FILE:-}" ]]; then
  if [[ -f "$ALEXA_REFRESH_TOKEN_FILE" ]]; then
    # shellcheck disable=SC2002
    REFRESH_TOKEN="$(cat "$ALEXA_REFRESH_TOKEN_FILE")"
    export REFRESH_TOKEN
  fi
fi

if [[ -z "${AMAZON:-}" ]]; then
  export AMAZON="${ALEXA_AMAZON_DOMAIN:-amazon.de}"
fi

if [[ -z "${ALEXA:-}" ]]; then
  export ALEXA="${ALEXA_APP_DOMAIN:-alexa.amazon.de}"
fi

if [[ -z "${REFRESH_TOKEN:-}" ]]; then
  echo "alexa_adapter: REFRESH_TOKEN is not set." >&2
  echo "Set REFRESH_TOKEN or ALEXA_REFRESH_TOKEN_FILE in MCP env." >&2
  exit 3
fi

exec "$REMOTE_SCRIPT" "$@"
