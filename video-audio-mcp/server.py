import ffmpeg
from mcp.server.fastmcp import FastMCP, Context
import os

# Import the core components (mcp instance)
from core import mcp

# Import all tool modules to register the tools with the MCP instance
import tools

# A simple health check tool can remain in the main server file
@mcp.tool()
def health_check() -> str:
    """Returns a simple health status to confirm the server is running."""
    return "Server is healthy!"

# Main execution block to run the server
if __name__ == "__main__":
    mcp.run()
