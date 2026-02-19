from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Literal, Mapping

BackendName = Literal["auto", "mlx_audio", "llama_cpp", "kokoro_onnx"]
LinuxRuntimeName = Literal["llama_cpp", "kokoro_onnx"]
MlxModelPreset = Literal["kokoro_fast", "qwen_base_hq", "qwen_voicedesign_hq"]
HfHubOfflineMode = Literal["auto", "true", "false"]

DEFAULT_SERVER_NAME = "tts-mcp"
DEFAULT_INSTRUCTIONS = (
    "Expose one speak tool that converts text to speech. "
    "Auto-route to MLX Audio on Apple Silicon, and on Linux route by runtime policy "
    "(llama.cpp or Kokoro ONNX)."
)

MLX_MODEL_PRESETS: dict[MlxModelPreset, tuple[str, str, bool]] = {
    "kokoro_fast": (
        "mlx-community/Kokoro-82M-bf16",
        "Fast and small; best default for low-latency speech.",
        False,
    ),
    "qwen_base_hq": (
        "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
        "Higher-quality general model.",
        False,
    ),
    "qwen_voicedesign_hq": (
        "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
        "Highest flexibility for designed voices; requires instruct.",
        True,
    ),
}

SUPPORTED_MLX_MODEL_IDS: tuple[str, ...] = tuple(
    preset[0] for preset in MLX_MODEL_PRESETS.values()
)


class ConfigError(ValueError):
    """Raised when configuration values are invalid."""


@dataclass(frozen=True, slots=True)
class ServerConfig:
    name: str = DEFAULT_SERVER_NAME
    instructions: str = DEFAULT_INSTRUCTIONS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ServerConfig":
        actual_env = env if env is not None else os.environ
        return cls(
            name=actual_env.get("TTS_MCP_NAME", DEFAULT_SERVER_NAME),
            instructions=actual_env.get("TTS_MCP_INSTRUCTIONS", DEFAULT_INSTRUCTIONS),
        )


@dataclass(frozen=True, slots=True)
class TtsSettings:
    default_backend: BackendName
    linux_runtime: LinuxRuntimeName
    timeout_seconds: int
    process_lock_timeout_seconds: int
    output_dir: str
    delete_auto_output: bool
    enforce_latest_runtime: bool
    version_check_timeout_seconds: int
    auto_install_runtime: bool
    auto_install_llama_on_macos: bool
    hf_hub_offline_mode: HfHubOfflineMode

    mlx_command: str
    mlx_model_preset: MlxModelPreset
    mlx_model: str
    mlx_default_voice: str | None
    mlx_default_language_code: str
    mlx_default_instruct: str | None

    llama_command: str
    llama_use_oute_default: bool
    llama_model_path: str | None
    llama_vocoder_path: str | None
    llama_n_gpu_layers: int

    kokoro_model_path: str
    kokoro_voices_path: str
    kokoro_default_voice: str
    kokoro_default_language_code: str

    linux_player: Literal["auto", "ffplay", "aplay", "paplay", "none"]


