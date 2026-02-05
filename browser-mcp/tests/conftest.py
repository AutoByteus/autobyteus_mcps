import logging
import os
from pathlib import Path

import pytest

from brui_core.browser.browser_manager import BrowserManager

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
env_test_path = project_root / ".env.test"

if not env_test_path.exists():
    raise FileNotFoundError(
        f"CRITICAL: Test environment file not found at '{env_test_path}'. Tests cannot proceed."
    )

load_dotenv(env_test_path, override=True)

chrome_user_data_dir = os.environ.get("CHROME_USER_DATA_DIR")
if chrome_user_data_dir:
    chrome_path = Path(chrome_user_data_dir)
    if not chrome_path.is_absolute():
        chrome_path = (project_root / chrome_path).resolve()
        os.environ["CHROME_USER_DATA_DIR"] = str(chrome_path)
    chrome_path.mkdir(parents=True, exist_ok=True)

logging.info("Successfully loaded test environment from %s", env_test_path)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    # Playwright (brui_core) requires asyncio; avoid trio backend in pytest-anyio.
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_browser_manager_state() -> None:
    # Reset shared Playwright/browser objects between tests to avoid cross-event-loop hangs.
    manager = BrowserManager()
    manager.browser = None
    manager.playwright = None
