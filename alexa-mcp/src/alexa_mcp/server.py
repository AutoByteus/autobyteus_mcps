from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import Context, FastMCP

from .config import (
    AlexaSettings,
    ConfigError,
    ServerConfig,
    ensure_allowed_music_action,
    ensure_allowed_routine,
    load_settings,
)
from .runner import (
    AlexaCommandResult,
    run_device_status,
    run_health_check,
    run_music_action,
    run_routine,
)


def create_server(
    settings: AlexaSettings | None = None,
    server_config: ServerConfig | None = None,
) -> FastMCP:
    resolved_settings = settings or load_settings()
    resolved_server_config = server_config or ServerConfig.from_env()

    server = FastMCP(
        name=resolved_server_config.name,
        instructions=resolved_server_config.instructions,
    )

    @server.tool(
        name="alexa_health_check",
        title="Alexa adapter health check",
        description="Validate Alexa adapter command availability and optional probe execution.",
        structured_output=True,
    )
    async def alexa_health_check(*, context: Context | None = None) -> AlexaCommandResult:
        if context is not None:
            await context.report_progress(0, 1, "Running Alexa adapter health check")
        result = run_health_check(resolved_settings)
        if context is not None:
            await context.report_progress(1, 1, "Health check complete")
        return result

    @server.tool(
        name="alexa_get_device_status",
        title="Get device playback status",
        description="Query Alexa playback and queue status for the selected device.",
        structured_output=True,
    )
    async def alexa_get_device_status(
        echo_device: str | None = None,
        *,
        context: Context | None = None,
    ) -> AlexaCommandResult:
        if context is not None:
            await context.report_progress(0, 1, "Querying Alexa device status")
        result = run_device_status(
            settings=resolved_settings,
            echo_device=echo_device,
        )
        if context is not None:
            await context.report_progress(1, 1, "Device status query complete")
        return result

    @server.tool(
        name="alexa_run_routine",
        title="Run allowlisted Alexa routine",
        description=(
            "Trigger one allowlisted routine by name. "
            "Example routine_name values: plug_on, plug_off."
        ),
        structured_output=True,
    )
    async def alexa_run_routine(
        routine_name: str,
        echo_device: str | None = None,
        *,
        context: Context | None = None,
    ) -> AlexaCommandResult:
        if context is not None:
            await context.report_progress(0, 1, f"Validating routine '{routine_name}'")
        try:
            approved_routine = ensure_allowed_routine(resolved_settings, routine_name)
        except ConfigError as exc:
            return _validation_error(
                action="run_routine",
                message=str(exc),
                routine_name=routine_name,
                echo_device=echo_device,
            )

        result = run_routine(
            settings=resolved_settings,
            routine_name=approved_routine,
            echo_device=echo_device,
        )
        if context is not None:
            await context.report_progress(1, 1, "Routine command completed")
        return result

    @server.tool(
        name="alexa_music_control",
        title="Control Alexa music playback",
        description=(
            "Run bounded music actions. action must be play or stop. "
            "When action is play and no play-routine override is configured, query is required."
        ),
        structured_output=True,
    )
    async def alexa_music_control(
        action: Literal["play", "stop"],
        query: str | None = None,
        echo_device: str | None = None,
        *,
        context: Context | None = None,
    ) -> AlexaCommandResult:
        if context is not None:
            await context.report_progress(0, 1, f"Validating music action '{action}'")
        try:
            approved_action = ensure_allowed_music_action(resolved_settings, action)
            result = run_music_action(
                settings=resolved_settings,
                action=approved_action,
                query=query,
                echo_device=echo_device,
            )
        except ConfigError as exc:
            return _validation_error(
                action="music_control",
                message=str(exc),
                music_action=action,
                echo_device=echo_device,
            )

        if context is not None:
            await context.report_progress(1, 1, "Music control command completed")
        return result

    return server


def _validation_error(
    action: str,
    message: str,
    routine_name: str | None = None,
    music_action: str | None = None,
    echo_device: str | None = None,
) -> AlexaCommandResult:
    return AlexaCommandResult(
        ok=False,
        action=action,
        command=[],
        stdout=None,
        stderr=None,
        exit_code=None,
        error_type="validation",
        error_message=message,
        routine_name=routine_name,
        music_action=music_action,
        echo_device=echo_device,
    )


def main() -> None:
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
