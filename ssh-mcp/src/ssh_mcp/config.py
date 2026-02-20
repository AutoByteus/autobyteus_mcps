from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
from typing import Mapping

DEFAULT_SERVER_NAME = "ssh-mcp"
DEFAULT_INSTRUCTIONS = (
    "Expose bounded SSH lifecycle tools for remote command execution. "
    "Open sessions explicitly, run commands by session id, and close sessions."
)
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_SESSION_ID_PATTERN = re.compile(r"^[a-f0-9]{8}$")


class ConfigError(ValueError):
    """Raised when SSH MCP configuration or input is invalid."""


@dataclass(frozen=True, slots=True)
class SshSettings:
    command: str
    base_args: tuple[str, ...]
    timeout_seconds: int
    allowed_hosts: tuple[str, ...]
    default_host: str | None
    default_user: str | None
    default_port: int | None
    max_command_chars: int
    max_output_chars: int
    health_check_args: tuple[str, ...]
    password: str | None
    password_file: str | None
    session_idle_timeout_seconds: int
    max_sessions: int
    session_dir: str | None


@dataclass(frozen=True, slots=True)
class ServerConfig:
    name: str = DEFAULT_SERVER_NAME
    instructions: str = DEFAULT_INSTRUCTIONS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ServerConfig":
        actual_env = env if env is not None else os.environ
        return cls(
            name=actual_env.get("SSH_MCP_NAME", DEFAULT_SERVER_NAME),
            instructions=actual_env.get("SSH_MCP_INSTRUCTIONS", DEFAULT_INSTRUCTIONS),
        )


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    host: str
    user: str | None
    port: int | None
    destination: str


def load_settings(env: Mapping[str, str] | None = None) -> SshSettings:
    actual_env = env if env is not None else os.environ

    command = _require_non_empty(actual_env, "SSH_MCP_COMMAND", default="ssh")
    base_args = tuple(_parse_shell_args(actual_env.get("SSH_MCP_BASE_ARGS", "")))
    timeout_seconds = _parse_positive_int(
        actual_env.get("SSH_MCP_TIMEOUT_SECONDS", "60"),
        "SSH_MCP_TIMEOUT_SECONDS",
    )
    allowed_hosts = tuple(_parse_allowed_hosts(actual_env.get("SSH_MCP_ALLOWED_HOSTS", "")))
    default_host = _parse_optional_host(actual_env.get("SSH_MCP_DEFAULT_HOST"), "SSH_MCP_DEFAULT_HOST")
    default_user = _parse_optional_identifier(actual_env.get("SSH_MCP_DEFAULT_USER"), "SSH_MCP_DEFAULT_USER")
    default_port = _parse_optional_port(actual_env.get("SSH_MCP_DEFAULT_PORT"), "SSH_MCP_DEFAULT_PORT")
    max_command_chars = _parse_positive_int(
        actual_env.get("SSH_MCP_MAX_COMMAND_CHARS", "4000"),
        "SSH_MCP_MAX_COMMAND_CHARS",
    )
    max_output_chars = _parse_positive_int(
        actual_env.get("SSH_MCP_MAX_OUTPUT_CHARS", "20000"),
        "SSH_MCP_MAX_OUTPUT_CHARS",
    )
    health_check_args = tuple(_parse_shell_args(actual_env.get("SSH_MCP_HEALTH_CHECK_ARGS", "-V")))
    password = _parse_optional_secret(actual_env.get("SSH_MCP_PASSWORD"), "SSH_MCP_PASSWORD")
    password_file = _parse_optional_file(actual_env.get("SSH_MCP_PASSWORD_FILE"), "SSH_MCP_PASSWORD_FILE")
    if password is not None and password_file is not None:
        raise ConfigError("Set either SSH_MCP_PASSWORD or SSH_MCP_PASSWORD_FILE, not both.")
    session_idle_timeout_seconds = _parse_positive_int(
        actual_env.get("SSH_MCP_SESSION_IDLE_TIMEOUT_SECONDS", "300"),
        "SSH_MCP_SESSION_IDLE_TIMEOUT_SECONDS",
    )
    max_sessions = _parse_positive_int(
        actual_env.get("SSH_MCP_MAX_SESSIONS", "32"),
        "SSH_MCP_MAX_SESSIONS",
    )
    session_dir = _parse_optional_dir(actual_env.get("SSH_MCP_SESSION_DIR"), "SSH_MCP_SESSION_DIR")

    return SshSettings(
        command=command,
        base_args=base_args,
        timeout_seconds=timeout_seconds,
        allowed_hosts=allowed_hosts,
        default_host=default_host,
        default_user=default_user,
        default_port=default_port,
        max_command_chars=max_command_chars,
        max_output_chars=max_output_chars,
        health_check_args=health_check_args,
        password=password,
        password_file=password_file,
        session_idle_timeout_seconds=session_idle_timeout_seconds,
        max_sessions=max_sessions,
        session_dir=session_dir,
    )


def resolve_target(
    settings: SshSettings,
    host: str | None,
    user: str | None,
    port: int | None,
) -> ResolvedTarget:
    if host is None or not host.strip():
        if settings.default_host is None:
            raise ConfigError("host is required when SSH_MCP_DEFAULT_HOST is not set.")
        normalized_host = settings.default_host
    else:
        normalized_host = normalize_host(host)
    normalized_user = normalize_optional_identifier(user, field_name="user")
    resolved_user = normalized_user or settings.default_user
    resolved_port = settings.default_port if port is None else normalize_port(port, field_name="port")

    if settings.allowed_hosts and normalized_host not in settings.allowed_hosts:
        allowed = ", ".join(settings.allowed_hosts)
        raise ConfigError(
            f"Host '{normalized_host}' is not allowlisted. Allowed hosts: {allowed}."
        )

    destination = f"{resolved_user}@{normalized_host}" if resolved_user is not None else normalized_host
    return ResolvedTarget(
        host=normalized_host,
        user=resolved_user,
        port=resolved_port,
        destination=destination,
    )


