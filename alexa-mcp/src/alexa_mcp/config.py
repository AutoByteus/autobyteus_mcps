from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
from typing import Mapping

DEFAULT_SERVER_NAME = "alexa-mcp"
DEFAULT_INSTRUCTIONS = (
    "Expose bounded Alexa routine and music control tools through a local adapter command. "
    "Reject unallowlisted routines and invalid actions."
)


class ConfigError(ValueError):
    """Raised when Alexa MCP configuration is invalid."""


@dataclass(frozen=True, slots=True)
class AlexaSettings:
    command: str
    base_args: tuple[str, ...]
    event_flag: str
    device_flag: str
    default_device: str | None
    allowed_routines: frozenset[str]
    allowed_music_actions: frozenset[str]
    timeout_seconds: int
    health_check_args: tuple[str, ...]
    music_play_routine: str | None
    music_stop_routine: str | None
    max_query_length: int


@dataclass(frozen=True, slots=True)
class ServerConfig:
    name: str = DEFAULT_SERVER_NAME
    instructions: str = DEFAULT_INSTRUCTIONS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ServerConfig":
        actual_env = env if env is not None else os.environ
        return cls(
            name=actual_env.get("ALEXA_MCP_NAME", DEFAULT_SERVER_NAME),
            instructions=actual_env.get("ALEXA_MCP_INSTRUCTIONS", DEFAULT_INSTRUCTIONS),
        )


def load_settings(env: Mapping[str, str] | None = None) -> AlexaSettings:
    actual_env = env if env is not None else os.environ

    command = _require_non_empty(actual_env, "ALEXA_COMMAND")
    base_args = tuple(_parse_shell_args(actual_env.get("ALEXA_COMMAND_BASE_ARGS", "")))
    event_flag = actual_env.get("ALEXA_EVENT_FLAG", "-e").strip() or "-e"
    device_flag = actual_env.get("ALEXA_DEVICE_FLAG", "-d").strip() or "-d"
    default_device = _normalize_optional_text(actual_env.get("ALEXA_DEFAULT_DEVICE"))

    allowed_routines = frozenset(_parse_csv(actual_env.get("ALEXA_ALLOWED_ROUTINES", "")))
    if not allowed_routines:
        raise ConfigError("ALEXA_ALLOWED_ROUTINES must include at least one routine name.")

    allowed_music_actions = frozenset(
        _parse_csv(actual_env.get("ALEXA_ALLOWED_MUSIC_ACTIONS", "play,stop"))
    )
    if not allowed_music_actions:
        raise ConfigError("ALEXA_ALLOWED_MUSIC_ACTIONS cannot be empty.")

    timeout_seconds = _parse_positive_int(actual_env.get("ALEXA_TIMEOUT_SECONDS", "20"), "ALEXA_TIMEOUT_SECONDS")
    health_check_args = tuple(_parse_shell_args(actual_env.get("ALEXA_HEALTH_CHECK_ARGS", "")))
    music_play_routine = _normalize_optional_text(actual_env.get("ALEXA_MUSIC_PLAY_ROUTINE"))
    music_stop_routine = _normalize_optional_text(actual_env.get("ALEXA_MUSIC_STOP_ROUTINE"))
    max_query_length = _parse_positive_int(
        actual_env.get("ALEXA_MAX_QUERY_LENGTH", "120"), "ALEXA_MAX_QUERY_LENGTH"
    )

    return AlexaSettings(
        command=command,
        base_args=base_args,
        event_flag=event_flag,
        device_flag=device_flag,
        default_device=default_device,
        allowed_routines=frozenset(item.lower() for item in allowed_routines),
        allowed_music_actions=frozenset(item.lower() for item in allowed_music_actions),
        timeout_seconds=timeout_seconds,
        health_check_args=health_check_args,
        music_play_routine=music_play_routine,
        music_stop_routine=music_stop_routine,
        max_query_length=max_query_length,
    )


def ensure_allowed_routine(settings: AlexaSettings, routine_name: str) -> str:
    normalized = normalize_identifier(routine_name, field_name="routine_name")
    if normalized.lower() not in settings.allowed_routines:
        allowed = ", ".join(sorted(settings.allowed_routines))
        raise ConfigError(
            f"Routine '{normalized}' is not allowlisted. Allowed routines: {allowed}."
        )
    return normalized


def ensure_allowed_music_action(settings: AlexaSettings, action: str) -> str:
    normalized = normalize_identifier(action, field_name="action").lower()
    if normalized not in settings.allowed_music_actions:
        allowed = ", ".join(sorted(settings.allowed_music_actions))
        raise ConfigError(
            f"Music action '{normalized}' is not allowlisted. Allowed actions: {allowed}."
        )
    return normalized


def normalize_identifier(raw_value: str, field_name: str) -> str:
    value = raw_value.strip()
    if not value:
        raise ConfigError(f"{field_name} cannot be empty.")
    if "\n" in value or "\r" in value:
        raise ConfigError(f"{field_name} cannot contain newline characters.")
    return value


def normalize_query(query: str, max_length: int) -> str:
    value = query.strip()
    if not value:
        raise ConfigError("query cannot be empty for the selected action.")
    if "\n" in value or "\r" in value:
        raise ConfigError("query cannot contain newline characters.")
    if len(value) > max_length:
        raise ConfigError(f"query length exceeds maximum of {max_length} characters.")
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


def _require_non_empty(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigError(f"{key} is required and must be non-empty.")
    return value


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None
