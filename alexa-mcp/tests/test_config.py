from __future__ import annotations

import pytest

from alexa_mcp.config import ConfigError, load_settings


def _base_env() -> dict[str, str]:
    return {
        "ALEXA_COMMAND": "/tmp/alexa_adapter.sh",
        "ALEXA_ALLOWED_ROUTINES": "plug_on,plug_off",
    }


def test_load_settings_rejects_placeholder_default_device() -> None:
    env = {
        **_base_env(),
        "ALEXA_DEFAULT_DEVICE": "REPLACE_WITH_DEFAULT_ECHO_NAME",
    }

    with pytest.raises(ConfigError, match="ALEXA_DEFAULT_DEVICE appears to be a placeholder"):
        load_settings(env)


def test_load_settings_accepts_real_default_device_name() -> None:
    env = {
        **_base_env(),
        "ALEXA_DEFAULT_DEVICE": "Kitchen Echo Dot",
    }

    settings = load_settings(env)
    assert settings.default_device == "Kitchen Echo Dot"


def test_load_settings_accepts_missing_default_device() -> None:
    settings = load_settings(_base_env())
    assert settings.default_device is None
