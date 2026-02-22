from __future__ import annotations

from tts_mcp.config import load_settings
from tts_mcp.platform import HostInfo
import tts_mcp.runtime_bootstrap as runtime_bootstrap


def _mac_host() -> HostInfo:
    return HostInfo(
        system="Darwin",
        machine="arm64",
        is_macos_arm64=True,
        is_linux=False,
        has_nvidia=False,
    )


def _linux_host() -> HostInfo:
    return HostInfo(
        system="Linux",
        machine="x86_64",
        is_macos_arm64=False,
        is_linux=True,
        has_nvidia=True,
    )


def test_bootstrap_installs_mlx_on_macos_when_missing(monkeypatch) -> None:
    settings = load_settings({})
    monkeypatch.setattr(runtime_bootstrap, "detect_host", lambda: _mac_host())
    monkeypatch.setattr(runtime_bootstrap.shutil, "which", lambda *_: None)

    scripts_called: list[str] = []
    monkeypatch.setattr(
        runtime_bootstrap,
        "_run_install_script",
        lambda path: scripts_called.append(path.name),
    )

    notes = runtime_bootstrap.bootstrap_runtime(settings)

    assert "install_mlx_audio_macos.sh" in scripts_called
    assert notes


def test_bootstrap_installs_kokoro_on_linux_by_default(monkeypatch) -> None:
    settings = load_settings({})
    monkeypatch.setattr(runtime_bootstrap, "detect_host", lambda: _linux_host())
    monkeypatch.setattr(runtime_bootstrap, "_python_module_available", lambda *_: False)
    monkeypatch.setattr(runtime_bootstrap, "_kokoro_assets_available", lambda **_: False)

    scripts_called: list[str] = []
    monkeypatch.setattr(
        runtime_bootstrap,
        "_run_install_script",
        lambda path: scripts_called.append(path.name),
    )

    notes = runtime_bootstrap.bootstrap_runtime(settings)

    assert "install_kokoro_onnx_linux.sh" in scripts_called
    assert notes


def test_bootstrap_installs_kokoro_zh_profile_when_default_language_is_zh(monkeypatch) -> None:
    settings = load_settings({"KOKORO_TTS_DEFAULT_LANG_CODE": "zh"})
    monkeypatch.setattr(runtime_bootstrap, "detect_host", lambda: _linux_host())
    monkeypatch.setattr(runtime_bootstrap, "_python_module_available", lambda *_: False)
    monkeypatch.setattr(runtime_bootstrap, "_kokoro_assets_available", lambda **_: False)

    profile_seen: list[str | None] = []
    monkeypatch.setattr(
        runtime_bootstrap,
        "_run_install_script",
        lambda path: profile_seen.append(runtime_bootstrap.os.environ.get("KOKORO_TTS_PROFILE")),
    )

    notes = runtime_bootstrap.bootstrap_runtime(settings)

    assert profile_seen == ["zh_v1_1"]
    assert runtime_bootstrap.os.environ.get("KOKORO_TTS_PROFILE") is None
    assert notes


def test_bootstrap_installs_llama_on_linux_when_selected(monkeypatch) -> None:
    settings = load_settings({"TTS_MCP_LINUX_RUNTIME": "llama_cpp"})
    monkeypatch.setattr(runtime_bootstrap, "detect_host", lambda: _linux_host())
    monkeypatch.setattr(runtime_bootstrap.shutil, "which", lambda *_: None)

    scripts_called: list[str] = []
    monkeypatch.setattr(
        runtime_bootstrap,
        "_run_install_script",
        lambda path: scripts_called.append(path.name),
    )

    notes = runtime_bootstrap.bootstrap_runtime(settings)

    assert "install_llama_tts_linux.sh" in scripts_called
    assert notes


def test_bootstrap_skips_kokoro_install_when_ready(monkeypatch) -> None:
    settings = load_settings({"TTS_MCP_LINUX_RUNTIME": "kokoro_onnx"})
    monkeypatch.setattr(runtime_bootstrap, "detect_host", lambda: _linux_host())
    monkeypatch.setattr(runtime_bootstrap, "_python_module_available", lambda *_: True)
    monkeypatch.setattr(runtime_bootstrap, "_kokoro_assets_available", lambda **_: True)

    scripts_called: list[str] = []
    monkeypatch.setattr(
        runtime_bootstrap,
        "_run_install_script",
        lambda path: scripts_called.append(path.name),
    )

    notes = runtime_bootstrap.bootstrap_runtime(settings)

    assert scripts_called == []
    assert notes == []


def test_kokoro_assets_available_uses_zh_defaults_when_language_is_zh(tmp_path) -> None:
    root_dir = tmp_path
    zh_dir = root_dir / ".tools" / "kokoro-v1.1-zh"
    zh_dir.mkdir(parents=True)
    (zh_dir / "kokoro-v1.1-zh.onnx").write_bytes(b"onnx")
    (zh_dir / "voices-v1.1-zh.bin").write_bytes(b"voices")
    (zh_dir / "config.json").write_text("{}", encoding="utf-8")

    settings = load_settings({"KOKORO_TTS_DEFAULT_LANG_CODE": "zh"})
    assert runtime_bootstrap._kokoro_assets_available(root_dir=root_dir, settings=settings) is True


def test_bootstrap_disabled_noop(monkeypatch) -> None:
    settings = load_settings({"TTS_MCP_AUTO_INSTALL_RUNTIME": "false"})
    monkeypatch.setattr(runtime_bootstrap, "detect_host", lambda: _mac_host())

    scripts_called: list[str] = []
    monkeypatch.setattr(
        runtime_bootstrap,
        "_run_install_script",
        lambda path: scripts_called.append(path.name),
    )

    notes = runtime_bootstrap.bootstrap_runtime(settings)

    assert scripts_called == []
    assert notes == []