def normalize_host(raw_value: str) -> str:
    return normalize_identifier(raw_value, field_name="host")


def normalize_optional_identifier(raw_value: str | None, field_name: str) -> str | None:
    if raw_value is None:
        return None
    stripped = raw_value.strip()
    if not stripped:
        return None
    return normalize_identifier(stripped, field_name=field_name)


def normalize_identifier(raw_value: str, field_name: str) -> str:
    value = raw_value.strip()
    if not value:
        raise ConfigError(f"{field_name} cannot be empty.")
    if "\n" in value or "\r" in value:
        raise ConfigError(f"{field_name} cannot contain newline characters.")
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ConfigError(
            f"{field_name} contains invalid characters. "
            "Allowed characters: letters, digits, dot, underscore, hyphen."
        )
    return value


def normalize_port(raw_value: int, field_name: str = "port") -> int:
    if not isinstance(raw_value, int):
        raise ConfigError(f"{field_name} must be an integer.")
    if raw_value < 1 or raw_value > 65535:
        raise ConfigError(f"{field_name} must be between 1 and 65535.")
    return raw_value


def normalize_session_id(raw_value: str) -> str:
    value = raw_value.strip().lower()
    if not value:
        raise ConfigError("session_id cannot be empty.")
    if "\n" in value or "\r" in value:
        raise ConfigError("session_id cannot contain newline characters.")
    if not _SESSION_ID_PATTERN.fullmatch(value):
        raise ConfigError("session_id format is invalid (expected 8 lowercase hex characters).")
    return value


def normalize_remote_command(raw_command: str, max_chars: int) -> str:
    command = raw_command.strip()
    if not command:
        raise ConfigError("command cannot be empty.")
    if "\n" in command or "\r" in command:
        raise ConfigError("command cannot contain newline characters.")
    if len(command) > max_chars:
        raise ConfigError(f"command length exceeds maximum of {max_chars} characters.")
    return command


def resolve_password(settings: SshSettings) -> str | None:
    if settings.password is not None:
        return settings.password
    if settings.password_file is None:
        return None

    file_path = Path(settings.password_file)
    try:
        secret = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read SSH_MCP_PASSWORD_FILE: {file_path}") from exc

    value = secret.rstrip("\n")
    if not value:
        raise ConfigError("SSH_MCP_PASSWORD_FILE is empty.")
    if "\r" in value:
        raise ConfigError("SSH_MCP_PASSWORD_FILE contains carriage-return characters.")
    return value


def resolve_remote_cwd(raw_cwd: str | None) -> str | None:
    if raw_cwd is None:
        return None
    cwd = raw_cwd.strip()
    if not cwd:
        return None
    if "\n" in cwd or "\r" in cwd:
        raise ConfigError("cwd cannot contain newline characters.")
    return cwd


def _parse_allowed_hosts(raw: str) -> list[str]:
    hosts: list[str] = []
    for item in _parse_csv(raw):
        value = item.strip()
        if not _HOST_PATTERN.fullmatch(value):
            raise ConfigError(
                "SSH_MCP_ALLOWED_HOSTS contains an invalid host entry. "
                f"Received: {value}"
            )
        hosts.append(value)
    return hosts


def _parse_optional_dir(raw: str | None, field_name: str) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if "\n" in value or "\r" in value:
        raise ConfigError(f"{field_name} cannot contain newline characters.")
    resolved = Path(value).expanduser().resolve()
    return str(resolved)


def _require_non_empty(env: Mapping[str, str], key: str, default: str | None = None) -> str:
    raw = env.get(key, default or "")
    value = raw.strip()
    if not value:
        raise ConfigError(f"{key} is required and must be non-empty.")
    return value


def _parse_shell_args(raw: str) -> list[str]:
    stripped = raw.strip()
    if not stripped:
        return []
    return shlex.split(stripped)


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_positive_int(raw: str, field_name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{field_name} must be an integer.") from exc
    if value <= 0:
        raise ConfigError(f"{field_name} must be greater than zero.")
    return value


def _parse_optional_identifier(raw: str | None, field_name: str) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return normalize_identifier(value, field_name)


def _parse_optional_host(raw: str | None, field_name: str) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if "\n" in value or "\r" in value:
        raise ConfigError(f"{field_name} cannot contain newline characters.")
    if not _HOST_PATTERN.fullmatch(value):
        raise ConfigError(
            f"{field_name} contains invalid characters. "
            "Allowed characters: letters, digits, dot, underscore, hyphen."
        )
    return value


def _parse_optional_secret(raw: str | None, field_name: str) -> str | None:
    if raw is None:
        return None
    if "\r" in raw:
        raise ConfigError(f"{field_name} cannot contain carriage-return characters.")
    value = raw.rstrip("\n")
    if not value:
        return None
    return value


def _parse_optional_file(raw: str | None, field_name: str) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if "\n" in value or "\r" in value:
        raise ConfigError(f"{field_name} cannot contain newline characters.")
    return str(Path(value).expanduser().resolve())


def _parse_optional_port(raw: str | None, field_name: str) -> int | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{field_name} must be an integer.") from exc
    return normalize_port(parsed, field_name)
