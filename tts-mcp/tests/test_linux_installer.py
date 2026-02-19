from __future__ import annotations

import os
from pathlib import Path
import shlex
import stat
import subprocess


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install_llama_tts_linux.sh"


def _make_executable(path: Path) -> None:
    path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_resolve_python_bin(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    command = f"source {shlex.quote(str(SCRIPT_PATH))}; resolve_python_bin"
    return subprocess.run(
        ["/bin/bash", "-c", command],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_resolve_python_bin_prefers_python3(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_executable(bin_dir / "python3")
    _make_executable(bin_dir / "python")

    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    env.pop("PYTHON_BIN", None)

    completed = _run_resolve_python_bin(env)

    assert completed.returncode == 0
    assert completed.stdout.strip() == "python3"


def test_resolve_python_bin_falls_back_to_python(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_executable(bin_dir / "python")

    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    env.pop("PYTHON_BIN", None)

    completed = _run_resolve_python_bin(env)

    assert completed.returncode == 0
    assert completed.stdout.strip() == "python"


def test_resolve_python_bin_uses_explicit_python_bin(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_executable(bin_dir / "custom-python")

    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    env["PYTHON_BIN"] = "custom-python"

    completed = _run_resolve_python_bin(env)

    assert completed.returncode == 0
    assert completed.stdout.strip() == "custom-python"


def test_resolve_python_bin_errors_when_explicit_python_missing(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_executable(bin_dir / "python3")

    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    env["PYTHON_BIN"] = "python-not-found"

    completed = _run_resolve_python_bin(env)

    assert completed.returncode != 0
    assert "Python not found: python-not-found" in completed.stderr


def test_resolve_python_bin_errors_when_no_python_available(tmp_path: Path) -> None:
    bin_dir = tmp_path / "empty-bin"
    bin_dir.mkdir()

    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    env.pop("PYTHON_BIN", None)

    completed = _run_resolve_python_bin(env)

    assert completed.returncode != 0
    assert "Python not found" in completed.stderr