def load_settings(env: Mapping[str, str] | None = None) -> TtsSettings:
    actual_env = env if env is not None else os.environ

    default_backend = _parse_backend(actual_env.get("TTS_MCP_BACKEND", "auto"))
    linux_runtime = _parse_linux_runtime(actual_env.get("TTS_MCP_LINUX_RUNTIME", "llama_cpp"))
    timeout_seconds = _parse_positive_int(
        actual_env.get("TTS_MCP_TIMEOUT_SECONDS", "180"),
        "TTS_MCP_TIMEOUT_SECONDS",
    )
    process_lock_timeout_seconds = _parse_positive_int(
        actual_env.get("TTS_MCP_PROCESS_LOCK_TIMEOUT_SECONDS", "30"),
        "TTS_MCP_PROCESS_LOCK_TIMEOUT_SECONDS",
    )
    output_dir = actual_env.get("TTS_MCP_OUTPUT_DIR", "outputs").strip() or "outputs"
    delete_auto_output = _parse_bool(
        actual_env.get("TTS_MCP_DELETE_AUTO_OUTPUT", "true"),
        "TTS_MCP_DELETE_AUTO_OUTPUT",
    )
    enforce_latest_runtime = _parse_bool(
        actual_env.get("TTS_MCP_ENFORCE_LATEST", "true"),
        "TTS_MCP_ENFORCE_LATEST",
    )
    version_check_timeout_seconds = _parse_positive_int(
        actual_env.get("TTS_MCP_VERSION_CHECK_TIMEOUT_SECONDS", "6"),
        "TTS_MCP_VERSION_CHECK_TIMEOUT_SECONDS",
    )
    auto_install_runtime = _parse_bool(
        actual_env.get("TTS_MCP_AUTO_INSTALL_RUNTIME", "true"),
        "TTS_MCP_AUTO_INSTALL_RUNTIME",
    )
    auto_install_llama_on_macos = _parse_bool(
        actual_env.get("TTS_MCP_AUTO_INSTALL_LLAMA_ON_MACOS", "false"),
        "TTS_MCP_AUTO_INSTALL_LLAMA_ON_MACOS",
    )
    hf_hub_offline_mode = _parse_hf_hub_offline_mode(
        actual_env.get("TTS_MCP_HF_HUB_OFFLINE_MODE", "auto")
    )

    mlx_command = _require_non_empty(actual_env, "MLX_TTS_COMMAND", default="mlx_audio.tts.generate")

    mlx_model_preset = _parse_model_preset(
        actual_env.get("TTS_MCP_MLX_MODEL_PRESET", "kokoro_fast")
    )
    preset_model = MLX_MODEL_PRESETS[mlx_model_preset][0]
    mlx_model = _require_non_empty(
        actual_env,
        "MLX_TTS_MODEL",
        default=preset_model,
    )

    if mlx_model not in SUPPORTED_MLX_MODEL_IDS:
        allowed = ", ".join(SUPPORTED_MLX_MODEL_IDS)
        raise ConfigError(
            f"MLX_TTS_MODEL must be one of supported models: {allowed}."
        )

    mlx_default_voice = _optional_text(actual_env.get("MLX_TTS_DEFAULT_VOICE"))
    mlx_default_language_code = _require_non_empty(
        actual_env,
        "MLX_TTS_DEFAULT_LANG_CODE",
        default="en",
    )
    mlx_default_instruct = _optional_text(actual_env.get("MLX_TTS_DEFAULT_INSTRUCT"))

    llama_command = _require_non_empty(actual_env, "LLAMA_TTS_COMMAND", default="llama-tts")
    llama_use_oute_default = _parse_bool(
        actual_env.get("LLAMA_TTS_USE_OUTE_DEFAULT", "true"),
        "LLAMA_TTS_USE_OUTE_DEFAULT",
    )
    llama_model_path = _optional_text(actual_env.get("LLAMA_TTS_MODEL_PATH"))
    llama_vocoder_path = _optional_text(actual_env.get("LLAMA_TTS_VOCODER_PATH"))
    llama_n_gpu_layers = _parse_int(
        actual_env.get("LLAMA_TTS_N_GPU_LAYERS", "-1"),
        "LLAMA_TTS_N_GPU_LAYERS",
    )

    if llama_model_path and not llama_vocoder_path:
        raise ConfigError(
            "LLAMA_TTS_VOCODER_PATH is required when LLAMA_TTS_MODEL_PATH is set."
        )
    if not llama_model_path and not llama_use_oute_default:
        raise ConfigError(
            "Set LLAMA_TTS_USE_OUTE_DEFAULT=true or provide both LLAMA_TTS_MODEL_PATH "
            "and LLAMA_TTS_VOCODER_PATH."
        )

    kokoro_model_path = _require_non_empty(
        actual_env,
        "KOKORO_TTS_MODEL_PATH",
        default=".tools/kokoro-current/kokoro-v1.0.int8.onnx",
    )
    kokoro_voices_path = _require_non_empty(
        actual_env,
        "KOKORO_TTS_VOICES_PATH",
        default=".tools/kokoro-current/voices-v1.0.bin",
    )
    kokoro_default_voice = _require_non_empty(
        actual_env,
        "KOKORO_TTS_DEFAULT_VOICE",
        default="af_heart",
    )
    kokoro_default_language_code = _require_non_empty(
        actual_env,
        "KOKORO_TTS_DEFAULT_LANG_CODE",
        default="en-us",
    )

    linux_player = _parse_linux_player(actual_env.get("TTS_MCP_LINUX_PLAYER", "auto"))

    return TtsSettings(
        default_backend=default_backend,
        linux_runtime=linux_runtime,
        timeout_seconds=timeout_seconds,
        process_lock_timeout_seconds=process_lock_timeout_seconds,
        output_dir=output_dir,
        delete_auto_output=delete_auto_output,
        enforce_latest_runtime=enforce_latest_runtime,
        version_check_timeout_seconds=version_check_timeout_seconds,
        auto_install_runtime=auto_install_runtime,
        auto_install_llama_on_macos=auto_install_llama_on_macos,
        hf_hub_offline_mode=hf_hub_offline_mode,
        mlx_command=mlx_command,
        mlx_model_preset=mlx_model_preset,
        mlx_model=mlx_model,
        mlx_default_voice=mlx_default_voice,
        mlx_default_language_code=mlx_default_language_code,
        mlx_default_instruct=mlx_default_instruct,
        llama_command=llama_command,
        llama_use_oute_default=llama_use_oute_default,
        llama_model_path=llama_model_path,
        llama_vocoder_path=llama_vocoder_path,
        llama_n_gpu_layers=llama_n_gpu_layers,
        kokoro_model_path=kokoro_model_path,
        kokoro_voices_path=kokoro_voices_path,
        kokoro_default_voice=kokoro_default_voice,
        kokoro_default_language_code=kokoro_default_language_code,
        linux_player=linux_player,
    )


