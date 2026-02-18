from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Literal, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import BackendName


class RuntimeVersionResult(TypedDict):
    status: Literal["latest", "outdated", "unknown"]
    local_version: str | None
    latest_version: str | None
    message: str


@lru_cache(maxsize=32)
def check_backend_runtime_version(
    backend: BackendName,
    command: str,
    timeout_seconds: int,
) -> RuntimeVersionResult:
    if backend == "mlx_audio":
        return _check_mlx_audio_runtime(command=command, timeout_seconds=timeout_seconds)
    if backend == "llama_cpp":
        return _check_llama_cpp_runtime(command=command, timeout_seconds=timeout_seconds)
    if backend == "kokoro_onnx":
        return _check_kokoro_runtime(timeout_seconds=timeout_seconds)

    return RuntimeVersionResult(
        status="unknown",
        local_version=None,
        latest_version=None,
        message=f"Unsupported backend for version check: {backend}.",
    )


def _check_mlx_audio_runtime(command: str, timeout_seconds: int) -> RuntimeVersionResult:
    local_version = _detect_mlx_audio_local_version(command=command, timeout_seconds=timeout_seconds)
    latest_version = _fetch_latest_pypi_version("mlx-audio", timeout_seconds=timeout_seconds)

    if not local_version:
        return RuntimeVersionResult(
            status="unknown",
            local_version=None,
            latest_version=latest_version,
            message=(
                "Could not detect local mlx-audio version from MLX command environment. "
                "Ensure MLX_TTS_COMMAND points to a valid mlx-audio installation."
            ),
        )
    if not latest_version:
        return RuntimeVersionResult(
            status="unknown",
            local_version=local_version,
            latest_version=None,
            message="Could not fetch latest mlx-audio version from PyPI.",
        )
    if local_version == latest_version:
        return RuntimeVersionResult(
            status="latest",
            local_version=local_version,
            latest_version=latest_version,
            message=f"mlx-audio is up to date ({local_version}).",
        )

    return RuntimeVersionResult(
        status="outdated",
        local_version=local_version,
        latest_version=latest_version,
        message=(
            f"mlx-audio is outdated: local={local_version}, latest={latest_version}. "
            "Upgrade with: pip install --upgrade 'mlx-audio[tts]'"
        ),
    )


def _check_llama_cpp_runtime(command: str, timeout_seconds: int) -> RuntimeVersionResult:
    local_version = _detect_command_version(command=command, timeout_seconds=timeout_seconds)
    latest_version = _fetch_latest_llama_cpp_release(timeout_seconds=timeout_seconds)

    if not local_version:
        return RuntimeVersionResult(
            status="unknown",
            local_version=None,
            latest_version=latest_version,
            message=f"Could not read local version from command '{command}'.",
        )
    if not latest_version:
        return RuntimeVersionResult(
            status="unknown",
            local_version=local_version,
            latest_version=None,
            message="Could not fetch latest llama.cpp release from GitHub.",
        )

    local_build = _extract_llama_build_number(local_version)
    latest_build = _extract_llama_build_number(latest_version)

    if local_build is not None and latest_build is not None:
        if local_build >= latest_build:
            return RuntimeVersionResult(
                status="latest",
                local_version=local_version,
                latest_version=latest_version,
                message=f"llama.cpp runtime is up to date (local build b{local_build}).",
            )
        return RuntimeVersionResult(
            status="outdated",
            local_version=local_version,
            latest_version=latest_version,
            message=(
                f"llama.cpp runtime is outdated: local build b{local_build}, latest {latest_version}. "
                "Upgrade llama.cpp and rebuild/install llama-tts."
            ),
        )

    if latest_version.lower() in local_version.lower():
        return RuntimeVersionResult(
            status="latest",
            local_version=local_version,
            latest_version=latest_version,
            message=f"llama.cpp runtime appears up to date ({latest_version}).",
        )

    return RuntimeVersionResult(
        status="unknown",
        local_version=local_version,
        latest_version=latest_version,
        message=(
            "Could not reliably compare local llama.cpp version to latest release. "
            f"Local='{local_version}', latest='{latest_version}'."
        ),
    )


