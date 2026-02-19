from mcp.server.fastmcp import FastMCP

from browser_mcp.tabs import TabManager
from browser_mcp.tools.close_tab import register as register_close_tab
from browser_mcp.tools.dom_snapshot import register as register_dom_snapshot
from browser_mcp.tools.run_script import register as register_run_script
from browser_mcp.tools.list_tabs import register as register_list_tabs
from browser_mcp.tools.navigate_to import register as register_navigate
from browser_mcp.tools.open_tab import register as register_open_tab
from browser_mcp.tools.read_page import register as register_read_page
from browser_mcp.tools.screenshot import register as register_screenshot


def register_tools(server: FastMCP, tab_manager: TabManager) -> None:
    register_open_tab(server, tab_manager)
    register_close_tab(server, tab_manager)
    register_list_tabs(server, tab_manager)
    register_navigate(server, tab_manager)
    register_read_page(server, tab_manager)
    register_screenshot(server, tab_manager)
    register_dom_snapshot(server, tab_manager)
    register_run_script(server, tab_manager)
