from __future__ import annotations

from datetime import datetime
import fcntl
from functools import lru_cache
import os
from pathlib import Path
import shutil
import subprocess
import wave
import time
from typing import TypedDict

from .config import (
    BackendName,
    ConfigError,
    DEFAULT_KOKORO_DEFAULT_VOICE,
    DEFAULT_KOKORO_MODEL_PATH,
    DEFAULT_KOKORO_VOICES_PATH,
    DEFAULT_KOKORO_ZH_DEFAULT_VOICE,
    DEFAULT_KOKORO_ZH_MODEL_PATH,
    DEFAULT_KOKORO_ZH_VOCAB_CONFIG_PATH,
    DEFAULT_KOKORO_ZH_VOICES_PATH,
    TtsSettings,
    model_requires_instruct,
)
from .platform import BackendSelectionError, select_backend
from .version_check import check_backend_runtime_version


class SpeakResult(TypedDict):
    ok: bool
    backend: BackendName | None
    platform: str
    machine: str
    command: list[str]
    output_path: str | None
    played: bool
    playback_command: list[str] | None
    warnings: list[str]
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    error_type: str | None
    error_message: str | None


class _OutputSignature(TypedDict):
    size: int
    mtime_ns: int


class _ResolvedOutputPath(TypedDict):
    path: Path
    is_auto_generated: bool


_GLOBAL_LOCK_FILE = Path("/tmp/tts_mcp_global_generation.lock")
_KOKORO_LANGUAGE_ALIASES: dict[str, str] = {
    "zh": "cmn",
    "zh-cn": "cmn",
    "zh-hans": "cmn",
    "zh_cn": "cmn",
    "zh_hans": "cmn",
    "mandarin": "cmn",
}


class _KokoroRuntimeConfig(TypedDict):
    model_path: str
    voices_path: str
    vocab_config_path: str | None
    selected_voice: str


