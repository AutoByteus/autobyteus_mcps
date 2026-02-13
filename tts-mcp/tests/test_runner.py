from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from tts_mcp.config import load_settings
from tts_mcp.platform import BackendSelection, HostInfo
import tts_mcp.runner as runner


_MIN_VALID_WAV_BYTES = b"RIFF" + (b"\x00" * 60)


@pytest.fixture(autouse=True)
def _mock_runtime_version_check(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "check_backend_runtime_version",
        lambda **_: {
            "status": "latest",
            "local_version": "1.0.0",
            "latest_version": "1.0.0",
            "message": "runtime is up to date",
        },
    )


def _mlx_host() -> HostInfo:
    return HostInfo(
        system="Darwin",
        machine="arm64",
        is_macos_arm64=True,
        is_linux=False,
        has_nvidia=False,
    )


def _linux_host() -> HostInfo:
    return HostInfo(
        system="Linux",
        machine="x86_64",
        is_macos_arm64=False,
        is_linux=True,
        has_nvidia=True,
    )


def test_run_speak_mlx_success(monkeypatch, tmp_path: Path) -> None:
    settings = load_settings({"TTS_MCP_OUTPUT_DIR": str(tmp_path)})

    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )

    output_file = tmp_path / "mlx.wav"

    def fake_run(command, **kwargs):
        assert command[0] == settings.mlx_command
        assert "--model" in command
        assert command[command.index("--lang_code") + 1] == "a"
        prefix = command[command.index("--file_prefix") + 1]
        Path(f"{prefix}.wav").write_bytes(_MIN_VALID_WAV_BYTES)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_speak(
        settings=settings,
        text="Hello from MLX",
        output_path=str(output_file),
        play=False,
    )

    assert result["ok"] is True
    assert result["backend"] == "mlx_audio"
    assert result["output_path"] == str(output_file)
    assert result["warnings"] == []


def test_run_speak_mlx_marks_played_only_when_confirmed(monkeypatch, tmp_path: Path) -> None:
    settings = load_settings({"TTS_MCP_OUTPUT_DIR": str(tmp_path)})

    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )

    output_file = tmp_path / "mlx_play.wav"

    def fake_run(command, **kwargs):
        prefix = command[command.index("--file_prefix") + 1]
        Path(f"{prefix}.wav").write_bytes(_MIN_VALID_WAV_BYTES)
        return subprocess.CompletedProcess(command, 0, "Starting audio stream...", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_speak(
        settings=settings,
        text="Hello from MLX",
        output_path=str(output_file),
        play=True,
    )

    assert result["ok"] is True
    assert result["played"] is True
    assert result["warnings"] == []


def test_run_speak_mlx_warns_when_playback_not_confirmed(monkeypatch, tmp_path: Path) -> None:
    settings = load_settings({"TTS_MCP_OUTPUT_DIR": str(tmp_path)})

    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )

    output_file = tmp_path / "mlx_no_play_marker.wav"

    def fake_run(command, **kwargs):
        prefix = command[command.index("--file_prefix") + 1]
        Path(f"{prefix}.wav").write_bytes(_MIN_VALID_WAV_BYTES)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_speak(
        settings=settings,
        text="Hello from MLX",
        output_path=str(output_file),
        play=True,
    )

    assert result["ok"] is True
    assert result["played"] is False
    assert result["warnings"]


def test_run_speak_requires_instruct_for_voicedesign(monkeypatch) -> None:
    settings = load_settings(
        {"TTS_MCP_MLX_MODEL_PRESET": "qwen_voicedesign_hq", "MLX_TTS_MODEL": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"}
    )
    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )

    result = runner.run_speak(
        settings=settings,
        text="Hello",
        instruct=None,
    )

    assert result["ok"] is False
    assert result["error_type"] == "validation"


def test_run_speak_uses_default_instruct_for_voicedesign(monkeypatch, tmp_path: Path) -> None:
    settings = load_settings(
        {
            "TTS_MCP_OUTPUT_DIR": str(tmp_path),
            "TTS_MCP_MLX_MODEL_PRESET": "qwen_voicedesign_hq",
            "MLX_TTS_MODEL": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
            "MLX_TTS_DEFAULT_INSTRUCT": "A warm calm narrator voice",
        }
    )
    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )

    output_file = tmp_path / "vd.wav"

    def fake_run(command, **kwargs):
        if command[1:] == ["-h"]:
            return subprocess.CompletedProcess(command, 0, "--instruct", "")
        assert "--instruct" in command
        prefix = command[command.index("--file_prefix") + 1]
        Path(f"{prefix}.wav").write_bytes(_MIN_VALID_WAV_BYTES)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_speak(
        settings=settings,
        text="Hello",
        output_path=str(output_file),
        play=False,
    )

    assert result["ok"] is True


