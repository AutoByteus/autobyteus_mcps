# Future-State Runtime Call Stacks (Debug-Trace Style)

## Design Basis

- Scope Classification: `Small`
- Call Stack Version: `v1`
- Requirements: `tickets/in-progress/tts-mcp-linux-speak-enable/requirements.md` (status `Design-ready`)
- Source Artifact:
  - `Small`: `tickets/in-progress/tts-mcp-linux-speak-enable/implementation-plan.md`
- Source Design Version: `v1`
- Referenced Sections:
  - `Solution Sketch`
  - `Step-By-Step Plan`

## Use Case Index (Stable IDs)

| use_case_id | Requirement | Use Case Name | Coverage Target (Primary/Fallback/Error) |
| --- | --- | --- | --- |
| UC-001 | R-001 | Linux installer resolves Python executable and installs runtime | Yes/Yes/Yes |
| UC-002 | R-002 | Linux speak generation produces valid WAV | Yes/Yes/Yes |

## Transition Notes

- No migration layer required; this is a direct installer reliability fix.

## Use Case: UC-001 Linux Installer Works Without `python` Alias

### Goal

Enable `install_llama_tts_linux.sh` to run on Ubuntu environments where only `python3` is available.

### Preconditions

- Host OS is Linux.
- Either `python3` or `python` exists in `PATH`.

### Expected Outcome

- Script resolves interpreter, fetches latest release metadata, downloads and installs runtime.

### Primary Runtime Call Stack

```text
[ENTRY] tts-mcp/src/tts_mcp/runtime_bootstrap.py:bootstrap_runtime(settings)
├── [IO] tts-mcp/src/tts_mcp/runtime_bootstrap.py:_run_install_script("install_llama_tts_linux.sh")
└── [ENTRY] tts-mcp/scripts/install_llama_tts_linux.sh:main
    ├── tts-mcp/scripts/install_llama_tts_linux.sh:resolve_python_bin()
    ├── [IO] tts-mcp/scripts/install_llama_tts_linux.sh:"$PYTHON_BIN" - <<PY ... GitHub release API ...
    ├── [IO] tts-mcp/scripts/install_llama_tts_linux.sh:curl download tarball
    ├── [IO] tts-mcp/scripts/install_llama_tts_linux.sh:tar extract + symlink `.tools/llama-current`
    └── [IO] tts-mcp/scripts/install_llama_tts_linux.sh:verify `llama-tts --version`
```

### Branching / Fallback Paths

```text
[FALLBACK] if `PYTHON_BIN` env var set
install_llama_tts_linux.sh:resolve_python_bin()
└── validate and use configured binary
```

```text
[FALLBACK] if `python3` missing but `python` exists
install_llama_tts_linux.sh:resolve_python_bin()
└── choose `python`
```

```text
[ERROR] if neither `python3` nor `python` exists
install_llama_tts_linux.sh:resolve_python_bin()
└── stderr "Python not found..." and exit non-zero
```

### State And Data Transformations

- GitHub release JSON -> `(tag, asset_url, asset_name)`.
- archive bytes -> extracted runtime directory + stable symlink.

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `Covered`

## Use Case: UC-002 Linux Speak Produces Valid WAV

### Goal

Confirm `speak` generation succeeds on this Linux host after runtime install.

### Preconditions

- `llama-tts` available in PATH or configured through `LLAMA_TTS_COMMAND`.
- Backend selection resolves to `llama_cpp`.

### Expected Outcome

- `run_speak` returns `ok=true` and writes valid `.wav` file.

### Primary Runtime Call Stack

```text
[ENTRY] tts-mcp/src/tts_mcp/server.py:speak(...)
└── tts-mcp/src/tts_mcp/runner.py:run_speak(...)
    ├── tts-mcp/src/tts_mcp/platform.py:select_backend(...)  # selects llama_cpp on Linux+NVIDIA
    ├── tts-mcp/src/tts_mcp/runner.py:_build_llama_command(...)
    ├── [IO] tts-mcp/src/tts_mcp/runner.py:_execute(llama-tts ...)
    ├── tts-mcp/src/tts_mcp/runner.py:_output_signature(...) [STATE]
    └── return {"ok": true}
```

### Branching / Fallback Paths

```text
[FALLBACK] if `play=true` and no player binary
runner.py:_build_linux_play_command(...)
└── return warning, keep `ok=true`
```

```text
[ERROR] if runtime missing/outdated when enforced
runner.py:check_backend_runtime_version(...)
└── return dependency error (`ok=false`)
```

### State And Data Transformations

- Input text -> llama CLI args.
- generated PCM stream -> WAV file persisted at output path.

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `Covered`
