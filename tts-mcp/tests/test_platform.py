from __future__ import annotations

import pytest

from tts_mcp.config import load_settings
from tts_mcp.platform import BackendSelectionError, HostInfo, select_backend


def _resolver_ok(_: str) -> str:
    return "/usr/bin/fake"


def test_select_backend_auto_prefers_mlx_on_apple_silicon() -> None:
    settings = load_settings({})
    host = HostInfo(
        system="Darwin",
        machine="arm64",
        is_macos_arm64=True,
        is_linux=False,
        has_nvidia=False,
    )

    selection = select_backend(settings=settings, host=host, command_resolver=_resolver_ok)

    assert selection.backend == "mlx_audio"
    assert selection.command == settings.mlx_command


def test_select_backend_auto_uses_llama_on_linux_nvidia() -> None:
    settings = load_settings({})
    host = HostInfo(
        system="Linux",
        machine="x86_64",
        is_macos_arm64=False,
        is_linux=True,
        has_nvidia=True,
    )

    selection = select_backend(settings=settings, host=host, command_resolver=_resolver_ok)

    assert selection.backend == "llama_cpp"
    assert selection.command == settings.llama_command


def test_select_backend_auto_rejects_unsupported_host() -> None:
    settings = load_settings({})
    host = HostInfo(
        system="Linux",
        machine="x86_64",
        is_macos_arm64=False,
        is_linux=True,
        has_nvidia=False,
    )

    with pytest.raises(BackendSelectionError, match="Auto backend selection"):
        select_backend(settings=settings, host=host, command_resolver=_resolver_ok)


def test_select_backend_reports_missing_command() -> None:
    settings = load_settings({})
    host = HostInfo(
        system="Darwin",
        machine="arm64",
        is_macos_arm64=True,
        is_linux=False,
        has_nvidia=False,
    )

    with pytest.raises(BackendSelectionError, match="Required command"):
        select_backend(settings=settings, host=host, command_resolver=lambda _: None)
