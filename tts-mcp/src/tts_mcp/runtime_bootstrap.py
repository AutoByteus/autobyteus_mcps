from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys

from .config import TtsSettings
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
        if (
            not _python_module_available("kokoro_onnx")
            or not _kokoro_assets_available(root_dir=root_dir, settings=settings)
        ):
            _run_install_script(root_dir / "scripts" / "install_kokoro_onnx_linux.sh")
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
    model_path = _resolve_runtime_path(root_dir, settings.kokoro_model_path)
    voices_path = _resolve_runtime_path(root_dir, settings.kokoro_voices_path)
    return model_path.exists() and voices_path.exists()


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