def run_speak(
    settings: TtsSettings,
    text: str,
    output_path: str | None = None,
    play: bool = True,
    voice: str | None = None,
    speed: float = 1.0,
    language_code: str | None = None,
    preferred_backend: BackendName | None = None,
    instruct: str | None = None,
) -> SpeakResult:
    normalized_text = text.strip()
    if not normalized_text:
        return _error_result(
            error_type="validation",
            error_message="text cannot be empty.",
        )
    if speed <= 0:
        return _error_result(
            error_type="validation",
            error_message="speed must be greater than zero.",
        )

    requested_instruct = _normalize_optional_text(instruct)

    try:
        selection = select_backend(settings=settings, preferred_backend=preferred_backend)
    except BackendSelectionError as exc:
        return _error_result(
            error_type=exc.error_type,
            error_message=str(exc),
        )

    try:
        resolved_output_info = _resolve_output_path(output_path, settings.output_dir)
    except ConfigError as exc:
        return _error_result(
            backend=selection.backend,
            platform_name=selection.host.system,
            machine=selection.host.machine,
            error_type="validation",
            error_message=str(exc),
        )
    resolved_output = resolved_output_info["path"]
    auto_generated_output = resolved_output_info["is_auto_generated"]

    if selection.backend == "mlx_audio":
        effective_instruct = requested_instruct or settings.mlx_default_instruct

        if model_requires_instruct(settings.mlx_model) and not effective_instruct:
            return _error_result(
                backend=selection.backend,
                platform_name=selection.host.system,
                machine=selection.host.machine,
                error_type="validation",
                error_message=(
                    "Configured MLX model requires instruct. Set MLX_TTS_DEFAULT_INSTRUCT "
                    "in MCP config or pass instruct in speak()."
                ),
            )

        try:
            command = _build_mlx_command(
                settings=settings,
                text=normalized_text,
                output_path=resolved_output,
                play=play,
                voice=voice,
                speed=speed,
                language_code=language_code,
                instruct=effective_instruct,
            )
        except ConfigError as exc:
            return _error_result(
                backend=selection.backend,
                platform_name=selection.host.system,
                machine=selection.host.machine,
                error_type="config",
                error_message=str(exc),
            )
    elif selection.backend == "llama_cpp":
        if requested_instruct:
            return _error_result(
                backend=selection.backend,
                platform_name=selection.host.system,
                machine=selection.host.machine,
                error_type="validation",
                error_message="instruct is currently supported only for mlx_audio backend.",
            )

        try:
            command = _build_llama_command(
                settings=settings,
                text=normalized_text,
                output_path=resolved_output,
            )
        except ConfigError as exc:
            return _error_result(
                backend=selection.backend,
                platform_name=selection.host.system,
                machine=selection.host.machine,
                error_type="config",
                error_message=str(exc),
            )
    elif selection.backend == "kokoro_onnx":
        if requested_instruct:
            return _error_result(
                backend=selection.backend,
                platform_name=selection.host.system,
                machine=selection.host.machine,
                error_type="validation",
                error_message="instruct is currently supported only for mlx_audio backend.",
            )
        command = ["kokoro_onnx.generate", str(resolved_output)]
    else:
        return _error_result(
            error_type="validation",
            error_message=f"Unsupported backend selected: {selection.backend}",
        )

    warnings: list[str] = []

    version_status = check_backend_runtime_version(
        backend=selection.backend,
        command=selection.command,
        timeout_seconds=settings.version_check_timeout_seconds,
    )
    if settings.enforce_latest_runtime and version_status["status"] != "latest":
        return _error_result(
            backend=selection.backend,
            platform_name=selection.host.system,
            machine=selection.host.machine,
            error_type="dependency",
            error_message=version_status["message"],
        )
    if version_status["status"] == "outdated":
        warnings.append(version_status["message"])
    elif version_status["status"] == "unknown":
        warnings.append(version_status["message"])

    before_signature = _output_signature(resolved_output)
    generation_env: dict[str, str] | None = None
    if selection.backend == "mlx_audio":
        generation_env = _resolve_mlx_subprocess_env(settings=settings)

    lock_fd = _acquire_global_generation_lock(
        timeout_seconds=settings.process_lock_timeout_seconds
    )
    if lock_fd is None:
        return _error_result(
            backend=selection.backend,
            platform_name=selection.host.system,
            machine=selection.host.machine,
            error_type="busy",
            error_message=(
                "Another speech generation is already running. "
                "Try again in a few seconds."
            ),
        )

    try:
        if selection.backend == "kokoro_onnx":
            generation = _run_kokoro_onnx(
                settings=settings,
                text=normalized_text,
                output_path=resolved_output,
                voice=voice,
                speed=speed,
                language_code=language_code,
            )
        else:
            generation = _execute(
                command=command,
                timeout_seconds=settings.timeout_seconds,
                env_overrides=generation_env,
            )
        if generation["exit_code"] != 0:
            return _error_result(
                backend=selection.backend,
                platform_name=selection.host.system,
                machine=selection.host.machine,
                command=command,
                output_path=resolved_output,
                stdout=generation["stdout"],
                stderr=generation["stderr"],
                exit_code=generation["exit_code"],
                error_type=generation["error_type"] or "execution",
                error_message=generation["error_message"] or "Speech command failed.",
            )

        played = False
        playback_command: list[str] | None = None

        after_signature = _output_signature(resolved_output)
        if after_signature is None or after_signature["size"] <= 44:
            return _error_result(
                backend=selection.backend,
                platform_name=selection.host.system,
                machine=selection.host.machine,
                command=command,
                output_path=resolved_output,
                stdout=generation["stdout"],
                stderr=generation["stderr"],
                exit_code=generation["exit_code"],
                error_type="execution",
                error_message=(
                    "Speech command completed but no valid WAV output was produced at "
                    f"{resolved_output}."
                ),
            )
        if before_signature is not None and before_signature == after_signature:
            return _error_result(
                backend=selection.backend,
                platform_name=selection.host.system,
                machine=selection.host.machine,
                command=command,
                output_path=resolved_output,
                stdout=generation["stdout"],
                stderr=generation["stderr"],
                exit_code=generation["exit_code"],
                error_type="execution",
                error_message=(
                    "Speech command completed, but output file was not updated. "
                    f"Expected a newly generated WAV at {resolved_output}."
                ),
            )

        if play and selection.backend in {"llama_cpp", "kokoro_onnx"} and resolved_output.exists():
            playback_command = _build_linux_play_command(
                audio_path=resolved_output,
                linux_player=settings.linux_player,
            )
            if playback_command is None:
                warnings.append(
                    "Audio generation succeeded, but no Linux audio player is available "
                    "(tried ffplay/aplay/paplay)."
                )
            else:
                playback = _execute(command=playback_command, timeout_seconds=45)
                if _linux_playback_confirmed(playback_command, playback):
                    played = True
                else:
                    warnings.append(
                        "Audio generation succeeded, but playback command failed."
                    )

        if play and selection.backend == "mlx_audio":
            if _mlx_playback_confirmed(generation):
                played = True
            else:
                warnings.append(
                    "Audio generation succeeded, but MLX playback could not be confirmed "
                    "from command output. Check your default audio output device."
                )

        if auto_generated_output and settings.delete_auto_output:
            try:
                resolved_output.unlink(missing_ok=True)
            except OSError:
                warnings.append(
                    f"Generated audio cleanup failed for {resolved_output}."
                )

        return SpeakResult(
            ok=True,
            backend=selection.backend,
            platform=selection.host.system,
            machine=selection.host.machine,
            command=command,
            output_path=str(resolved_output),
            played=played,
            playback_command=playback_command,
            warnings=warnings,
            stdout=generation["stdout"],
            stderr=generation["stderr"],
            exit_code=generation["exit_code"],
            error_type=None,
            error_message=None,
        )
    finally:
        _release_global_generation_lock(lock_fd)


