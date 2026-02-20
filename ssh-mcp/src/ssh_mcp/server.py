from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP

from .config import ConfigError, ServerConfig, SshSettings, load_settings
from .runner import (
    SshToolResult,
    create_session_manager,
    run_close_session,
    run_health_check,
    run_open_session,
    run_session_exec,
)


def create_server(
    settings: SshSettings | None = None,
    server_config: ServerConfig | None = None,
) -> FastMCP:
    resolved_settings = settings or load_settings()
    resolved_server_config = server_config or ServerConfig.from_env()
    session_manager = create_session_manager(resolved_settings)

    server = FastMCP(
        name=resolved_server_config.name,
        instructions=resolved_server_config.instructions,
    )

    @server.tool(
        name="ssh_health_check",
        title="SSH command health check",
        description="Validate SSH command availability and optional version probe execution.",
        structured_output=True,
    )
    async def ssh_health_check(*, context: Context | None = None) -> SshToolResult:
        if context is not None:
            await context.report_progress(0, 1, "Running SSH health check")
        result = run_health_check(resolved_settings)
        if context is not None:
            await context.report_progress(1, 1, "SSH health check complete")
        return result

    @server.tool(
        name="ssh_open_session",
        title="Open reusable SSH session",
        description=(
            "Open one reusable SSH session and return its session_id. "
            "host is optional when SSH_MCP_DEFAULT_HOST is configured."
        ),
        structured_output=True,
    )
    async def ssh_open_session(
        host: str | None = None,
        user: str | None = None,
        port: int | None = None,
        cwd: str | None = None,
        *,
        context: Context | None = None,
    ) -> SshToolResult:
        display_host = host if host and host.strip() else "<default>"
        if context is not None:
            await context.report_progress(0, 1, f"Opening SSH session for host '{display_host}'")
        try:
            result = run_open_session(
                settings=resolved_settings,
                manager=session_manager,
                host=host,
                user=user,
                port=port,
                cwd=cwd,
            )
        except ConfigError as exc:
            result = _validation_error(
                action="open_session",
                message=str(exc),
                host=host,
                user=user,
                port=port,
                cwd=cwd,
            )
        if context is not None:
            await context.report_progress(1, 1, "SSH session open completed")
        return result

    @server.tool(
        name="ssh_session_exec",
        title="Run command in SSH session",
        description="Run one command against an existing session_id.",
        structured_output=True,
    )
    async def ssh_session_exec(
        session_id: str,
        command: str,
        cwd: str | None = None,
        *,
        context: Context | None = None,
    ) -> SshToolResult:
        if context is not None:
            await context.report_progress(0, 1, f"Running command in session '{session_id}'")
        try:
            result = run_session_exec(
                settings=resolved_settings,
                manager=session_manager,
                session_id=session_id,
                command=command,
                cwd=cwd,
            )
        except ConfigError as exc:
            result = _validation_error(
                action="session_exec",
                message=str(exc),
                session_id=session_id,
                command=command,
                cwd=cwd,
            )
        if context is not None:
            await context.report_progress(1, 1, "SSH session command completed")
        return result

    @server.tool(
        name="ssh_close_session",
        title="Close SSH session",
        description="Close one active session_id and release its control socket.",
        structured_output=True,
    )
    async def ssh_close_session(
        session_id: str,
        *,
        context: Context | None = None,
    ) -> SshToolResult:
        if context is not None:
            await context.report_progress(0, 1, f"Closing SSH session '{session_id}'")
        try:
            result = run_close_session(
                settings=resolved_settings,
                manager=session_manager,
                session_id=session_id,
            )
        except ConfigError as exc:
            result = _validation_error(
                action="close_session",
                message=str(exc),
                session_id=session_id,
            )
        if context is not None:
            await context.report_progress(1, 1, "SSH session close completed")
        return result

    return server


def _validation_error(
    action: str,
    message: str,
    host: str | None = None,
    user: str | None = None,
    port: int | None = None,
    session_id: str | None = None,
    command: str | None = None,
    cwd: str | None = None,
) -> SshToolResult:
    return SshToolResult(
        ok=False,
        action=action,
        command=[],
        session_id=session_id,
        destination=None,
        host=host,
        user=user,
        port=port,
        remote_command=command,
        cwd=cwd,
        stdout=None,
        stderr=None,
        exit_code=None,
        duration_ms=None,
        error_type="validation",
        error_message=message,
        session_count=None,
        created_at=None,
        last_used_at=None,
    )


def main() -> None:
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
