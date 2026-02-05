import logging
import os
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from browser_mcp.sessions import SessionManager
from browser_mcp.tools import register_tools

DEFAULT_SERVER_NAME = "browser-mcp"
DEFAULT_INSTRUCTIONS = (
    "Expose browser automation tools backed by brui_core/Playwright. "
    "Use session_id for multi-step workflows when you need stateful navigation."
)

logger = logging.getLogger(__name__)


def initialize_workspace() -> None:
    workspace_path = os.environ.get("AUTOBYTEUS_AGENT_WORKSPACE")
    if workspace_path:
        logger.info("AUTOBYTEUS_AGENT_WORKSPACE found: '%s'", workspace_path)
        if os.path.isdir(workspace_path):
            try:
                os.chdir(workspace_path)
                logger.info("Successfully changed CWD to: %s", os.getcwd())
            except Exception as exc:
                logger.error("Failed to change CWD to '%s': %s", workspace_path, exc, exc_info=True)
        else:
            logger.warning(
                "Workspace path '%s' does not exist or is not a directory. CWD not changed.",
                workspace_path,
            )
    else:
        logger.info("AUTOBYTEUS_AGENT_WORKSPACE not set. Using default CWD.")


initialize_workspace()


@dataclass(slots=True)
class ServerConfig:
    name: str = DEFAULT_SERVER_NAME
    instructions: str = DEFAULT_INSTRUCTIONS

    @classmethod
    def from_env(cls) -> "ServerConfig":
        name = os.environ.get("BROWSER_MCP_NAME", DEFAULT_SERVER_NAME)
        instructions = os.environ.get("BROWSER_MCP_INSTRUCTIONS", DEFAULT_INSTRUCTIONS)
        return cls(name=name, instructions=instructions)


def create_server(config: ServerConfig | None = None) -> FastMCP:
    cfg = config or ServerConfig.from_env()
    server = FastMCP(name=cfg.name, instructions=cfg.instructions)
    session_manager = SessionManager()
    register_tools(server, session_manager)
    return server


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