def _check_kokoro_runtime(timeout_seconds: int) -> RuntimeVersionResult:
    local_version = _detect_installed_package_version("kokoro-onnx")
    latest_version = _fetch_latest_pypi_version("kokoro-onnx", timeout_seconds=timeout_seconds)

    if not local_version:
        return RuntimeVersionResult(
            status="unknown",
            local_version=None,
            latest_version=latest_version,
            message=(
                "Could not detect local kokoro-onnx version. "
                "Install or upgrade with: pip install --upgrade kokoro-onnx"
            ),
        )
    if not latest_version:
        return RuntimeVersionResult(
            status="unknown",
            local_version=local_version,
            latest_version=None,
            message="Could not fetch latest kokoro-onnx version from PyPI.",
        )
    if local_version == latest_version:
        return RuntimeVersionResult(
            status="latest",
            local_version=local_version,
            latest_version=latest_version,
            message=f"kokoro-onnx is up to date ({local_version}).",
        )

    return RuntimeVersionResult(
        status="outdated",
        local_version=local_version,
        latest_version=latest_version,
        message=(
            f"kokoro-onnx is outdated: local={local_version}, latest={latest_version}. "
            "Upgrade with: pip install --upgrade kokoro-onnx"
        ),
    )


def _detect_mlx_audio_local_version(command: str, timeout_seconds: int) -> str | None:
    command_path = shutil.which(command)
    if command_path is None:
        return None

    python_command = _resolve_python_from_script(Path(command_path))
    if not python_command:
        return None

    completed = subprocess.run(
        [*python_command, "-c", "import importlib.metadata as m; print(m.version('mlx-audio'))"],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        return None

    version = completed.stdout.strip()
    return version or None


def _detect_installed_package_version(package_name: str) -> str | None:
    try:
        import importlib.metadata as metadata
    except Exception:
        return None

    try:
        version = metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None
    except Exception:
        return None

    cleaned = version.strip()
    return cleaned if cleaned else None


def _resolve_python_from_script(path: Path) -> list[str] | None:
    try:
        first_line = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
    except (OSError, IndexError):
        return None

    if not first_line.startswith("#!"):
        return None

    parts = shlex.split(first_line[2:])
    if not parts:
        return None

    executable = parts[0]
    if os.path.basename(executable) == "env":
        if len(parts) < 2:
            return None
        return [parts[1], *parts[2:]]
    return parts


def _detect_command_version(command: str, timeout_seconds: int) -> str | None:
    for args in (["--version"], ["-v"]):
        try:
            completed = subprocess.run(
                [command, *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return None

        merged = f"{completed.stdout}\n{completed.stderr}".strip()
        if merged:
            first_line = merged.splitlines()[0].strip()
            if first_line:
                return first_line

    return None


@lru_cache(maxsize=8)
def _fetch_latest_pypi_version(package_name: str, timeout_seconds: int) -> str | None:
    url = f"https://pypi.org/pypi/{package_name}/json"
    payload = _fetch_json(url=url, timeout_seconds=timeout_seconds)
    if payload is None:
        return None

    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    version = info.get("version")
    return version.strip() if isinstance(version, str) and version.strip() else None


@lru_cache(maxsize=4)
def _fetch_latest_llama_cpp_release(timeout_seconds: int) -> str | None:
    payload = _fetch_json(
        url="https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
        timeout_seconds=timeout_seconds,
    )
    if payload is None:
        return None

    tag_name = payload.get("tag_name")
    return tag_name.strip() if isinstance(tag_name, str) and tag_name.strip() else None


def _fetch_json(url: str, timeout_seconds: int) -> dict[str, object] | None:
    request = Request(
        url=url,
        headers={"User-Agent": "tts-mcp-version-check/1.0"},
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _extract_llama_build_number(version_text: str) -> int | None:
    match = re.search(r"\bb(\d{3,})\b", version_text.lower())
    if not match:
        return None
    return int(match.group(1))
