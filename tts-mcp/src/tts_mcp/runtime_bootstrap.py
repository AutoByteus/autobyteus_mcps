from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys

from .config import (
    DEFAULT_KOKORO_DEFAULT_LANGUAGE_CODE,
    DEFAULT_KOKORO_MODEL_PATH,
    DEFAULT_KOKORO_VOICES_PATH,
    DEFAULT_KOKORO_ZH_MODEL_PATH,
    DEFAULT_KOKORO_ZH_VOCAB_CONFIG_PATH,
    DEFAULT_KOKORO_ZH_VOICES_PATH,
    TtsSettings,
)
from .platform import detect_host


def bootstrap_runtime(settings: TtsSettings) -> list[str]:
    if not settings.auto_install_runtime:
        return []

    notes: list[str] = []
    root_dir = Path(__file__).resolve().parents[2]
    host = detect_host()

    mlx_bin_dir = root_dir / ".venv-mlx" / "bin"
    llama_bin_dir = root_dir / ".tools" / "llama-current"

    if host.is_macos_arm64 and settings.default_backend in {"auto", "mlx_audio"}:
        _prepend_path(mlx_bin_dir)
        if shutil.which(settings.mlx_command) is None:
            _run_install_script(root_dir / "scripts" / "install_mlx_audio_macos.sh")
            _prepend_path(mlx_bin_dir)
            notes.append("Installed MLX runtime automatically.")

    linux_target_runtime = _linux_runtime_target(settings)

    if host.is_linux and linux_target_runtime == "llama_cpp":
        _prepend_path(llama_bin_dir)
        if shutil.which(settings.llama_command) is None:
            _run_install_script(root_dir / "scripts" / "install_llama_tts_linux.sh")
            _prepend_path(llama_bin_dir)
            notes.append("Installed llama-tts runtime automatically.")

    if host.is_linux and linux_target_runtime == "kokoro_onnx":
        kokoro_profile = _resolve_kokoro_install_profile(settings)
        if (
            not _python_module_available("kokoro_onnx")
            or not _kokoro_assets_available(root_dir=root_dir, settings=settings)
        ):
            _run_install_script_with_env(
                root_dir / "scripts" / "install_kokoro_onnx_linux.sh",
                {"KOKORO_TTS_PROFILE": kokoro_profile},
            )
            notes.append("Installed Kokoro ONNX runtime automatically.")

    if host.is_macos_arm64 and settings.auto_install_llama_on_macos:
        _prepend_path(llama_bin_dir)
        if shutil.which(settings.llama_command) is None:
            _run_install_script(root_dir / "scripts" / "install_llama_tts_macos.sh")
            _prepend_path(llama_bin_dir)
            notes.append("Installed optional macOS llama-tts runtime automatically.")

    return notes


def _linux_runtime_target(settings: TtsSettings) -> str | None:
    if settings.default_backend == "llama_cpp":
        return "llama_cpp"
    if settings.default_backend == "kokoro_onnx":
        return "kokoro_onnx"
    if settings.default_backend == "auto":
        return settings.linux_runtime
    return None


def _kokoro_assets_available(root_dir: Path, settings: TtsSettings) -> bool:
    model_path_value, voices_path_value, vocab_path_value = _resolve_kokoro_assets(settings)
    model_path = _resolve_runtime_path(root_dir, model_path_value)
    voices_path = _resolve_runtime_path(root_dir, voices_path_value)
    if not (model_path.exists() and voices_path.exists()):
        return False

    if vocab_path_value:
        vocab_config_path = _resolve_runtime_path(root_dir, vocab_path_value)
        return vocab_config_path.exists()

    return True


def _resolve_kokoro_install_profile(settings: TtsSettings) -> str:
    if _should_use_kokoro_zh_defaults(settings):
        return "zh_v1_1"
    return "v1_0"


def _resolve_kokoro_assets(settings: TtsSettings) -> tuple[str, str, str | None]:
    if _should_use_kokoro_zh_defaults(settings):
        return (
            DEFAULT_KOKORO_ZH_MODEL_PATH,
            DEFAULT_KOKORO_ZH_VOICES_PATH,
            DEFAULT_KOKORO_ZH_VOCAB_CONFIG_PATH,
        )

    auto_vocab_for_zh_profile = (
        _normalize_kokoro_lang(settings.kokoro_default_language_code) in {"cmn", "z"}
        and settings.kokoro_vocab_config_path is None
        and settings.kokoro_model_path == DEFAULT_KOKORO_ZH_MODEL_PATH
        and settings.kokoro_voices_path == DEFAULT_KOKORO_ZH_VOICES_PATH
    )
    vocab_path = (
        DEFAULT_KOKORO_ZH_VOCAB_CONFIG_PATH
        if auto_vocab_for_zh_profile
        else settings.kokoro_vocab_config_path
    )
    return (settings.kokoro_model_path, settings.kokoro_voices_path, vocab_path)


def _should_use_kokoro_zh_defaults(settings: TtsSettings) -> bool:
    return (
        _normalize_kokoro_lang(settings.kokoro_default_language_code) in {"cmn", "z"}
        and settings.kokoro_model_path == DEFAULT_KOKORO_MODEL_PATH
        and settings.kokoro_voices_path == DEFAULT_KOKORO_VOICES_PATH
        and settings.kokoro_vocab_config_path is None
    )


def _normalize_kokoro_lang(value: str) -> str:
    normalized = (value or DEFAULT_KOKORO_DEFAULT_LANGUAGE_CODE).strip().lower().replace("_", "-")
    aliases = {
        "zh": "cmn",
        "zh-cn": "cmn",
        "zh-hans": "cmn",
        "mandarin": "cmn",
    }
    return aliases.get(normalized, normalized)


def _resolve_runtime_path(root_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return root_dir / path


def _python_module_available(module_name: str) -> bool:
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _prepend_path(directory: Path) -> None:
    path_value = str(directory)
    current_path = os.environ.get("PATH", "")
    entries = current_path.split(":") if current_path else []
    if path_value in entries:
        return
    os.environ["PATH"] = f"{path_value}:{current_path}" if current_path else path_value


def _run_install_script(script_path: Path) -> None:
    if not script_path.exists():
        raise RuntimeError(f"Missing installer script: {script_path}")

    env = os.environ.copy()
    env.setdefault("PYTHON_BIN", sys.executable)

    completed = subprocess.run(
        [str(script_path)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        output = "\n".join(
            [
                part.strip()
                for part in (completed.stdout, completed.stderr)
                if part and part.strip()
            ]
        )
        raise RuntimeError(
            f"Runtime auto-install failed via {script_path.name} (exit {completed.returncode}). "
            f"{output}"
        )


def _run_install_script_with_env(script_path: Path, extra_env: dict[str, str]) -> None:
    previous: dict[str, str | None] = {
        key: os.environ.get(key)
        for key in extra_env
    }
    os.environ.update(extra_env)
    try:
        _run_install_script(script_path)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
