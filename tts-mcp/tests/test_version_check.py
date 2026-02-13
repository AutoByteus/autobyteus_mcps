from __future__ import annotations

import tts_mcp.version_check as version_check


def test_check_backend_runtime_version_mlx_latest(monkeypatch) -> None:
    version_check.check_backend_runtime_version.cache_clear()
    monkeypatch.setattr(version_check, "_detect_mlx_audio_local_version", lambda **_: "0.3.1")
    monkeypatch.setattr(version_check, "_fetch_latest_pypi_version", lambda *_, **__: "0.3.1")

    result = version_check.check_backend_runtime_version(
        backend="mlx_audio",
        command="mlx_audio.tts.generate",
        timeout_seconds=5,
    )

    assert result["status"] == "latest"


def test_check_backend_runtime_version_mlx_outdated(monkeypatch) -> None:
    version_check.check_backend_runtime_version.cache_clear()
    monkeypatch.setattr(version_check, "_detect_mlx_audio_local_version", lambda **_: "0.2.10")
    monkeypatch.setattr(version_check, "_fetch_latest_pypi_version", lambda *_, **__: "0.3.1")

    result = version_check.check_backend_runtime_version(
        backend="mlx_audio",
        command="mlx_audio.tts.generate",
        timeout_seconds=5,
    )

    assert result["status"] == "outdated"
    assert "0.2.10" in result["message"]


def test_check_backend_runtime_version_llama_outdated(monkeypatch) -> None:
    version_check.check_backend_runtime_version.cache_clear()
    monkeypatch.setattr(version_check, "_detect_command_version", lambda **_: "llama.cpp version b6200")
    monkeypatch.setattr(version_check, "_fetch_latest_llama_cpp_release", lambda **_: "b6300")

    result = version_check.check_backend_runtime_version(
        backend="llama_cpp",
        command="llama-tts",
        timeout_seconds=5,
    )

    assert result["status"] == "outdated"
    assert "b6200" in result["message"]
