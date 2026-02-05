from pathlib import Path
from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except ValueError:
        return False


def resolve_output_path(candidate: str) -> Path:
    raw_path = Path(candidate).expanduser()
    if not raw_path.is_absolute():
        raw_path = (Path.cwd() / raw_path).resolve()
    parent = raw_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    return raw_path
