from __future__ import annotations

import pytest

from ssh_mcp.config import (
    ConfigError,
    load_settings,
    normalize_remote_command,
    normalize_session_id,
    resolve_password,
    resolve_target,
)


def test_load_settings_defaults() -> None:
    settings = load_settings({})

    assert settings.command == "ssh"
    assert settings.base_args == tuple()
    assert settings.timeout_seconds == 60
    assert settings.allowed_hosts == tuple()
    assert settings.default_host is None
    assert settings.default_user is None
    assert settings.default_port is None
    assert settings.max_command_chars == 4000
    assert settings.max_output_chars == 20000
    assert settings.health_check_args == ("-V",)
    assert settings.password is None
    assert settings.password_file is None
    assert settings.session_idle_timeout_seconds == 300
    assert settings.max_sessions == 32
    assert settings.session_dir is None


def test_load_settings_parses_allowed_hosts_and_defaults() -> None:
    settings = load_settings(
        {
            "SSH_MCP_ALLOWED_HOSTS": "host-a,host-b",
            "SSH_MCP_DEFAULT_HOST": "host-a",
            "SSH_MCP_DEFAULT_USER": "ubuntu",
            "SSH_MCP_DEFAULT_PORT": "2222",
            "SSH_MCP_SESSION_IDLE_TIMEOUT_SECONDS": "120",
            "SSH_MCP_MAX_SESSIONS": "8",
            "SSH_MCP_SESSION_DIR": "~/tmp/ssh-mcp-sessions",
        }
    )

    assert settings.allowed_hosts == ("host-a", "host-b")
    assert settings.default_host == "host-a"
    assert settings.default_user == "ubuntu"
    assert settings.default_port == 2222
    assert settings.session_idle_timeout_seconds == 120
    assert settings.max_sessions == 8
    assert settings.session_dir is not None


def test_load_settings_rejects_invalid_allowlist_entry() -> None:
    with pytest.raises(ConfigError, match="invalid host entry"):
        load_settings({"SSH_MCP_ALLOWED_HOSTS": "host-a,invalid host"})


def test_resolve_target_uses_defaults_and_allowlist() -> None:
    settings = load_settings(
        {
            "SSH_MCP_ALLOWED_HOSTS": "prod-1",
            "SSH_MCP_DEFAULT_HOST": "prod-1",
            "SSH_MCP_DEFAULT_USER": "ubuntu",
            "SSH_MCP_DEFAULT_PORT": "2200",
        }
    )

    target = resolve_target(settings, host=None, user=None, port=None)

    assert target.host == "prod-1"
    assert target.user == "ubuntu"
    assert target.port == 2200
    assert target.destination == "ubuntu@prod-1"


def test_resolve_target_rejects_disallowed_host() -> None:
    settings = load_settings({"SSH_MCP_ALLOWED_HOSTS": "prod-1"})

    with pytest.raises(ConfigError, match="not allowlisted"):
        resolve_target(settings, host="prod-2", user=None, port=None)


def test_resolve_target_requires_host_when_no_default() -> None:
    settings = load_settings({})

    with pytest.raises(ConfigError, match="host is required"):
        resolve_target(settings, host=None, user=None, port=None)


def test_normalize_remote_command_rejects_newline() -> None:
    with pytest.raises(ConfigError, match="newline"):
        normalize_remote_command("echo hi\nwhoami", max_chars=100)


def test_normalize_session_id_validates_format() -> None:
    assert normalize_session_id("abc12345") == "abc12345"
    with pytest.raises(ConfigError, match="format"):
        normalize_session_id("bad session")


def test_load_settings_rejects_conflicting_password_sources() -> None:
    with pytest.raises(ConfigError, match="either SSH_MCP_PASSWORD or SSH_MCP_PASSWORD_FILE"):
        load_settings({"SSH_MCP_PASSWORD": "x", "SSH_MCP_PASSWORD_FILE": "/tmp/secret"})


def test_resolve_password_prefers_inline_secret() -> None:
    settings = load_settings({"SSH_MCP_PASSWORD": "topsecret"})
    assert resolve_password(settings) == "topsecret"


def test_resolve_password_reads_from_file(tmp_path) -> None:
    secret_file = tmp_path / "ssh-password.txt"
    secret_file.write_text("dockerpass\n", encoding="utf-8")
    settings = load_settings({"SSH_MCP_PASSWORD_FILE": str(secret_file)})
    assert resolve_password(settings) == "dockerpass"


def test_resolve_password_rejects_empty_file(tmp_path) -> None:
    secret_file = tmp_path / "ssh-password.txt"
    secret_file.write_text("\n", encoding="utf-8")
    settings = load_settings({"SSH_MCP_PASSWORD_FILE": str(secret_file)})
    with pytest.raises(ConfigError, match="is empty"):
        resolve_password(settings)
