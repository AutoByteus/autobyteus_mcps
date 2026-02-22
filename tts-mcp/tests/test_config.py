from __future__ import annotations

import pytest

from tts_mcp.config import ConfigError, SUPPORTED_MLX_MODEL_IDS, load_settings, model_requires_instruct


def test_load_settings_defaults() -> None:
    settings = load_settings({})

    assert settings.default_backend == "auto"
    assert settings.linux_runtime == "kokoro_onnx"
    assert settings.timeout_seconds == 180
    assert settings.process_lock_timeout_seconds == 30
    assert settings.delete_auto_output is True
    assert settings.enforce_latest_runtime is True
    assert settings.version_check_timeout_seconds == 6
    assert settings.auto_install_runtime is True
    assert settings.auto_install_llama_on_macos is False
    assert settings.hf_hub_offline_mode == "auto"
    assert settings.default_speed == 1.0
    assert settings.mlx_command == "mlx_audio.tts.generate"
    assert settings.mlx_model_preset == "kokoro_fast"
    assert settings.mlx_model in SUPPORTED_MLX_MODEL_IDS
    assert settings.llama_command == "llama-tts"
    assert settings.kokoro_model_path.endswith("kokoro-v1.0.int8.onnx")
    assert settings.kokoro_voices_path.endswith("voices-v1.0.bin")
    assert settings.kokoro_vocab_config_path is None
    assert settings.kokoro_misaki_zh_version == "1.1"
    assert settings.kokoro_default_voice == "af_heart"
    assert settings.kokoro_default_language_code == "en-us"


def test_load_settings_rejects_invalid_backend() -> None:
    with pytest.raises(ConfigError, match="TTS_MCP_BACKEND"):
        load_settings({"TTS_MCP_BACKEND": "bad"})


def test_load_settings_rejects_invalid_linux_runtime() -> None:
    with pytest.raises(ConfigError, match="TTS_MCP_LINUX_RUNTIME"):
        load_settings({"TTS_MCP_LINUX_RUNTIME": "bad"})


def test_load_settings_rejects_invalid_preset() -> None:
    with pytest.raises(ConfigError, match="TTS_MCP_MLX_MODEL_PRESET"):
        load_settings({"TTS_MCP_MLX_MODEL_PRESET": "unknown"})


def test_load_settings_rejects_unsupported_mlx_model() -> None:
    with pytest.raises(ConfigError, match="MLX_TTS_MODEL"):
        load_settings({"MLX_TTS_MODEL": "my-org/custom"})


def test_load_settings_requires_vocoder_when_model_is_set() -> None:
    with pytest.raises(ConfigError, match="LLAMA_TTS_VOCODER_PATH"):
        load_settings({"LLAMA_TTS_MODEL_PATH": "/tmp/model.gguf"})


def test_load_settings_rejects_invalid_hf_hub_offline_mode() -> None:
    with pytest.raises(ConfigError, match="TTS_MCP_HF_HUB_OFFLINE_MODE"):
        load_settings({"TTS_MCP_HF_HUB_OFFLINE_MODE": "maybe"})


def test_load_settings_rejects_invalid_process_lock_timeout() -> None:
    with pytest.raises(ConfigError, match="TTS_MCP_PROCESS_LOCK_TIMEOUT_SECONDS"):
        load_settings({"TTS_MCP_PROCESS_LOCK_TIMEOUT_SECONDS": "0"})


def test_load_settings_rejects_invalid_default_speed() -> None:
    with pytest.raises(ConfigError, match="TTS_MCP_DEFAULT_SPEED"):
        load_settings({"TTS_MCP_DEFAULT_SPEED": "0"})


def test_model_requires_instruct_for_voicedesign() -> None:
    assert model_requires_instruct("mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16") is True
    assert model_requires_instruct("mlx-community/Kokoro-82M-bf16") is False