def _build_mlx_command(
    settings: TtsSettings,
    text: str,
    output_path: Path,
    play: bool,
    voice: str | None,
    speed: float,
    language_code: str | None,
    instruct: str | None,
) -> list[str]:
    chosen_voice = (voice or settings.mlx_default_voice or "").strip() or None
    lang = _resolve_mlx_language_code(
        model_id=settings.mlx_model,
        language_code=language_code,
        default_language_code=settings.mlx_default_language_code,
    )
    file_prefix = str(output_path.with_suffix(""))

    command = [
        settings.mlx_command,
        "--model",
        settings.mlx_model,
        "--text",
        text,
        "--lang_code",
        lang,
        "--speed",
        str(speed),
        "--file_prefix",
        file_prefix,
        "--audio_format",
        "wav",
        "--join_audio",
    ]

    if chosen_voice:
        command.extend(["--voice", chosen_voice])
    if instruct:
        if not _mlx_supports_flag(settings.mlx_command, "--instruct"):
            raise ConfigError(
                "Configured MLX command does not support --instruct. "
                "Upgrade mlx-audio or switch to a non-VoiceDesign model."
            )
        command.extend(["--instruct", instruct])
    if play:
        command.append("--play")

    return command


def _build_llama_command(
    settings: TtsSettings,
    text: str,
    output_path: Path,
) -> list[str]:
    command = [
        settings.llama_command,
        "-p",
        text,
        "-o",
        str(output_path),
        "--n-gpu-layers",
        str(settings.llama_n_gpu_layers),
    ]

    if settings.llama_model_path:
        if not settings.llama_vocoder_path:
            raise ConfigError("llama vocoder model path is required when model path is set.")
        command.extend(["-m", settings.llama_model_path, "-mv", settings.llama_vocoder_path])
    elif settings.llama_use_oute_default:
        command.append("--tts-oute-default")
    else:
        raise ConfigError(
            "No llama.cpp model configured. Enable LLAMA_TTS_USE_OUTE_DEFAULT or set model paths."
        )

    return command


