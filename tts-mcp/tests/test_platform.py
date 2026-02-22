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


def test_select_backend_auto_uses_kokoro_on_linux_by_default() -> None:
    settings = load_settings({})
    host = HostInfo(
        system="Linux",
        machine="x86_64",
        is_macos_arm64=False,
        is_linux=True,
        has_nvidia=True,
    )

    selection = select_backend(settings=settings, host=host, command_resolver=_resolver_ok)

    assert selection.backend == "kokoro_onnx"
    assert selection.command == "kokoro_onnx"


def test_select_backend_auto_rejects_llama_on_host_without_nvidia() -> None:
    settings = load_settings({"TTS_MCP_LINUX_RUNTIME": "llama_cpp"})
    host = HostInfo(
        system="Linux",
        machine="x86_64",
        is_macos_arm64=False,
        is_linux=True,
        has_nvidia=False,
    )

    with pytest.raises(BackendSelectionError, match="TTS_MCP_LINUX_RUNTIME=llama_cpp"):
        select_backend(settings=settings, host=host, command_resolver=_resolver_ok)


def test_select_backend_auto_uses_kokoro_on_linux_when_configured() -> None:
    settings = load_settings({"TTS_MCP_LINUX_RUNTIME": "kokoro_onnx"})
    host = HostInfo(
        system="Linux",
        machine="x86_64",
        is_macos_arm64=False,
        is_linux=True,
        has_nvidia=False,
    )

    selection = select_backend(settings=settings, host=host, command_resolver=_resolver_ok)

    assert selection.backend == "kokoro_onnx"
    assert selection.command == "kokoro_onnx"


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


def test_select_backend_explicit_kokoro_rejects_non_linux() -> None:
    settings = load_settings({})
    host = HostInfo(
        system="Darwin",
        machine="arm64",
        is_macos_arm64=True,
        is_linux=False,
        has_nvidia=False,
    )

    with pytest.raises(BackendSelectionError, match="kokoro_onnx backend"):
        select_backend(
            settings=settings,
            preferred_backend="kokoro_onnx",
            host=host,
            command_resolver=_resolver_ok,
        )
