# Requirements

## Status

- `Design-ready`

## Goal / Problem Statement

`tts-mcp` must run successfully on this Ubuntu Linux host and produce speech through the existing `speak` tool path (`llama_cpp` backend), including runtime bootstrap/install behavior.

## In-Scope Use Cases

- `UC-001`: Runtime installer for Linux resolves a valid Python executable and completes release asset discovery/download.
- `UC-002`: `speak` tool invocation on Linux (`llama_cpp`) generates a valid WAV file (`ok=true`).

## Acceptance Criteria

- Linux installer script no longer fails on hosts without `python` alias when `python3` exists.
- Existing test suite remains green.
- New/updated automated test covers Linux installer Python executable resolution behavior.
- On current host, end-to-end Linux speech generation succeeds and produces valid WAV output.

## Constraints / Dependencies

- Host must have NVIDIA-capable environment for `llama_cpp` backend path.
- Runtime depends on latest llama.cpp release asset availability from GitHub.

## Assumptions

- `python3` is available on target Ubuntu host.
- Network access is available for runtime download and model/runtime setup.

## Open Questions / Risks

- Download/runtime startup time may be high during first run.
- Latest release packaging format could change and break asset matching logic.
- Runtime binary may have host-specific execution/runtime-library issues after install.

## Scope Classification

- Final classification: `Small`
- Rationale: expected touch set is limited (`scripts/install_llama_tts_linux.sh`, targeted test file(s), possibly README note) with no cross-module architecture change.
