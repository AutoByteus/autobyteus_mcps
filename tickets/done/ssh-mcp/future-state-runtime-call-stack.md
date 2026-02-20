# Future-State Runtime Call Stacks (Debug-Trace Style)

## Design Basis
- Scope Classification: Medium
- Call Stack Version: v5
- Requirements: `tickets/in-progress/ssh-mcp/requirements.md` (status `Refined`)
- Source Artifact: `tickets/in-progress/ssh-mcp/proposed-design.md`
- Source Design Version: v5

## Use Case Index (Stable IDs)
| use_case_id | Requirement | Use Case Name | Coverage Target (Primary/Fallback/Error) |
| --- | --- | --- | --- |
| UC-001 | R-001 | SSH command health check | Yes/N/A/Yes |
| UC-002 | R-002 | Open reusable SSH session | Yes/N/A/Yes |
| UC-003 | R-003 | Execute command using session ID | Yes/Yes/Yes |
| UC-004 | R-004 | Close session | Yes/N/A/Yes |
| UC-005 | R-005 | Expire idle sessions | Yes/N/A/Yes |
| UC-006 | R-006 | Docker E2E lifecycle validation | Yes/N/A/Yes |
| UC-007 | R-006 | Docker E2E lifecycle (key auth) | Yes/N/A/Yes |
| UC-008 | R-006 | Docker E2E lifecycle (password auth) | Yes/N/A/Yes |

## Use Case: UC-001 [SSH command health check]

### Primary Runtime Call Stack
```text
[ENTRY] ssh-mcp/src/ssh_mcp/server.py:ssh_health_check(...)
└── ssh-mcp/src/ssh_mcp/runner.py:run_health_check(settings)
    ├── shutil.which(settings.command) [IO]
    ├── subprocess.run([ssh, ..., -V], timeout=...) [IO]
    └── _success_result(...)
```

### Error Paths
```text
[ERROR] ssh binary missing or probe execution failure
ssh-mcp/src/ssh_mcp/runner.py:run_health_check(...)
└── _error_result(error_type="config"|"execution"|"timeout")
```

### Coverage Status
- Primary Path: Covered
- Fallback Path: N/A
- Error Path: Covered

## Use Case: UC-002 [Open reusable SSH session]

### Primary Runtime Call Stack
```text
[ENTRY] ssh-mcp/src/ssh_mcp/server.py:ssh_open_session(host?, user?, port?, cwd?)
├── ssh-mcp/src/ssh_mcp/runner.py:run_open_session(...)
│   ├── config.py:resolve_target(host?) # uses SSH_MCP_DEFAULT_HOST when host omitted
│   ├── config.py:resolve_remote_cwd(...)
│   ├── runner.py:_cleanup_expired_sessions() [STATE]
│   ├── runner.py:_generate_session_id() # 8-char lowercase hex
│   ├── runner.py:_create_session_record(session_id, control_path, target, cwd) [STATE]
│   ├── runner.py:_build_open_command(...ControlMaster=yes...) 
│   ├── subprocess.run(open_command, timeout=...) [IO]
│   └── runner.py:_success_open_result(...)
└── server.py:return session metadata
```

### Error Paths
```text
[ERROR] invalid host/user/port/cwd or session cap exceeded
runner.py:run_open_session(...)
└── _error_result(error_type="validation")
```

```text
[ERROR] SSH master open fails
runner.py:_execute(...)
└── _error_result(error_type="execution"|"timeout")
```

### Coverage Status
- Primary Path: Covered
- Fallback Path: N/A
- Error Path: Covered

## Use Case: UC-003 [Execute command using session ID]

### Primary Runtime Call Stack
```text
[ENTRY] ssh-mcp/src/ssh_mcp/server.py:ssh_session_exec(session_id, command, cwd?)
├── runner.py:run_session_exec(...)
│   ├── config.py:normalize_session_id(...)
│   ├── config.py:normalize_remote_command(...)
│   ├── runner.py:_cleanup_expired_sessions() [STATE]
│   ├── runner.py:_get_session(session_id) [STATE]
│   ├── runner.py:_compose_remote_command(session.cwd/call.cwd, command)
│   ├── runner.py:_build_session_exec_command(...ControlPath=session.control_path...)
│   ├── subprocess.run(exec_command, timeout=...) [IO]
│   ├── runner.py:_touch_session_last_used(session_id) [STATE]
│   └── _success_exec_result(...)
└── server.py:return command result
```