def _run_kokoro_onnx(
    settings: TtsSettings,
    text: str,
    output_path: Path,
    voice: str | None,
    speed: float,
    language_code: str | None,
) -> _ExecutionResult:
    try:
        import numpy as np  # type: ignore
    except Exception as exc:
        return _ExecutionResult(
            stdout=None,
            stderr=None,
            exit_code=None,
            error_type="dependency",
            error_message=f"numpy dependency is unavailable for kokoro_onnx backend: {exc}",
        )

    selected_language = _resolve_kokoro_language_code(
        language_code=language_code,
        default_language_code=settings.kokoro_default_language_code,
    )
    runtime_config = _resolve_kokoro_runtime_config(
        settings=settings,
        selected_language=selected_language,
        requested_voice=voice,
    )

    try:
        kokoro = _load_kokoro_runtime(
            model_path=_resolve_runtime_path(runtime_config["model_path"]),
            voices_path=_resolve_runtime_path(runtime_config["voices_path"]),
            vocab_config_path=(
                _resolve_runtime_path(runtime_config["vocab_config_path"])
                if runtime_config["vocab_config_path"]
                else None
            ),
        )
    except Exception as exc:
        return _ExecutionResult(
            stdout=None,
            stderr=None,
            exit_code=None,
            error_type="dependency",
            error_message=str(exc),
        )

    selected_voice = runtime_config["selected_voice"]
    use_misaki_zh = _should_use_kokoro_misaki_zh(
        selected_language=selected_language,
        vocab_config_path=runtime_config["vocab_config_path"],
    )

    synthesis_text = text
    create_kwargs: dict[str, object] = {}
    if use_misaki_zh:
        try:
            g2p = _load_misaki_zh_g2p(version=settings.kokoro_misaki_zh_version)
        except Exception as exc:
            return _ExecutionResult(
                stdout=None,
                stderr=None,
                exit_code=None,
                error_type="dependency",
                error_message=str(exc),
            )
        synthesis_text, _ = g2p(text)
        create_kwargs["is_phonemes"] = True
    else:
        create_kwargs["lang"] = selected_language

    try:
        samples, sample_rate = kokoro.create(
            text=synthesis_text,
            voice=selected_voice,
            speed=speed,
            **create_kwargs,
        )
        audio = np.asarray(samples, dtype=np.float32)
        audio = np.clip(audio, -1.0, 1.0)
        pcm16 = (audio * 32767.0).astype(np.int16)

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(sample_rate))
            wav_file.writeframes(pcm16.tobytes())
    except Exception as exc:
        return _ExecutionResult(
            stdout=None,
            stderr=None,
            exit_code=1,
            error_type="execution",
            error_message=f"Kokoro generation failed: {exc}",
        )

    return _ExecutionResult(
        stdout=(
            f"kokoro_onnx generated voice={selected_voice} lang={selected_language} "
            f"misaki_zh={use_misaki_zh}"
        ),
        stderr=None,
        exit_code=0,
        error_type=None,
        error_message=None,
    )


@lru_cache(maxsize=4)
def _load_kokoro_runtime(
    model_path: Path,
    voices_path: Path,
    vocab_config_path: Path | None,
):
    if not model_path.exists():
        raise RuntimeError(
            f"Kokoro model file not found: {model_path}. "
            "Run scripts/install_kokoro_onnx_linux.sh or set KOKORO_TTS_MODEL_PATH."
        )
    if not voices_path.exists():
        raise RuntimeError(
            f"Kokoro voices file not found: {voices_path}. "
            "Run scripts/install_kokoro_onnx_linux.sh or set KOKORO_TTS_VOICES_PATH."
        )
    if vocab_config_path is not None and not vocab_config_path.exists():
        raise RuntimeError(
            f"Kokoro vocab config file not found: {vocab_config_path}. "
            "Set KOKORO_TTS_VOCAB_CONFIG_PATH to a valid file path."
        )

    try:
        from kokoro_onnx import Kokoro  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "kokoro-onnx package is not installed. "
            "Install with: pip install --upgrade kokoro-onnx"
        ) from exc

    kwargs: dict[str, str] = {}
    if vocab_config_path is not None:
        kwargs["vocab_config"] = str(vocab_config_path)
    return Kokoro(str(model_path), str(voices_path), **kwargs)


