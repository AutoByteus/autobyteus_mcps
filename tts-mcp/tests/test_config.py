from __future__ import annotations

import pytest

from tts_mcp.config import ConfigError, SUPPORTED_MLX_MODEL_IDS, load_settings, model_requires_instruct


def test_load_settings_defaults() -> None:
    settings = load_settings({})

    assert settings.default_backend == "auto"
    assert settings.timeout_seconds == 180
    assert settings.enforce_latest_runtime is True
    assert settings.version_check_timeout_seconds == 6
    assert settings.auto_install_runtime is True
    assert settings.auto_install_llama_on_macos is False
    assert settings.mlx_command == "mlx_audio.tts.generate"
    assert settings.mlx_model_preset == "kokoro_fast"
    assert settings.mlx_model in SUPPORTED_MLX_MODEL_IDS
    assert settings.llama_command == "llama-tts"


def test_load_settings_rejects_invalid_backend() -> None:
    with pytest.raises(ConfigError, match="TTS_MCP_BACKEND"):
        load_settings({"TTS_MCP_BACKEND": "bad"})


def test_load_settings_rejects_invalid_preset() -> None:
    with pytest.raises(ConfigError, match="TTS_MCP_MLX_MODEL_PRESET"):
        load_settings({"TTS_MCP_MLX_MODEL_PRESET": "unknown"})


def test_load_settings_rejects_unsupported_mlx_model() -> None:
    with pytest.raises(ConfigError, match="MLX_TTS_MODEL"):
        load_settings({"MLX_TTS_MODEL": "my-org/custom"})


def test_load_settings_requires_vocoder_when_model_is_set() -> None:
    with pytest.raises(ConfigError, match="LLAMA_TTS_VOCODER_PATH"):
        load_settings({"LLAMA_TTS_MODEL_PATH": "/tmp/model.gguf"})


def test_model_requires_instruct_for_voicedesign() -> None:
    assert model_requires_instruct("mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16") is True
    assert model_requires_instruct("mlx-community/Kokoro-82M-bf16") is False
