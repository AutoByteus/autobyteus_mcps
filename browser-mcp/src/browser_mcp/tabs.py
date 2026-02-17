import asyncio
from dataclasses import dataclass
from datetime import datetime

from brui_core.ui_integrator import UIIntegrator


def create_integrator() -> UIIntegrator:
    return UIIntegrator()


async def prepare_integrator() -> UIIntegrator:
    integrator = create_integrator()
    await integrator.initialize()
    return integrator


@dataclass(slots=True)
class BrowserTab:
    tab_id: str
    integrator: UIIntegrator
    created_at: datetime
    last_url: str | None = None


class TabManager:
    def __init__(self) -> None:
        self._tabs: dict[str, BrowserTab] = {}
        self._lock = asyncio.Lock()
        self._next_tab_number = 1

    async def open_tab(self) -> BrowserTab:
        integrator = await prepare_integrator()
        async with self._lock:
            tab_id = self._allocate_tab_id()
            tab = BrowserTab(
                tab_id=tab_id,
                integrator=integrator,
                created_at=datetime.utcnow(),
            )
            self._tabs[tab_id] = tab
        return tab

    async def close_tab(self, tab_id: str, close_browser: bool = False) -> tuple[str, bool]:
        async with self._lock:
            tab = self._tabs.pop(tab_id, None)
            if not tab:
                return tab_id, False

        await tab.integrator.close(close_browser=close_browser)
        return tab_id, True

    def get_tab(self, tab_id: str) -> BrowserTab | None:
        return self._tabs.get(tab_id)

    def list_tabs(self) -> list[str]:
        return sorted(self._tabs.keys(), key=int)

    def _allocate_tab_id(self) -> str:
        # Numeric tab IDs capped at 6 digits for human-readable handles.
        max_tab_number = 999999
        start = self._next_tab_number

        while True:
            candidate = str(self._next_tab_number)
            self._next_tab_number += 1
            if self._next_tab_number > max_tab_number:
                self._next_tab_number = 1

            if candidate not in self._tabs:
                return candidate
            if self._next_tab_number == start:
                raise RuntimeError("No available tab IDs. Close tabs and retry.")


async def get_tab_or_raise(tab_manager: TabManager, tab_id: str) -> BrowserTab:
    tab = tab_manager.get_tab(tab_id)
    if not tab:
        raise ValueError(f"Unknown tab_id: {tab_id}")
    return tab