def _resolve_kokoro_runtime_config(
    settings: TtsSettings,
    selected_language: str,
    requested_voice: str | None,
) -> _KokoroRuntimeConfig:
    normalized_voice = _normalize_optional_text(requested_voice)
    if normalized_voice:
        selected_voice = normalized_voice
    else:
        selected_voice = settings.kokoro_default_voice

    default_paths_in_use = (
        settings.kokoro_model_path == DEFAULT_KOKORO_MODEL_PATH
        and settings.kokoro_voices_path == DEFAULT_KOKORO_VOICES_PATH
        and settings.kokoro_vocab_config_path is None
    )
    language_is_chinese = selected_language.strip().lower() in {"cmn", "z"}

    if language_is_chinese and default_paths_in_use:
        if normalized_voice is None and settings.kokoro_default_voice == DEFAULT_KOKORO_DEFAULT_VOICE:
            selected_voice = DEFAULT_KOKORO_ZH_DEFAULT_VOICE
        return _KokoroRuntimeConfig(
            model_path=DEFAULT_KOKORO_ZH_MODEL_PATH,
            voices_path=DEFAULT_KOKORO_ZH_VOICES_PATH,
            vocab_config_path=DEFAULT_KOKORO_ZH_VOCAB_CONFIG_PATH,
            selected_voice=selected_voice,
        )

    auto_vocab_for_zh_profile = (
        language_is_chinese
        and settings.kokoro_vocab_config_path is None
        and settings.kokoro_model_path == DEFAULT_KOKORO_ZH_MODEL_PATH
        and settings.kokoro_voices_path == DEFAULT_KOKORO_ZH_VOICES_PATH
    )
    return _KokoroRuntimeConfig(
        model_path=settings.kokoro_model_path,
        voices_path=settings.kokoro_voices_path,
        vocab_config_path=(
            DEFAULT_KOKORO_ZH_VOCAB_CONFIG_PATH
            if auto_vocab_for_zh_profile
            else settings.kokoro_vocab_config_path
        ),
        selected_voice=selected_voice,
    )


def _should_use_kokoro_misaki_zh(
    selected_language: str,
    vocab_config_path: str | None,
) -> bool:
    return bool(vocab_config_path) and selected_language.strip().lower() in {"cmn", "z"}


@lru_cache(maxsize=2)
def _load_misaki_zh_g2p(version: str):
    try:
        from misaki import zh  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "misaki-fork[zh] package is not installed for Kokoro Chinese phonemization. "
            "Install with: pip install --upgrade 'misaki-fork[zh]'"
        ) from exc

    return zh.ZHG2P(version=version)


def _resolve_runtime_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    root_dir = Path(__file__).resolve().parents[2]
    return (root_dir / path).resolve(strict=False)


def _resolve_output_path(candidate: str | None, default_output_dir: str) -> _ResolvedOutputPath:
    is_auto_generated = candidate is None
    if candidate is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_path = Path(default_output_dir) / f"speak_{timestamp}.wav"
    else:
        raw_path = Path(candidate).expanduser()

    if not raw_path.is_absolute():
        raw_path = Path.cwd() / raw_path

    if raw_path.suffix == "":
        raw_path = raw_path.with_suffix(".wav")
    if raw_path.suffix.lower() != ".wav":
        raise ConfigError("output_path must end with .wav")

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    return _ResolvedOutputPath(
        path=raw_path.resolve(strict=False),
        is_auto_generated=is_auto_generated,
    )


def _build_linux_play_command(
    audio_path: Path,
    linux_player: str,
) -> list[str] | None:
    if linux_player == "none":
        return None

    candidates: list[tuple[str, list[str]]]
    if linux_player == "ffplay":
        candidates = [("ffplay", ["-nodisp", "-autoexit", str(audio_path)])]
    elif linux_player == "aplay":
        candidates = [("aplay", [str(audio_path)])]
    elif linux_player == "paplay":
        candidates = [("paplay", [str(audio_path)])]
    else:
        candidates = [
            ("ffplay", ["-nodisp", "-autoexit", str(audio_path)]),
            ("aplay", [str(audio_path)]),
            ("paplay", [str(audio_path)]),
        ]

    for binary, args in candidates:
        if shutil.which(binary):
            return [binary, *args]
    return None


class _ExecutionResult(TypedDict):
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    error_type: str | None
    error_message: str | None


def _execute(
    command: list[str],
    timeout_seconds: int,
    env_overrides: dict[str, str] | None = None,
) -> _ExecutionResult:
    merged_env = None
    if env_overrides:
        merged_env = os.environ.copy()
        merged_env.update(env_overrides)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=merged_env,
        )
    except FileNotFoundError:
        return _ExecutionResult(
            stdout=None,
            stderr=None,
            exit_code=None,
            error_type="dependency",
            error_message=f"Command not found: {command[0]}",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.output if isinstance(exc.output, str) else None
        stderr = exc.stderr if isinstance(exc.stderr, str) else None
        return _ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=None,
            error_type="timeout",
            error_message=f"Command timed out after {timeout_seconds} seconds.",
        )
    except OSError as exc:
        return _ExecutionResult(
            stdout=None,
            stderr=None,
            exit_code=None,
            error_type="execution",
            error_message=f"Failed to execute command: {exc}",
        )

    return _ExecutionResult(
        stdout=_clean_output(completed.stdout),
        stderr=_clean_output(completed.stderr),
        exit_code=completed.returncode,
        error_type=None,
        error_message=None,
    )


