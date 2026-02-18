# Requirements

## Status

- `Design-ready`

## Goal / Problem Statement

Enable `tts-mcp` to run Kokoro ONNX on Linux CPU as a selectable backend, with automatic runtime installation based on Linux runtime policy env configuration.

## In-Scope Use Cases

- `UC-001`: Linux backend auto-selection honors runtime policy and can route to `kokoro_onnx`.
- `UC-002`: `speak` succeeds with `kokoro_onnx` backend (`ok=true`) and writes valid WAV.
- `UC-003`: Linux runtime bootstrap auto-installs Kokoro runtime/assets when policy selects Kokoro and runtime is missing.
- `UC-004`: Existing `llama_cpp` Linux path remains functional when policy stays on llama.

## Acceptance Criteria

- New backend value `kokoro_onnx` is supported in config and runtime selection.
- New env policy exists for Linux runtime choice and is documented.
- Runtime bootstrap installs Kokoro runtime/assets automatically for Linux when selected.
- `run_speak` supports Kokoro path and existing playback behavior on Linux.
- Automated tests cover config/platform/bootstrap/runner changes.
- Existing test suite remains passing.

## Constraints / Dependencies

- Kokoro runtime depends on Python package `kokoro-onnx` and model assets (`kokoro-v1.0.*.onnx`, `voices-v1.0.bin`).
- Version freshness checks remain enforced under `TTS_MCP_ENFORCE_LATEST=true`.

## Assumptions

- Linux runtime auto-install can use network access to PyPI/GitHub.
- Default Kokoro model variant can be `int8` for CPU-first footprint/perf.

## Open Questions / Risks

- Potential quality/perf tradeoff across model variants.
- Future Kokoro release asset naming could change.

## Scope Classification

- Final classification: `Medium`
- Rationale: cross-cutting updates across config, platform selection, runner execution, runtime bootstrap/install scripts, version checks, docs, and multiple test suites.
