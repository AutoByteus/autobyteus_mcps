from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from typing import TypedDict

from .config import (
    ConfigError,
    SshSettings,
    normalize_remote_command,
    normalize_session_id,
    resolve_password,
    resolve_remote_cwd,
    resolve_target,
)


class SshToolResult(TypedDict):
    ok: bool
    action: str
    command: list[str]
    session_id: str | None
    destination: str | None
    host: str | None
    user: str | None
    port: int | None
    remote_command: str | None
    cwd: str | None
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    duration_ms: int | None
    error_type: str | None
    error_message: str | None
    session_count: int | None
    created_at: float | None
    last_used_at: float | None


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    destination: str
    host: str
    user: str | None
    port: int | None
    default_cwd: str | None
    control_path: str
    created_at: float
    last_used_at: float


class SessionManager:
    def __init__(self, session_dir: str | None = None) -> None:
        short_tmp_dir = Path("/tmp")
        if session_dir is None:
            self._root_dir = Path(tempfile.mkdtemp(prefix="sshmcp-", dir=str(short_tmp_dir)))
        else:
            self._root_dir = Path(session_dir)
            self._root_dir.mkdir(parents=True, exist_ok=True)

        self._fallback_socket_dir = short_tmp_dir / "ssh-mcp-sockets"
        self._fallback_socket_dir.mkdir(parents=True, exist_ok=True)
        self._askpass_script_path = self._root_dir / "ssh-askpass.sh"

        self._lock = threading.Lock()
        self._sessions: dict[str, SessionRecord] = {}

    @property
    def root_dir(self) -> str:
        return str(self._root_dir)

    def control_path_for(self, session_id: str) -> str:
        socket_name = f"s-{session_id}.sock"
        preferred = str(self._root_dir / socket_name)
        if len(preferred) <= 100:
            return preferred

        fallback = str(self._fallback_socket_dir / socket_name)
        if len(fallback) <= 100:
            return fallback

        raise ConfigError("Unable to allocate a valid SSH control socket path within length limits.")

    def askpass_script_path(self) -> str:
        return str(self._askpass_script_path)

    def ensure_capacity(self, max_sessions: int) -> None:
        with self._lock:
            if len(self._sessions) >= max_sessions:
                raise ConfigError(
                    f"Session limit reached ({max_sessions}). Close a session before opening a new one."
                )

    def add(self, record: SessionRecord, max_sessions: int) -> None:
        with self._lock:
            if len(self._sessions) >= max_sessions:
                raise ConfigError(
                    f"Session limit reached ({max_sessions}). Close a session before opening a new one."
                )
            self._sessions[record.session_id] = record

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)

    def pop(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.pop(session_id, None)

    def touch(self, session_id: str, used_at: float) -> SessionRecord | None:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            record.last_used_at = used_at
            return record

    def remove_expired(self, idle_timeout_seconds: int, now: float) -> list[SessionRecord]:
        with self._lock:
            expired_ids = [
                session_id
                for session_id, record in self._sessions.items()
                if now - record.last_used_at >= idle_timeout_seconds
            ]
            return [self._sessions.pop(session_id) for session_id in expired_ids]

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


@dataclass(frozen=True, slots=True)
class _ExecutionSpec:
    action: str
    command: list[str]
    session_id: str | None
    destination: str | None
    host: str | None
    user: str | None
    port: int | None
    remote_command: str | None
    cwd: str | None
    created_at: float | None
    last_used_at: float | None
    env: dict[str, str] | None


def create_session_manager(settings: SshSettings) -> SessionManager:
    return SessionManager(session_dir=settings.session_dir)


def run_health_check(settings: SshSettings) -> SshToolResult:
    if shutil.which(settings.command) is None:
        return _error_result(
            action="health_check",
            command=[settings.command],
            session_id=None,
            destination=None,
            host=None,
            user=None,
            port=None,
            remote_command=None,
            cwd=None,
            created_at=None,
            last_used_at=None,
            error_type="config",
            error_message=f"SSH command '{settings.command}' was not found.",
            session_count=None,
        )

    command = [settings.command, *settings.base_args, *settings.health_check_args]
    spec = _ExecutionSpec(
        action="health_check",
        command=command,
        session_id=None,
        destination=None,
        host=None,
        user=None,
        port=None,
        remote_command=None,
        cwd=None,
        created_at=None,
        last_used_at=None,
        env=None,
    )
    return _execute(spec=spec, timeout_seconds=settings.timeout_seconds, max_output_chars=settings.max_output_chars)


def run_open_session(
    settings: SshSettings,
    manager: SessionManager,
    host: str | None = None,
    user: str | None = None,
    port: int | None = None,
    cwd: str | None = None,
) -> SshToolResult:
    _cleanup_expired_sessions(settings=settings, manager=manager)

    try:
        target = resolve_target(settings=settings, host=host, user=user, port=port)
        normalized_cwd = resolve_remote_cwd(cwd)
        manager.ensure_capacity(settings.max_sessions)
        execution_env = _build_execution_env(settings=settings, manager=manager)
    except ConfigError as exc:
        return _error_result(
            action="open_session",
            command=[settings.command],
            session_id=None,
            destination=None,
            host=host.strip() if host else settings.default_host,
            user=user.strip() if user else None,
            port=port,
            remote_command=None,
            cwd=cwd.strip() if cwd else None,
            created_at=None,
            last_used_at=None,
            error_type="validation",
            error_message=str(exc),
            session_count=manager.count(),
        )

    session_id = _generate_session_id(manager)
    control_path = manager.control_path_for(session_id)
    password_auth_enabled = execution_env is not None

    open_command = _build_open_command(
        settings=settings,
        destination=target.destination,
        port=target.port,
        control_path=control_path,
        password_auth_enabled=password_auth_enabled,
    )
    spec = _ExecutionSpec(
        action="open_session",
        command=open_command,
        session_id=session_id,
        destination=target.destination,
        host=target.host,
        user=target.user,
        port=target.port,
        remote_command=None,
        cwd=normalized_cwd,
        created_at=None,
        last_used_at=None,
        env=execution_env,
    )
    open_result = _execute(spec=spec, timeout_seconds=settings.timeout_seconds, max_output_chars=settings.max_output_chars)
    if not open_result["ok"]:
        open_result["session_count"] = manager.count()
        return open_result

    now = time.time()
    record = SessionRecord(
        session_id=session_id,
        destination=target.destination,
        host=target.host,
        user=target.user,
        port=target.port,
        default_cwd=normalized_cwd,
        control_path=control_path,
        created_at=now,
        last_used_at=now,
    )

    try:
        manager.add(record, settings.max_sessions)
    except ConfigError as exc:
        _best_effort_close_control_master(settings=settings, record=record)
        _safe_unlink(record.control_path)
        return _error_result(
            action="open_session",
            command=open_command,
            session_id=session_id,
            destination=target.destination,
            host=target.host,
            user=target.user,
            port=target.port,
            remote_command=None,
            cwd=normalized_cwd,
            created_at=now,
            last_used_at=now,
            error_type="validation",
            error_message=str(exc),
            session_count=manager.count(),
        )

    return SshToolResult(
        ok=True,
        action="open_session",
        command=open_command,
        session_id=session_id,
        destination=target.destination,
        host=target.host,
        user=target.user,
        port=target.port,
        remote_command=None,
        cwd=normalized_cwd,
        stdout=open_result["stdout"],
        stderr=open_result["stderr"],
        exit_code=open_result["exit_code"],
        duration_ms=open_result["duration_ms"],
        error_type=None,
        error_message=None,
        session_count=manager.count(),
        created_at=now,
        last_used_at=now,
    )


def run_session_exec(
    settings: SshSettings,
    manager: SessionManager,
    session_id: str,
    command: str,
    cwd: str | None = None,
) -> SshToolResult:
    _cleanup_expired_sessions(settings=settings, manager=manager)

    try:
        normalized_session_id = normalize_session_id(session_id)
        normalized_command = normalize_remote_command(command, max_chars=settings.max_command_chars)
        normalized_cwd = resolve_remote_cwd(cwd)
        execution_env = _build_execution_env(settings=settings, manager=manager)
    except ConfigError as exc:
        return _error_result(
            action="session_exec",
            command=[settings.command],
            session_id=session_id.strip().lower() if session_id else None,
            destination=None,
            host=None,
            user=None,
            port=None,
            remote_command=None,
            cwd=cwd.strip() if cwd else None,
            created_at=None,
            last_used_at=None,
            error_type="validation",
            error_message=str(exc),
            session_count=manager.count(),
        )

    record = manager.get(normalized_session_id)
    if record is None:
        return _error_result(
            action="session_exec",
            command=[settings.command],
            session_id=normalized_session_id,
            destination=None,
            host=None,
            user=None,
            port=None,
            remote_command=None,
            cwd=normalized_cwd,
            created_at=None,
            last_used_at=None,
            error_type="execution",
            error_message=f"Session '{normalized_session_id}' was not found or has expired.",
            session_count=manager.count(),
        )

    effective_cwd = normalized_cwd if normalized_cwd is not None else record.default_cwd
    remote_command = _compose_remote_command(command=normalized_command, cwd=effective_cwd)
    exec_command = _build_session_exec_command(
        settings=settings,
        record=record,
        remote_command=remote_command,
    )
    spec = _ExecutionSpec(
        action="session_exec",
        command=exec_command,
        session_id=record.session_id,
        destination=record.destination,
        host=record.host,
        user=record.user,
        port=record.port,
        remote_command=remote_command,
        cwd=effective_cwd,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        env=execution_env,
    )
    result = _execute(spec=spec, timeout_seconds=settings.timeout_seconds, max_output_chars=settings.max_output_chars)

    touched = manager.touch(record.session_id, time.time())
    if touched is not None:
        result["last_used_at"] = touched.last_used_at
    result["session_count"] = manager.count()
    return result


def run_close_session(
    settings: SshSettings,
    manager: SessionManager,
    session_id: str,
) -> SshToolResult:
    _cleanup_expired_sessions(settings=settings, manager=manager)

    try:
        normalized_session_id = normalize_session_id(session_id)
    except ConfigError as exc:
        return _error_result(
            action="close_session",
            command=[settings.command],
            session_id=session_id.strip().lower() if session_id else None,
            destination=None,
            host=None,
            user=None,
            port=None,
            remote_command=None,
            cwd=None,
            created_at=None,
            last_used_at=None,
            error_type="validation",
            error_message=str(exc),
            session_count=manager.count(),
        )

    record = manager.pop(normalized_session_id)
    if record is None:
        return _error_result(
            action="close_session",
            command=[settings.command],
            session_id=normalized_session_id,
            destination=None,
            host=None,
            user=None,
            port=None,
            remote_command=None,
            cwd=None,
            created_at=None,
            last_used_at=None,
            error_type="execution",
            error_message=f"Session '{normalized_session_id}' was not found or has already been closed.",
            session_count=manager.count(),
        )

    close_command = _build_close_command(settings=settings, record=record)
    spec = _ExecutionSpec(
        action="close_session",
        command=close_command,
        session_id=record.session_id,
        destination=record.destination,
        host=record.host,
        user=record.user,
        port=record.port,
        remote_command=None,
        cwd=record.default_cwd,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        env=None,
    )
    result = _execute(spec=spec, timeout_seconds=settings.timeout_seconds, max_output_chars=settings.max_output_chars)
    _safe_unlink(record.control_path)
    result["session_count"] = manager.count()
    return result


def _cleanup_expired_sessions(settings: SshSettings, manager: SessionManager) -> None:
    now = time.time()
    expired = manager.remove_expired(settings.session_idle_timeout_seconds, now)
    for record in expired:
        _best_effort_close_control_master(settings=settings, record=record)
        _safe_unlink(record.control_path)


def _build_open_command(
    settings: SshSettings,
    destination: str,
    port: int | None,
    control_path: str,
    password_auth_enabled: bool,
) -> list[str]:
    command = [settings.command, *settings.base_args]
    if port is not None:
        command.extend(["-p", str(port)])
    command.extend(
        [
            "-o",
            "ControlMaster=yes",
            "-o",
            f"ControlPath={control_path}",
            "-o",
            f"ControlPersist={settings.session_idle_timeout_seconds}",
        ]
    )
    if password_auth_enabled:
        command.extend(
            [
                "-o",
                "BatchMode=no",
                "-o",
                "PubkeyAuthentication=no",
                "-o",
                "PreferredAuthentications=password,keyboard-interactive",
            ]
        )
    command.extend([destination, "--", "echo __ssh_mcp_session_opened__"])
    return command


def _build_session_exec_command(
    settings: SshSettings,
    record: SessionRecord,
    remote_command: str,
) -> list[str]:
    command = [settings.command, *settings.base_args]
    if record.port is not None:
        command.extend(["-p", str(record.port)])
    command.extend(
        [
            "-o",
            "ControlMaster=no",
            "-o",
            f"ControlPath={record.control_path}",
            record.destination,
            "--",
            remote_command,
        ]
    )
    return command


def _build_close_command(settings: SshSettings, record: SessionRecord) -> list[str]:
    command = [settings.command, *settings.base_args]
    if record.port is not None:
        command.extend(["-p", str(record.port)])
    command.extend(
        [
            "-o",
            f"ControlPath={record.control_path}",
            "-O",
            "exit",
            record.destination,
        ]
    )
    return command


def _build_execution_env(settings: SshSettings, manager: SessionManager) -> dict[str, str] | None:
    password = resolve_password(settings)
    if password is None:
        return None

    askpass_path = _ensure_askpass_script(manager.askpass_script_path())
    env = dict(os.environ)
    env["SSH_ASKPASS"] = askpass_path
    env["SSH_ASKPASS_REQUIRE"] = "force"
    env["DISPLAY"] = env.get("DISPLAY", ":0")
    env["SSH_MCP_TOOL_PASSWORD"] = password
    return env


def _ensure_askpass_script(path: str) -> str:
    script = Path(path)
    if not script.exists():
        script.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$SSH_MCP_TOOL_PASSWORD\"\n",
            encoding="utf-8",
        )
        script.chmod(0o700)
    return str(script)


