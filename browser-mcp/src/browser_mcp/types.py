from typing import TypedDict


class NavigateResult(TypedDict):
    url: str
    ok: bool
    status: int | None
    tab_id: str


class ReadPageResult(TypedDict):
    url: str
    content: str
    tab_id: str


class ScreenshotResult(TypedDict):
    url: str
    file_path: str
    tab_id: str


class BoundingBox(TypedDict):
    x: float
    y: float
    width: float
    height: float


class DomSnapshotElement(TypedDict):
    element_id: str
    tag_name: str
    dom_id: str | None
    css_selector: str
    role: str | None
    name: str | None
    text: str | None
    href: str | None
    value: str | None
    bounding_box: BoundingBox | None


class DomSnapshotResult(TypedDict):
    url: str
    tab_id: str
    elements: list[DomSnapshotElement]
    total_candidates: int
    returned_elements: int
    truncated: bool


class OpenTabResult(TypedDict):
    tab_id: str
    url: str


class CloseTabResult(TypedDict):
    tab_id: str
    closed: bool


class ListTabsResult(TypedDict):
    tab_ids: list[str]


class RunScriptResult(TypedDict):
    url: str
    result: object | None
    tab_id: str