def model_requires_instruct(model_id: str) -> bool:
    for configured_model, _, requires_instruct in MLX_MODEL_PRESETS.values():
        if configured_model == model_id:
            return requires_instruct
    return False


def _parse_model_preset(raw: str) -> MlxModelPreset:
    value = raw.strip().lower()
    allowed = set(MLX_MODEL_PRESETS.keys())
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ConfigError(f"TTS_MCP_MLX_MODEL_PRESET must be one of: {allowed_values}.")
    return value  # type: ignore[return-value]


def _parse_backend(raw: str) -> BackendName:
    value = raw.strip().lower()
    allowed = {"auto", "mlx_audio", "llama_cpp", "kokoro_onnx"}
    if value not in allowed:
        raise ConfigError(
            "TTS_MCP_BACKEND must be one of: auto, mlx_audio, llama_cpp, kokoro_onnx."
        )
    return value  # type: ignore[return-value]


def _parse_linux_runtime(raw: str) -> LinuxRuntimeName:
    value = raw.strip().lower()
    allowed = {"llama_cpp", "kokoro_onnx"}
    if value not in allowed:
        raise ConfigError(
            "TTS_MCP_LINUX_RUNTIME must be one of: llama_cpp, kokoro_onnx."
        )
    return value  # type: ignore[return-value]


def _parse_linux_player(raw: str) -> Literal["auto", "ffplay", "aplay", "paplay", "none"]:
    value = raw.strip().lower()
    allowed = {"auto", "ffplay", "aplay", "paplay", "none"}
    if value not in allowed:
        raise ConfigError(
            "TTS_MCP_LINUX_PLAYER must be one of: auto, ffplay, aplay, paplay, none."
        )
    return value  # type: ignore[return-value]


def _parse_hf_hub_offline_mode(raw: str) -> HfHubOfflineMode:
    value = raw.strip().lower()
    allowed = {"auto", "true", "false"}
    if value not in allowed:
        raise ConfigError(
            "TTS_MCP_HF_HUB_OFFLINE_MODE must be one of: auto, true, false."
        )
    return value  # type: ignore[return-value]


def _parse_positive_int(raw: str, field_name: str) -> int:
    value = _parse_int(raw, field_name)
    if value <= 0:
        raise ConfigError(f"{field_name} must be greater than zero.")
    return value


def _parse_int(raw: str, field_name: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{field_name} must be an integer.") from exc


def _parse_bool(raw: str, field_name: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{field_name} must be a boolean string (true/false).")


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _require_non_empty(env: Mapping[str, str], key: str, default: str | None = None) -> str:
    if default is not None:
        value = env.get(key, default)
    else:
        value = env.get(key, "")
    cleaned = value.strip()
    if not cleaned:
        raise ConfigError(f"{key} is required and must be non-empty.")
    return cleaned
