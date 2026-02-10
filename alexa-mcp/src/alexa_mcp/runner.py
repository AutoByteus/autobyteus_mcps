from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import TypedDict

from .config import AlexaSettings, ConfigError, normalize_query


class AlexaCommandResult(TypedDict):
    ok: bool
    action: str
    command: list[str]
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    error_type: str | None
    error_message: str | None
    routine_name: str | None
    music_action: str | None
    echo_device: str | None


@dataclass(frozen=True, slots=True)
class _ExecutionSpec:
    action: str
    command: list[str]
    routine_name: str | None
    music_action: str | None
    echo_device: str | None


def run_routine(
    settings: AlexaSettings,
    routine_name: str,
    echo_device: str | None = None,
) -> AlexaCommandResult:
    device = _resolve_device(settings, echo_device)
    command = _build_command(
        settings,
        event_value=f"automation:{routine_name}",
        echo_device=device,
    )
    spec = _ExecutionSpec(
        action="run_routine",
        command=command,
        routine_name=routine_name,
        music_action=None,
        echo_device=device,
    )
    return _execute(spec, settings.timeout_seconds)


def run_music_action(
    settings: AlexaSettings,
    action: str,
    query: str | None = None,
    echo_device: str | None = None,
) -> AlexaCommandResult:
    device = _resolve_device(settings, echo_device)
    normalized_action = action.lower()

    if normalized_action == "play" and settings.music_play_routine:
        return run_routine(settings, settings.music_play_routine, device)
    if normalized_action == "stop" and settings.music_stop_routine:
        return run_routine(settings, settings.music_stop_routine, device)

    if normalized_action == "play":
        if query is None:
            raise ConfigError("query is required when action is 'play' without a play routine override.")
        clean_query = normalize_query(query, settings.max_query_length)
        event_value = f"textcommand:play {clean_query}"
    elif normalized_action == "stop":
        event_value = "textcommand:stop"
    else:
        raise ConfigError(f"Unsupported music action '{action}'.")

    command = _build_command(settings, event_value=event_value, echo_device=device)
    spec = _ExecutionSpec(
        action="music_control",
        command=command,
        routine_name=None,
        music_action=normalized_action,
        echo_device=device,
    )
    return _execute(spec, settings.timeout_seconds)


def run_device_status(
    settings: AlexaSettings,
    echo_device: str | None = None,
) -> AlexaCommandResult:
    device = _resolve_device(settings, echo_device)
    command = _build_passthrough_command(settings, extra_args=["-q"], echo_device=device)
    spec = _ExecutionSpec(
        action="device_status",
        command=command,
        routine_name=None,
        music_action=None,
        echo_device=device,
    )
    return _execute(spec, settings.timeout_seconds)


def run_health_check(settings: AlexaSettings) -> AlexaCommandResult:
    if _resolve_command_path(settings.command) is None:
        return _error_result(
            action="health_check",
            command=[settings.command],
            error_type="config",
            error_message=f"Adapter command '{settings.command}' was not found.",
            routine_name=None,
            music_action=None,
            echo_device=None,
        )

    if not settings.health_check_args:
        return _success_result(
            action="health_check",
            command=[settings.command],
            stdout="command available",
            stderr=None,
            exit_code=0,
            routine_name=None,
            music_action=None,
            echo_device=None,
        )

    command = [settings.command, *settings.base_args, *settings.health_check_args]
    spec = _ExecutionSpec(
        action="health_check",
        command=command,
        routine_name=None,
        music_action=None,
        echo_device=None,
    )
    return _execute(spec, settings.timeout_seconds)


def _execute(spec: _ExecutionSpec, timeout_seconds: int) -> AlexaCommandResult:
    try:
        completed = subprocess.run(
            spec.command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return _error_result(
            action=spec.action,
            command=spec.command,
            error_type="config",
            error_message=f"Command '{spec.command[0]}' was not found.",
            routine_name=spec.routine_name,
            music_action=spec.music_action,
            echo_device=spec.echo_device,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.output if isinstance(exc.output, str) else None
        stderr = exc.stderr if isinstance(exc.stderr, str) else None
        return _error_result(
            action=spec.action,
            command=spec.command,
            error_type="timeout",
            error_message=f"Command timed out after {timeout_seconds} seconds.",
            routine_name=spec.routine_name,
            music_action=spec.music_action,
            echo_device=spec.echo_device,
            stdout=stdout,
            stderr=stderr,
        )
    except OSError as exc:
        return _error_result(
            action=spec.action,
            command=spec.command,
            error_type="execution",
            error_message=f"Failed to execute command: {exc}",
            routine_name=spec.routine_name,
            music_action=spec.music_action,
            echo_device=spec.echo_device,
        )

    if completed.returncode != 0:
        return _error_result(
            action=spec.action,
            command=spec.command,
            error_type="execution",
            error_message=f"Command exited with status {completed.returncode}.",
            routine_name=spec.routine_name,
            music_action=spec.music_action,
            echo_device=spec.echo_device,
            stdout=_normalize_output(completed.stdout),
            stderr=_normalize_output(completed.stderr),
            exit_code=completed.returncode,
        )

    return _success_result(
        action=spec.action,
        command=spec.command,
        stdout=_normalize_output(completed.stdout),
        stderr=_normalize_output(completed.stderr),
        exit_code=completed.returncode,
        routine_name=spec.routine_name,
        music_action=spec.music_action,
        echo_device=spec.echo_device,
    )


def _build_command(settings: AlexaSettings, event_value: str, echo_device: str | None) -> list[str]:
    return _build_passthrough_command(
        settings,
        extra_args=[settings.event_flag, event_value],
        echo_device=echo_device,
    )


def _build_passthrough_command(
    settings: AlexaSettings,
    extra_args: list[str],
    echo_device: str | None,
) -> list[str]:
    command = [settings.command, *settings.base_args]
    if echo_device:
        command.extend([settings.device_flag, echo_device])
    command.extend(extra_args)
    return command


def _resolve_device(settings: AlexaSettings, echo_device: str | None) -> str | None:
    if echo_device is None:
        return settings.default_device
    stripped = echo_device.strip()
    return stripped if stripped else settings.default_device


def _resolve_command_path(command: str) -> str | None:
    command_path = Path(command)
    if command_path.is_absolute() or "/" in command:
        if command_path.exists():
            return str(command_path)
        return None
    return shutil.which(command)


def _normalize_output(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _success_result(
    action: str,
    command: list[str],
    stdout: str | None,
    stderr: str | None,
    exit_code: int | None,
    routine_name: str | None,
    music_action: str | None,
    echo_device: str | None,
) -> AlexaCommandResult:
    return AlexaCommandResult(
        ok=True,
        action=action,
        command=command,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        error_type=None,
        error_message=None,
        routine_name=routine_name,
        music_action=music_action,
        echo_device=echo_device,
    )


def _error_result(
    action: str,
    command: list[str],
    error_type: str,
    error_message: str,
    routine_name: str | None,
    music_action: str | None,
    echo_device: str | None,
    stdout: str | None = None,
    stderr: str | None = None,
    exit_code: int | None = None,
) -> AlexaCommandResult:
    return AlexaCommandResult(
        ok=False,
        action=action,
        command=command,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        error_type=error_type,
        error_message=error_message,
        routine_name=routine_name,
        music_action=music_action,
        echo_device=echo_device,
    )