def _generate_session_id(manager: SessionManager) -> str:
    for _ in range(50):
        candidate = secrets.token_hex(4)
        if manager.get(candidate) is None:
            return candidate
    raise ConfigError("Failed to allocate a unique session_id.")


def _compose_remote_command(command: str, cwd: str | None) -> str:
    if cwd is None:
        return command
    return f"cd {shlex.quote(cwd)} && {command}"


def _best_effort_close_control_master(settings: SshSettings, record: SessionRecord) -> None:
    try:
        subprocess.run(
            _build_close_command(settings=settings, record=record),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=settings.timeout_seconds,
            check=False,
        )
    except Exception:
        return


def _safe_unlink(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        return


def _execute(spec: _ExecutionSpec, timeout_seconds: int, max_output_chars: int) -> SshToolResult:
    started_at = time.monotonic()
    try:
        completed = subprocess.run(
            spec.command,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=spec.env,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return _error_result(
            action=spec.action,
            command=spec.command,
            session_id=spec.session_id,
            destination=spec.destination,
            host=spec.host,
            user=spec.user,
            port=spec.port,
            remote_command=spec.remote_command,
            cwd=spec.cwd,
            created_at=spec.created_at,
            last_used_at=spec.last_used_at,
            error_type="config",
            error_message=f"Command '{spec.command[0]}' was not found.",
            duration_ms=_duration_ms(started_at),
            session_count=None,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.output if isinstance(exc.output, str) else None
        stderr = exc.stderr if isinstance(exc.stderr, str) else None
        return _error_result(
            action=spec.action,
            command=spec.command,
            session_id=spec.session_id,
            destination=spec.destination,
            host=spec.host,
            user=spec.user,
            port=spec.port,
            remote_command=spec.remote_command,
            cwd=spec.cwd,
            created_at=spec.created_at,
            last_used_at=spec.last_used_at,
            error_type="timeout",
            error_message=f"Command timed out after {timeout_seconds} seconds.",
            stdout=_normalize_output(stdout, max_output_chars),
            stderr=_normalize_output(stderr, max_output_chars),
            duration_ms=_duration_ms(started_at),
            session_count=None,
        )
    except OSError as exc:
        return _error_result(
            action=spec.action,
            command=spec.command,
            session_id=spec.session_id,
            destination=spec.destination,
            host=spec.host,
            user=spec.user,
            port=spec.port,
            remote_command=spec.remote_command,
            cwd=spec.cwd,
            created_at=spec.created_at,
            last_used_at=spec.last_used_at,
            error_type="execution",
            error_message=f"Failed to execute command: {exc}",
            duration_ms=_duration_ms(started_at),
            session_count=None,
        )

    stdout = _normalize_output(completed.stdout, max_output_chars)
    stderr = _normalize_output(completed.stderr, max_output_chars)
    duration_ms = _duration_ms(started_at)

    if completed.returncode != 0:
        return _error_result(
            action=spec.action,
            command=spec.command,
            session_id=spec.session_id,
            destination=spec.destination,
            host=spec.host,
            user=spec.user,
            port=spec.port,
            remote_command=spec.remote_command,
            cwd=spec.cwd,
            created_at=spec.created_at,
            last_used_at=spec.last_used_at,
            error_type="execution",
            error_message=f"Command exited with status {completed.returncode}.",
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            session_count=None,
        )

    return SshToolResult(
        ok=True,
        action=spec.action,
        command=spec.command,
        session_id=spec.session_id,
        destination=spec.destination,
        host=spec.host,
        user=spec.user,
        port=spec.port,
        remote_command=spec.remote_command,
        cwd=spec.cwd,
        stdout=stdout,
        stderr=stderr,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        error_type=None,
        error_message=None,
        session_count=None,
        created_at=spec.created_at,
        last_used_at=spec.last_used_at,
    )


def _duration_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def _normalize_output(value: str | None, max_output_chars: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) <= max_output_chars:
        return normalized
    return normalized[:max_output_chars] + f"\n...[truncated to {max_output_chars} chars]"


def _error_result(
    action: str,
    command: list[str],
    session_id: str | None,
    destination: str | None,
    host: str | None,
    user: str | None,
    port: int | None,
    remote_command: str | None,
    cwd: str | None,
    created_at: float | None,
    last_used_at: float | None,
    error_type: str,
    error_message: str,
    stdout: str | None = None,
    stderr: str | None = None,
    exit_code: int | None = None,
    duration_ms: int | None = None,
    session_count: int | None = None,
) -> SshToolResult:
    return SshToolResult(
        ok=False,
        action=action,
        command=command,
        session_id=session_id,
        destination=destination,
        host=host,
        user=user,
        port=port,
        remote_command=remote_command,
        cwd=cwd,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=duration_ms,
        error_type=error_type,
        error_message=error_message,
        session_count=session_count,
        created_at=created_at,
        last_used_at=last_used_at,
    )
