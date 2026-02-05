from mcp.server.fastmcp import FastMCP

from browser_mcp.sessions import SessionManager
from browser_mcp.tools.close_browser_session import register as register_close_session
from browser_mcp.tools.execute_script import register as register_execute_script
from browser_mcp.tools.list_browser_sessions import register as register_list_sessions
from browser_mcp.tools.navigate_to import register as register_navigate
from browser_mcp.tools.open_browser_session import register as register_open_session
from browser_mcp.tools.read_webpage import register as register_read_webpage
from browser_mcp.tools.take_webpage_screenshot import register as register_screenshot
from browser_mcp.tools.trigger_web_element import register as register_trigger


def register_tools(server: FastMCP, session_manager: SessionManager) -> None:
    register_open_session(server, session_manager)
    register_close_session(server, session_manager)
    register_list_sessions(server, session_manager)
    register_navigate(server, session_manager)
    register_read_webpage(server, session_manager)
    register_screenshot(server, session_manager)
    register_trigger(server, session_manager)
    register_execute_script(server, session_manager)