### Branching / Fallback Paths
```text
[FALLBACK] per-call cwd override provided
runner.py:run_session_exec(...)
└── compose command with override cwd instead of session default cwd
```

### Error Paths
```text
[ERROR] unknown/expired session id
runner.py:run_session_exec(...)
└── _error_result(error_type="execution")
```

```text
[ERROR] command timeout/non-zero exit
runner.py:_execute(...)
└── _error_result(error_type="timeout"|"execution")
```

### Coverage Status
- Primary Path: Covered
- Fallback Path: Covered
- Error Path: Covered

## Use Case: UC-004 [Close session]

### Primary Runtime Call Stack
```text
[ENTRY] ssh-mcp/src/ssh_mcp/server.py:ssh_close_session(session_id)
├── runner.py:run_close_session(...)
│   ├── config.py:normalize_session_id(...)
│   ├── runner.py:_get_session(session_id) [STATE]
│   ├── runner.py:_build_close_command(... -O exit ...)
│   ├── subprocess.run(close_command, timeout=...) [IO]
│   ├── runner.py:_remove_session(session_id) [STATE]
│   └── runner.py:_cleanup_control_socket_path(...) [IO]
└── server.py:return close status
```

### Error Paths
```text
[ERROR] unknown session id
runner.py:run_close_session(...)
└── _error_result(error_type="execution")
```

### Coverage Status
- Primary Path: Covered
- Fallback Path: N/A
- Error Path: Covered

## Use Case: UC-005 [Expire idle sessions]

### Primary Runtime Call Stack
```text
[ENTRY] runner.py:run_open_session(...) or runner.py:run_session_exec(...)
└── runner.py:_cleanup_expired_sessions()
    ├── iterate session table [STATE]
    ├── compare now - last_used_at against idle timeout
    ├── for expired: run close command (-O exit) [IO]
    └── remove expired entries [STATE]
```

### Error Paths
```text
[ERROR] close command for expired session fails
runner.py:_cleanup_expired_sessions(...)
└── continue cleanup and drop local record (best-effort shutdown)
```

### Coverage Status
- Primary Path: Covered
- Fallback Path: N/A
- Error Path: Covered

## Use Case: UC-006 [Docker E2E lifecycle validation]

### Primary Runtime Call Stack
```text
[ENTRY] ssh-mcp/tests/test_e2e_docker.py:test_session_lifecycle_end_to_end_with_dockerized_sshd
├── docker build/run sshd fixture [IO]
├── MCP call: ssh_open_session(...) without host (uses default host) [ASYNC]
├── MCP call: ssh_session_exec(... "whoami") [ASYNC]
├── MCP call: ssh_session_exec(... "pwd") [ASYNC]
├── MCP call: ssh_close_session(...) [ASYNC]
└── docker rm/image cleanup [IO]
```

### Error Paths
```text
[ERROR] docker unavailable/disabled
test_e2e_docker.py:_require_docker_prerequisites(...)
└── pytest.skip(...)
```

### Coverage Status
- Primary Path: Covered
- Fallback Path: N/A
- Error Path: Covered

## Use Case: UC-007 [Docker E2E lifecycle - key auth]

### Primary Runtime Call Stack
```text
[ENTRY] test_e2e_docker.py:test_session_lifecycle_end_to_end_with_dockerized_sshd_key_auth
├── docker run sshd fixture [IO]
├── MCP call: ssh_open_session(...) [ASYNC]
├── MCP call: ssh_session_exec(...)
├── MCP call: ssh_close_session(...)
└── cleanup [IO]
```

### Coverage Status
- Primary Path: Covered
- Fallback Path: N/A
- Error Path: Covered

## Use Case: UC-008 [Docker E2E lifecycle - password auth]

### Primary Runtime Call Stack
```text
[ENTRY] test_e2e_docker.py:test_session_lifecycle_end_to_end_with_dockerized_sshd_password_auth
├── docker run sshd fixture with password auth enabled [IO]
├── runner.py:_build_execution_env(...) # SSH_ASKPASS variables from env secret
├── MCP call: ssh_open_session(...) [ASYNC]
├── MCP call: ssh_session_exec(...)
├── MCP call: ssh_close_session(...)
└── cleanup [IO]
```

### Coverage Status
- Primary Path: Covered
- Fallback Path: N/A
- Error Path: Covered
