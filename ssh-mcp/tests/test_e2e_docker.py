from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import time
import uuid

import anyio
import pytest
pytest.importorskip("mcp")

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from ssh_mcp.config import ServerConfig, SshSettings
from ssh_mcp.server import create_server


def _run_command(args: list[str], timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            "Command failed with exit code "
            f"{completed.returncode}: {' '.join(args)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed


def _require_docker_prerequisites() -> None:
    if os.environ.get("SSH_MCP_RUN_DOCKER_E2E") != "1":
        pytest.skip("Set SSH_MCP_RUN_DOCKER_E2E=1 to run Docker E2E tests.")

    if _run_command(["docker", "--version"], check=False).returncode != 0:
        pytest.skip("docker CLI is unavailable.")
    if _run_command(["docker", "info"], check=False).returncode != 0:
        pytest.skip("docker daemon is unavailable.")


def _generate_ssh_keypair(tmp_path: Path) -> tuple[Path, str]:
    private_key = tmp_path / "id_ed25519"
    _run_command(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        timeout=20,
    )
    public_key = private_key.with_suffix(".pub").read_text(encoding="utf-8").strip()
    return private_key, public_key


def _resolve_mapped_port(container_id: str) -> int:
    completed = _run_command(["docker", "port", container_id, "2222/tcp"])
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise AssertionError("Docker did not report a mapped port for 2222/tcp.")

    loopback_line = next((line for line in lines if line.startswith("127.0.0.1:")), lines[0])
    try:
        return int(loopback_line.rsplit(":", 1)[1])
    except ValueError as exc:
        raise AssertionError(f"Unable to parse mapped port from: {loopback_line}") from exc


def _wait_for_ssh_ready(private_key: Path, port: int, container_id: str) -> None:
    probe_command = [
        "ssh",
        "-i",
        str(private_key),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=2",
        "-p",
        str(port),
        "mcpuser@127.0.0.1",
        "--",
        "echo ready",
    ]

    deadline = time.time() + 30
    while time.time() < deadline:
        completed = _run_command(probe_command, timeout=5, check=False)
        if completed.returncode == 0 and completed.stdout.strip() == "ready":
            return
        time.sleep(1)

    logs = _run_command(["docker", "logs", container_id], check=False)
    raise AssertionError(
        "SSH daemon did not become ready within 30 seconds.\n"
        f"container logs:\n{logs.stdout}\n{logs.stderr}"
    )


def _wait_for_sshd_port(port: int, container_id: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(1)
            sock.connect(("127.0.0.1", port))
            return
        except OSError:
            time.sleep(1)
        finally:
            sock.close()

    logs = _run_command(["docker", "logs", container_id], check=False)
    raise AssertionError(
        "SSH daemon TCP port did not become reachable within 30 seconds.\n"
        f"container logs:\n{logs.stdout}\n{logs.stderr}"
    )


def _build_e2e_image(image_tag: str) -> None:
    _run_command(
        [
            "docker",
            "build",
            "-t",
            image_tag,
            str(Path(__file__).parent / "e2e"),
        ],
        timeout=240,
    )


def _run_e2e_container(image_tag: str, public_key: str | None = None) -> str:
    command = [
        "docker",
        "run",
        "-d",
        "--rm",
    ]
    if public_key is not None:
        command.extend(["-e", f"PUBLIC_KEY={public_key}"])
    command.extend(
        [
            "-p",
            "127.0.0.1::2222",
            image_tag,
        ]
    )
    run_completed = _run_command(command)
    container_id = run_completed.stdout.strip()
    if not container_id:
        raise AssertionError("Docker did not return a container ID.")
    return container_id


def _cleanup_e2e_container_image(container_id: str | None, image_tag: str) -> None:
    if container_id:
        _run_command(["docker", "rm", "-f", container_id], check=False)
    _run_command(["docker", "image", "rm", image_tag], check=False)


async def _run_mcp_lifecycle(
    settings: SshSettings,
    expected_user: str = "mcpuser",
    open_payload: dict[str, object] | None = None,
    run_chained_command_check: bool = False,
) -> None:
    server = create_server(settings=settings, server_config=ServerConfig(name="ssh-e2e"))
    client_to_server_send, server_read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    server_to_client_send, client_read_stream = anyio.create_memory_object_stream[SessionMessage](0)

    async def server_task() -> None:
        await server._mcp_server.run(  # type: ignore[attr-defined]
            server_read_stream,
            server_to_client_send,
            server._mcp_server.create_initialization_options(),  # type: ignore[attr-defined]
            raise_exceptions=True,
        )

    async with anyio.create_task_group() as tg:
        tg.start_soon(server_task)
        async with ClientSession(client_read_stream, client_to_server_send) as session:
            await session.initialize()

            open_result = await session.call_tool("ssh_open_session", open_payload or {})
            assert not open_result.isError
            open_structured = open_result.structuredContent
            assert isinstance(open_structured, dict)
            assert open_structured["ok"] is True, (
                open_structured.get("error_message"),
                open_structured.get("stderr"),
                open_structured.get("command"),
            )
            session_id = open_structured["session_id"]
            assert isinstance(session_id, str)

            whoami_result = await session.call_tool(
                "ssh_session_exec",
                {"session_id": session_id, "command": "whoami"},
            )
            assert not whoami_result.isError
            whoami_structured = whoami_result.structuredContent
            assert isinstance(whoami_structured, dict)
            assert whoami_structured["ok"] is True
            assert whoami_structured["stdout"] == expected_user

            pwd_result = await session.call_tool(
                "ssh_session_exec",
                {"session_id": session_id, "command": "pwd", "cwd": "/tmp"},
            )
            assert not pwd_result.isError
            pwd_structured = pwd_result.structuredContent
            assert isinstance(pwd_structured, dict)
            assert pwd_structured["ok"] is True
            assert pwd_structured["stdout"] == "/tmp"

            if run_chained_command_check:
                chained_result = await session.call_tool(
                    "ssh_session_exec",
                    {
                        "session_id": session_id,
                        "command": "echo alpha && echo beta | wc -l && uname -s",
                    },
                )
                assert not chained_result.isError
                chained_structured = chained_result.structuredContent
                assert isinstance(chained_structured, dict)
                assert chained_structured["ok"] is True
                assert chained_structured["stdout"] is not None
                chained_lines = chained_structured["stdout"].splitlines()
                assert len(chained_lines) == 3
                assert chained_lines[0] == "alpha"
                assert chained_lines[1] == "1"
                assert chained_lines[2] == "Linux"

            close_result = await session.call_tool("ssh_close_session", {"session_id": session_id})
            assert not close_result.isError
            close_structured = close_result.structuredContent
            assert isinstance(close_structured, dict)
            assert close_structured["ok"] is True

            after_close_result = await session.call_tool(
                "ssh_session_exec",
                {"session_id": session_id, "command": "whoami"},
            )
            assert not after_close_result.isError
            after_close_structured = after_close_result.structuredContent
            assert isinstance(after_close_structured, dict)
            assert after_close_structured["ok"] is False
            assert after_close_structured["error_type"] == "execution"

        await client_to_server_send.aclose()
        await server_to_client_send.aclose()
        tg.cancel_scope.cancel()


async def _run_mcp_open_expect_error(
    settings: SshSettings,
    open_payload: dict[str, object],
    expected_error_type: str,
) -> None:
    server = create_server(settings=settings, server_config=ServerConfig(name="ssh-e2e"))
    client_to_server_send, server_read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    server_to_client_send, client_read_stream = anyio.create_memory_object_stream[SessionMessage](0)

    async def server_task() -> None:
        await server._mcp_server.run(  # type: ignore[attr-defined]
            server_read_stream,
            server_to_client_send,
            server._mcp_server.create_initialization_options(),  # type: ignore[attr-defined]
            raise_exceptions=True,
        )

    async with anyio.create_task_group() as tg:
        tg.start_soon(server_task)
        async with ClientSession(client_read_stream, client_to_server_send) as session:
            await session.initialize()
            open_result = await session.call_tool("ssh_open_session", open_payload)
            assert not open_result.isError
            structured = open_result.structuredContent
            assert isinstance(structured, dict)
            assert structured["ok"] is False
            assert structured["error_type"] == expected_error_type

        await client_to_server_send.aclose()
        await server_to_client_send.aclose()
        tg.cancel_scope.cancel()


@pytest.mark.e2e
def test_session_lifecycle_end_to_end_with_dockerized_sshd(tmp_path: Path) -> None:
    _require_docker_prerequisites()

    private_key, public_key = _generate_ssh_keypair(tmp_path)
    session_dir = tmp_path / "session-sockets"

    image_tag = f"ssh-mcp-e2e:{uuid.uuid4().hex[:12]}"
    container_id: str | None = None

    try:
        _build_e2e_image(image_tag)
        container_id = _run_e2e_container(image_tag, public_key=public_key)

        mapped_port = _resolve_mapped_port(container_id)
        _wait_for_ssh_ready(private_key, mapped_port, container_id)

        settings = SshSettings(
            command="ssh",
            base_args=(
                "-i",
                str(private_key),
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ),
            timeout_seconds=20,
            allowed_hosts=("127.0.0.1",),
            default_host="127.0.0.1",
            default_user="mcpuser",
            default_port=mapped_port,
            max_command_chars=4000,
            max_output_chars=20000,
            health_check_args=("-V",),
            password=None,
            password_file=None,
            session_idle_timeout_seconds=30,
            max_sessions=4,
            session_dir=str(session_dir),
        )

        anyio.run(_run_mcp_lifecycle, settings)
    finally:
        _cleanup_e2e_container_image(container_id, image_tag)


@pytest.mark.e2e
def test_session_lifecycle_password_auth_end_to_end_with_dockerized_sshd(tmp_path: Path) -> None:
    _require_docker_prerequisites()

    session_dir = tmp_path / "session-sockets-password"
    image_tag = f"ssh-mcp-e2e:{uuid.uuid4().hex[:12]}"
    container_id: str | None = None

    try:
        _build_e2e_image(image_tag)
        container_id = _run_e2e_container(image_tag)

        mapped_port = _resolve_mapped_port(container_id)
        _wait_for_sshd_port(mapped_port, container_id)

        settings = SshSettings(
            command="ssh",
            base_args=(
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ),
            timeout_seconds=20,
            allowed_hosts=("127.0.0.1",),
            default_host="127.0.0.1",
            default_user="mcpuser",
            default_port=mapped_port,
            max_command_chars=4000,
            max_output_chars=20000,
            health_check_args=("-V",),
            password="dockerpass",
            password_file=None,
            session_idle_timeout_seconds=30,
            max_sessions=4,
            session_dir=str(session_dir),
        )

        anyio.run(_run_mcp_lifecycle, settings)
    finally:
        _cleanup_e2e_container_image(container_id, image_tag)


@pytest.mark.e2e
def test_session_lifecycle_password_file_auth_end_to_end_with_dockerized_sshd(tmp_path: Path) -> None:
    _require_docker_prerequisites()

    session_dir = tmp_path / "session-sockets-password-file"
    password_file = tmp_path / "password.txt"
    password_file.write_text("dockerpass\n", encoding="utf-8")
    image_tag = f"ssh-mcp-e2e:{uuid.uuid4().hex[:12]}"
    container_id: str | None = None

    try:
        _build_e2e_image(image_tag)
        container_id = _run_e2e_container(image_tag)

        mapped_port = _resolve_mapped_port(container_id)
        _wait_for_sshd_port(mapped_port, container_id)

        settings = SshSettings(
            command="ssh",
            base_args=(
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ),
            timeout_seconds=20,
            allowed_hosts=("127.0.0.1",),
            default_host="127.0.0.1",
            default_user="mcpuser",
            default_port=mapped_port,
            max_command_chars=4000,
            max_output_chars=20000,
            health_check_args=("-V",),
            password=None,
            password_file=str(password_file),
            session_idle_timeout_seconds=30,
            max_sessions=4,
            session_dir=str(session_dir),
        )

        anyio.run(_run_mcp_lifecycle, settings)
    finally:
        _cleanup_e2e_container_image(container_id, image_tag)


@pytest.mark.e2e
def test_session_lifecycle_key_auth_with_explicit_open_args_end_to_end_with_dockerized_sshd(
    tmp_path: Path,
) -> None:
    _require_docker_prerequisites()

    private_key, public_key = _generate_ssh_keypair(tmp_path)
    session_dir = tmp_path / "session-sockets-explicit-open"
    image_tag = f"ssh-mcp-e2e:{uuid.uuid4().hex[:12]}"
    container_id: str | None = None

    try:
        _build_e2e_image(image_tag)
        container_id = _run_e2e_container(image_tag, public_key=public_key)

        mapped_port = _resolve_mapped_port(container_id)
        _wait_for_ssh_ready(private_key, mapped_port, container_id)

        settings = SshSettings(
            command="ssh",
            base_args=(
                "-i",
                str(private_key),
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ),
            timeout_seconds=20,
            allowed_hosts=("127.0.0.1",),
            default_host=None,
            default_user=None,
            default_port=None,
            max_command_chars=4000,
            max_output_chars=20000,
            health_check_args=("-V",),
            password=None,
            password_file=None,
            session_idle_timeout_seconds=30,
            max_sessions=4,
            session_dir=str(session_dir),
        )

        anyio.run(
            _run_mcp_lifecycle,
            settings,
            "mcpuser",
            {"host": "127.0.0.1", "user": "mcpuser", "port": mapped_port},
        )
    finally:
        _cleanup_e2e_container_image(container_id, image_tag)


@pytest.mark.e2e
def test_open_session_reports_execution_error_for_wrong_password_end_to_end_with_dockerized_sshd(
    tmp_path: Path,
) -> None:
    _require_docker_prerequisites()

    session_dir = tmp_path / "session-sockets-bad-password"
    image_tag = f"ssh-mcp-e2e:{uuid.uuid4().hex[:12]}"
    container_id: str | None = None

    try:
        _build_e2e_image(image_tag)
        container_id = _run_e2e_container(image_tag)

        mapped_port = _resolve_mapped_port(container_id)
        _wait_for_sshd_port(mapped_port, container_id)

        settings = SshSettings(
            command="ssh",
            base_args=(
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "NumberOfPasswordPrompts=1",
            ),
            timeout_seconds=20,
            allowed_hosts=("127.0.0.1",),
            default_host="127.0.0.1",
            default_user="mcpuser",
            default_port=mapped_port,
            max_command_chars=4000,
            max_output_chars=20000,
            health_check_args=("-V",),
            password="wrong-password",
            password_file=None,
            session_idle_timeout_seconds=30,
            max_sessions=4,
            session_dir=str(session_dir),
        )

        anyio.run(_run_mcp_open_expect_error, settings, {}, "execution")
    finally:
        _cleanup_e2e_container_image(container_id, image_tag)


@pytest.mark.e2e
def test_session_exec_supports_chained_shell_command_end_to_end_with_dockerized_sshd(tmp_path: Path) -> None:
    _require_docker_prerequisites()

    private_key, public_key = _generate_ssh_keypair(tmp_path)
    session_dir = tmp_path / "session-sockets-chained-command"
    image_tag = f"ssh-mcp-e2e:{uuid.uuid4().hex[:12]}"
    container_id: str | None = None

    try:
        _build_e2e_image(image_tag)
        container_id = _run_e2e_container(image_tag, public_key=public_key)

        mapped_port = _resolve_mapped_port(container_id)
        _wait_for_ssh_ready(private_key, mapped_port, container_id)

        settings = SshSettings(
            command="ssh",
            base_args=(
                "-i",
                str(private_key),
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ),
            timeout_seconds=20,
            allowed_hosts=("127.0.0.1",),
            default_host="127.0.0.1",
            default_user="mcpuser",
            default_port=mapped_port,
            max_command_chars=4000,
            max_output_chars=20000,
            health_check_args=("-V",),
            password=None,
            password_file=None,
            session_idle_timeout_seconds=30,
            max_sessions=4,
            session_dir=str(session_dir),
        )

        anyio.run(_run_mcp_lifecycle, settings, "mcpuser", None, True)
    finally:
        _cleanup_e2e_container_image(container_id, image_tag)
