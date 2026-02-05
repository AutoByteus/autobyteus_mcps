from typing import TypedDict


class NavigateResult(TypedDict):
    url: str
    ok: bool
    status: int | None
    session_id: str | None


class ReadWebpageResult(TypedDict):
    url: str
    content: str
    session_id: str | None


class ScreenshotResult(TypedDict):
    url: str
    file_path: str
    session_id: str | None


class SessionResult(TypedDict):
    session_id: str


class CloseSessionResult(TypedDict):
    session_id: str
    closed: bool


class ListSessionsResult(TypedDict):
    session_ids: list[str]


class TriggerElementResult(TypedDict):
    message: str
    session_id: str | None


class ExecuteScriptResult(TypedDict):
    url: str
    result: object | None
    session_id: str | None