def test_run_speak_llama_playback_warning_when_no_player(monkeypatch, tmp_path: Path) -> None:
    settings = load_settings({"TTS_MCP_OUTPUT_DIR": str(tmp_path)})

    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="llama_cpp", command=settings.llama_command, host=_linux_host()),
    )
    monkeypatch.setattr(runner, "_build_linux_play_command", lambda **_: None)

    output_file = tmp_path / "llama.wav"

    def fake_run(command, **kwargs):
        assert command[0] == settings.llama_command
        output_file.write_bytes(_MIN_VALID_WAV_BYTES)
        return subprocess.CompletedProcess(command, 0, "done", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_speak(
        settings=settings,
        text="Hello from llama",
        output_path=str(output_file),
        play=True,
    )

    assert result["ok"] is True
    assert result["backend"] == "llama_cpp"
    assert result["played"] is False
    assert result["warnings"]


def test_run_speak_rejects_instruct_on_llama(monkeypatch) -> None:
    settings = load_settings({})
    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="llama_cpp", command=settings.llama_command, host=_linux_host()),
    )

    result = runner.run_speak(
        settings=settings,
        text="Hello",
        instruct="style",
    )

    assert result["ok"] is False
    assert result["error_type"] == "validation"


def test_run_speak_rejects_empty_text() -> None:
    settings = load_settings({})
    result = runner.run_speak(settings=settings, text="   ")

    assert result["ok"] is False
    assert result["error_type"] == "validation"


def test_run_speak_rejects_non_wav_output_path(monkeypatch, tmp_path: Path) -> None:
    settings = load_settings({})
    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )

    result = runner.run_speak(
        settings=settings,
        text="hello",
        output_path=str(tmp_path / "audio.mp3"),
    )

    assert result["ok"] is False
    assert result["error_type"] == "validation"


def test_run_speak_fails_if_existing_output_file_not_updated(monkeypatch, tmp_path: Path) -> None:
    settings = load_settings({"TTS_MCP_OUTPUT_DIR": str(tmp_path)})
    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )

    output_file = tmp_path / "stale.wav"
    output_file.write_bytes(_MIN_VALID_WAV_BYTES)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_speak(
        settings=settings,
        text="hello",
        output_path=str(output_file),
        play=False,
    )

    assert result["ok"] is False
    assert result["error_type"] == "execution"


def test_run_speak_blocks_outdated_runtime_when_enforced(monkeypatch) -> None:
    settings = load_settings({})
    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )
    monkeypatch.setattr(
        runner,
        "check_backend_runtime_version",
        lambda **_: {
            "status": "outdated",
            "local_version": "0.2.10",
            "latest_version": "0.3.1",
            "message": "mlx-audio is outdated",
        },
    )

    result = runner.run_speak(settings=settings, text="hello")

    assert result["ok"] is False
    assert result["error_type"] == "dependency"


def test_run_speak_allows_outdated_runtime_when_not_enforced(monkeypatch, tmp_path: Path) -> None:
    settings = load_settings(
        {
            "TTS_MCP_ENFORCE_LATEST": "false",
            "TTS_MCP_OUTPUT_DIR": str(tmp_path),
        }
    )
    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )
    monkeypatch.setattr(
        runner,
        "check_backend_runtime_version",
        lambda **_: {
            "status": "outdated",
            "local_version": "0.2.10",
            "latest_version": "0.3.1",
            "message": "mlx-audio is outdated",
        },
    )

    output_file = tmp_path / "outdated_but_allowed.wav"

    def fake_run(command, **kwargs):
        prefix = command[command.index("--file_prefix") + 1]
        Path(f"{prefix}.wav").write_bytes(_MIN_VALID_WAV_BYTES)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_speak(
        settings=settings,
        text="hello",
        output_path=str(output_file),
        play=False,
    )

    assert result["ok"] is True
    assert result["warnings"]


def test_run_speak_blocks_when_runtime_freshness_is_unknown_and_enforced(monkeypatch) -> None:
    settings = load_settings({})
    monkeypatch.setattr(
        runner,
        "select_backend",
        lambda **_: BackendSelection(backend="mlx_audio", command=settings.mlx_command, host=_mlx_host()),
    )
    monkeypatch.setattr(
        runner,
        "check_backend_runtime_version",
        lambda **_: {
            "status": "unknown",
            "local_version": None,
            "latest_version": "0.3.1",
            "message": "Could not fetch latest mlx-audio version from PyPI.",
        },
    )

    result = runner.run_speak(settings=settings, text="hello")

    assert result["ok"] is False
    assert result["error_type"] == "dependency"