def _linux_playback_confirmed(
    command: list[str],
    playback: _ExecutionResult,
) -> bool:
    if playback["exit_code"] != 0:
        return False

    binary = Path(command[0]).name.lower()
    if binary == "ffplay":
        combined = f"{playback['stdout'] or ''}\n{playback['stderr'] or ''}".lower()
        ffplay_failure_markers = (
            "audio open failed",
            "failed to open file",
            "configure filtergraph",
        )
        if any(marker in combined for marker in ffplay_failure_markers):
            return False

    return True


def _clean_output(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _resolve_mlx_subprocess_env(settings: TtsSettings) -> dict[str, str] | None:
    mode = settings.hf_hub_offline_mode
    if mode == "true":
        return {"HF_HUB_OFFLINE": "1"}
    if mode == "false":
        return None
    if _is_hf_model_cached(settings.mlx_model):
        return {"HF_HUB_OFFLINE": "1"}
    return None


def _acquire_global_generation_lock(timeout_seconds: int) -> int | None:
    _GLOBAL_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(_GLOBAL_LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout_seconds

    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(0.1)
        except OSError:
            os.close(fd)
            return None


def _release_global_generation_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@lru_cache(maxsize=32)
def _is_hf_model_cached(model_id: str) -> bool:
    if not _looks_like_hf_repo_id(model_id):
        return False

    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    model_cache_dir = cache_root / f"models--{model_id.replace('/', '--')}"
    snapshots_dir = model_cache_dir / "snapshots"
    if not snapshots_dir.exists():
        return False

    try:
        return any(child.is_dir() for child in snapshots_dir.iterdir())
    except OSError:
        return False


def _looks_like_hf_repo_id(value: str) -> bool:
    # Hugging Face repo IDs are like "org/name"; local paths are handled separately.
    if "://" in value:
        return False
    if value.startswith("/") or value.startswith("./") or value.startswith("../"):
        return False
    return value.count("/") == 1


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _mlx_playback_confirmed(generation: _ExecutionResult) -> bool:
    combined = f"{generation['stdout'] or ''}\n{generation['stderr'] or ''}".lower()
    markers = (
        "starting audio stream",
        "audio stream started",
    )
    return any(marker in combined for marker in markers)


def _resolve_mlx_language_code(
    model_id: str,
    language_code: str | None,
    default_language_code: str,
) -> str:
    resolved = (language_code or default_language_code).strip()
    if model_id == "mlx-community/Kokoro-82M-bf16" and resolved.lower() == "en":
        return "a"
    return resolved


def _resolve_kokoro_language_code(
    language_code: str | None,
    default_language_code: str,
) -> str:
    resolved = (language_code or default_language_code).strip()
    normalized = resolved.lower().replace("_", "-")
    return _KOKORO_LANGUAGE_ALIASES.get(normalized, resolved)


def _output_signature(path: Path) -> _OutputSignature | None:
    if not path.exists():
        return None

    stat = path.stat()
    return _OutputSignature(size=stat.st_size, mtime_ns=stat.st_mtime_ns)


@lru_cache(maxsize=8)
def _mlx_supports_flag(command: str, flag: str) -> bool:
    try:
        completed = subprocess.run(
            [command, "-h"],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False

    help_text = f"{completed.stdout}\n{completed.stderr}"
    return flag in help_text


def _error_result(
    error_type: str,
    error_message: str,
    *,
    backend: BackendName | None = None,
    platform_name: str = "unknown",
    machine: str = "unknown",
    command: list[str] | None = None,
    output_path: Path | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    exit_code: int | None = None,
) -> SpeakResult:
    return SpeakResult(
        ok=False,
        backend=backend,
        platform=platform_name,
        machine=machine,
        command=command or [],
        output_path=str(output_path) if output_path else None,
        played=False,
        playback_command=None,
        warnings=[],
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        error_type=error_type,
        error_message=error_message,
    )
