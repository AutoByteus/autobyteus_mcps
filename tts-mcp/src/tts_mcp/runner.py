from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess
from typing import TypedDict

from .config import BackendName, ConfigError, TtsSettings, model_requires_instruct
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
        resolved_output = _resolve_output_path(output_path, settings.output_dir)
    except ConfigError as exc:
        return _error_result(
            backend=selection.backend,
            platform_name=selection.host.system,
            machine=selection.host.machine,
            error_type="validation",
            error_message=str(exc),
        )

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

    generation = _execute(command=command, timeout_seconds=settings.timeout_seconds)
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

    if play and selection.backend == "llama_cpp" and resolved_output.exists():
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
            if playback["exit_code"] == 0:
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


def _resolve_output_path(candidate: str | None, default_output_dir: str) -> Path:
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
    return raw_path.resolve(strict=False)


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


def _execute(command: list[str], timeout_seconds: int) -> _ExecutionResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
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


def _clean_output(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


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
