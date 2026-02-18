# Future-State Runtime Call Stacks (Debug-Trace Style)

## Design Basis

- Scope Classification: `Medium`
- Call Stack Version: `v1`
- Requirements: `tickets/in-progress/tts-mcp-linux-kokoro-cpu-backend/requirements.md` (`Design-ready`)
- Source Artifact: `tickets/in-progress/tts-mcp-linux-kokoro-cpu-backend/proposed-design.md` (`v1`)

## Use Case Index (Stable IDs)

| use_case_id | Requirement | Use Case Name | Coverage Target (Primary/Fallback/Error) |
| --- | --- | --- | --- |
| UC-001 | R-001 | Linux auto backend selects Kokoro by runtime policy | Yes/Yes/Yes |
| UC-002 | R-002 | Speak generation via Kokoro backend | Yes/Yes/Yes |
| UC-003 | R-003 | Linux bootstrap auto-installs Kokoro runtime/assets | Yes/Yes/Yes |
| UC-004 | R-004 | Existing llama Linux path remains intact | Yes/Yes/Yes |

## Use Case: UC-001 Linux Auto Backend Selects Kokoro

### Primary Runtime Call Stack

```text
[ENTRY] tts-mcp/src/tts_mcp/server.py:create_server(...)
└── tts-mcp/src/tts_mcp/server.py:speak(...)
    └── tts-mcp/src/tts_mcp/runner.py:run_speak(...)
        └── tts-mcp/src/tts_mcp/platform.py:select_backend(...)
            ├── read settings.default_backend + settings.linux_runtime
            └── choose backend `kokoro_onnx` on Linux when policy requires
```

### Fallback / Error

```text
[FALLBACK] Linux runtime policy = llama_cpp
select_backend(...) -> backend `llama_cpp`
```

```text
[ERROR] Linux runtime policy invalid or unsupported host/backend combo
select_backend(...) -> BackendSelectionError
```

## Use Case: UC-002 Speak Generation Via Kokoro

### Primary Runtime Call Stack

```text
[ENTRY] tts-mcp/src/tts_mcp/server.py:speak(...)
└── tts-mcp/src/tts_mcp/runner.py:run_speak(...)
    ├── tts-mcp/src/tts_mcp/version_check.py:check_backend_runtime_version(backend="kokoro_onnx")
    ├── tts-mcp/src/tts_mcp/runner.py:_run_kokoro_onnx(...)
    │   ├── load kokoro runtime [ASYNC/IO: module import + model file read]
    │   ├── Kokoro(...).create(text, voice, speed, lang)
    │   └── write WAV output [IO]
    └── optional linux playback via ffplay/aplay/paplay
```

### Fallback / Error

```text
[FALLBACK] play=true but no player binary found
run_speak(...) -> ok=true + warning
```

```text
[ERROR] kokoro package/model/voices missing
_run_kokoro_onnx(...) -> dependency failure -> ok=false
```

## Use Case: UC-003 Linux Bootstrap Auto-Installs Kokoro

### Primary Runtime Call Stack

```text
[ENTRY] tts-mcp/src/tts_mcp/server.py:create_server(...)
└── tts-mcp/src/tts_mcp/runtime_bootstrap.py:bootstrap_runtime(...)
    ├── detect host Linux
    ├── evaluate runtime policy (`TTS_MCP_LINUX_RUNTIME`)
    └── [IO] run `scripts/install_kokoro_onnx_linux.sh` when runtime/assets missing
```

### Fallback / Error

```text
[FALLBACK] runtime already present
bootstrap_runtime(...) -> no install, notes=[]
```

```text
[ERROR] installer script failure
bootstrap_runtime(...) -> RuntimeError with captured output
```

## Use Case: UC-004 Llama Path Remains Intact

### Primary Runtime Call Stack

```text
[ENTRY] runner.py:run_speak(... preferred_backend="auto")
└── platform.py:select_backend(... linux_runtime="llama_cpp", has_nvidia=true)
    └── existing llama command flow unchanged
```

### Fallback / Error

```text
[FALLBACK] explicit backend=llama_cpp
select_backend(...) honors explicit backend
```

```text
[ERROR] llama command missing
select_backend(...) -> dependency error
```
