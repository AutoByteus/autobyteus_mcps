from __future__ import annotations

from dataclasses import dataclass
import platform
import shutil
import subprocess
from typing import Callable

from .config import BackendName, TtsSettings


@dataclass(frozen=True, slots=True)
class HostInfo:
    system: str
    machine: str
    is_macos_arm64: bool
    is_linux: bool
    has_nvidia: bool


@dataclass(frozen=True, slots=True)
class BackendSelection:
    backend: BackendName
    command: str
    host: HostInfo


class BackendSelectionError(RuntimeError):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type


def detect_host() -> HostInfo:
    raw_system = platform.system().strip()
    raw_machine = platform.machine().strip().lower()

    system = raw_system.lower()
    is_macos_arm64 = system == "darwin" and raw_machine in {"arm64", "aarch64"}
    is_linux = system == "linux"
    has_nvidia = is_linux and _has_nvidia_gpu()

    return HostInfo(
        system=raw_system,
        machine=raw_machine,
        is_macos_arm64=is_macos_arm64,
        is_linux=is_linux,
        has_nvidia=has_nvidia,
    )


def select_backend(
    settings: TtsSettings,
    preferred_backend: BackendName | None = None,
    host: HostInfo | None = None,
    command_resolver: Callable[[str], str | None] | None = None,
) -> BackendSelection:
    actual_host = host or detect_host()
    resolve_command = command_resolver or shutil.which

    requested = preferred_backend or settings.default_backend
    backend: BackendName

    if requested == "auto":
        if actual_host.is_macos_arm64:
            backend = "mlx_audio"
        elif actual_host.is_linux:
            if settings.linux_runtime == "kokoro_onnx":
                backend = "kokoro_onnx"
            elif actual_host.has_nvidia:
                backend = "llama_cpp"
            else:
                raise BackendSelectionError(
                    "unsupported_platform",
                    "Auto backend selection for Linux with TTS_MCP_LINUX_RUNTIME=llama_cpp "
                    "requires NVIDIA GPU availability. Set TTS_MCP_LINUX_RUNTIME=kokoro_onnx "
                    "for CPU Kokoro runtime.",
                )
        else:
            raise BackendSelectionError(
                "unsupported_platform",
                "Auto backend selection supports Apple Silicon macOS (MLX Audio) and Linux "
                "runtime policy (llama.cpp or Kokoro ONNX).",
            )
    else:
        backend = requested

    if backend == "mlx_audio":
        if not actual_host.is_macos_arm64:
            raise BackendSelectionError(
                "unsupported_platform",
                "mlx_audio backend requires Apple Silicon macOS.",
            )
        command = settings.mlx_command
    elif backend == "llama_cpp":
        if not actual_host.is_linux or not actual_host.has_nvidia:
            raise BackendSelectionError(
                "unsupported_platform",
                "llama_cpp backend requires Linux with NVIDIA GPU availability.",
            )
        command = settings.llama_command
    elif backend == "kokoro_onnx":
        if not actual_host.is_linux:
            raise BackendSelectionError(
                "unsupported_platform",
                "kokoro_onnx backend currently supports Linux hosts only.",
            )
        command = "kokoro_onnx"
    else:
        raise BackendSelectionError("validation", f"Unsupported backend value: {backend}")

    if backend in {"mlx_audio", "llama_cpp"} and resolve_command(command) is None:
        raise BackendSelectionError(
            "dependency",
            f"Required command '{command}' is not available in PATH.",
        )

    return BackendSelection(backend=backend, command=command, host=actual_host)


def _has_nvidia_gpu() -> bool:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False

    return completed.returncode == 0
