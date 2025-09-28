import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence, cast

from typing_extensions import TypedDict

from mcp.server.fastmcp import Context, FastMCP
from pypdf import PdfReader
import fitz

DEFAULT_SERVER_NAME = "pdf-mcp"
DEFAULT_INSTRUCTIONS = (
    "Expose read-only tools for viewing the text content and metadata of PDF files. "
    "All page numbers are 1-indexed."
)

def _resolve_pdf_path(candidate: str) -> Path:
    raw_path = Path(candidate).expanduser()
    if not raw_path.is_absolute():
        raise ValueError("PDF path must be absolute")

    resolved = raw_path.resolve(strict=False)

    if not resolved.exists():
        raise FileNotFoundError(f"PDF file not found: {resolved}")

    if resolved.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported")

    return resolved


def _collect_requested_pages(
    total_pages: int,
    pages: Sequence[int] | None,
    start_page: int | None,
    end_page: int | None,
) -> list[int]:
    page_numbers: set[int] = set()
    if pages:
        page_numbers.update(pages)

    if start_page is not None or end_page is not None:
        if start_page is None:
            raise ValueError("start_page is required when end_page is provided")
        page_end = end_page if end_page is not None else start_page
        if page_end < start_page:
            raise ValueError("end_page must be >= start_page")
        page_numbers.update(range(start_page, page_end + 1))

    if not page_numbers:
        page_numbers.update(range(1, total_pages + 1))

    normalized = sorted(page_numbers)
    for number in normalized:
        if number < 1 or number > total_pages:
            raise ValueError(f"Page {number} is out of range (1-{total_pages})")

    return normalized

class PageContent(TypedDict):
    page: int
    text: str

class ReadPdfResult(TypedDict):
    path: str
    total_pages: int
    pages: list[PageContent]

class PdfMetadata(TypedDict):
    path: str
    total_pages: int
    title: str | None
    author: str | None
    subject: str | None


class RenderedPage(TypedDict):
    page: int
    image_path: str


class RenderPdfResult(TypedDict):
    path: str
    format: Literal["png"]
    output_dir: str
    pages: list[RenderedPage]

@dataclass(slots=True)
class ServerConfig:
    name: str = DEFAULT_SERVER_NAME
    instructions: str = DEFAULT_INSTRUCTIONS

    @classmethod
    def from_env(cls) -> "ServerConfig":
        name = os.environ.get("PDF_MCP_NAME", DEFAULT_SERVER_NAME)
        instructions = os.environ.get("PDF_MCP_INSTRUCTIONS", DEFAULT_INSTRUCTIONS)
        return cls(name=name, instructions=instructions)

def create_server(config: ServerConfig | None = None) -> FastMCP:
    cfg = config or ServerConfig.from_env()

    server = FastMCP(name=cfg.name, instructions=cfg.instructions)

    @server.tool(
        name="read_pdf_pages",
        title="Read PDF pages",
        description=(
            "Retrieve the text of selected PDF pages (1-indexed). Examples: "
            "single page -> {\"file_path\": \"/docs/report.pdf\", \"pages\": [2]}; "
            "range -> {\"file_path\": \"/docs/report.pdf\", \"start_page\": 1, \"end_page\": 2}."
        ),
        structured_output=True,
    )
    async def read_pdf_pages(
        file_path: str,
        pages: Sequence[int] | None = None,
        start_page: int | None = None,
        end_page: int | None = None,
        *,
        context: Context,
    ) -> ReadPdfResult:
        resolved_path = _resolve_pdf_path(file_path)
        reader = PdfReader(str(resolved_path))
        total_pages = len(reader.pages)

        normalized_pages = _collect_requested_pages(total_pages, pages, start_page, end_page)

        extracted: list[PageContent] = []
        total_requested = len(normalized_pages)
        if total_requested == 0:
            return ReadPdfResult(
                path=str(resolved_path),
                total_pages=total_pages,
                pages=[],
            )

        for idx, page_number in enumerate(normalized_pages):
            page = reader.pages[page_number - 1]
            text = page.extract_text() or ""
            extracted.append(PageContent(page=page_number, text=text))
            await context.report_progress(idx + 1, total_requested, f"Read page {page_number}")

        return ReadPdfResult(
            path=str(resolved_path),
            total_pages=total_pages,
            pages=extracted,
        )

    @server.tool(
        name="pdf_metadata",
        title="PDF metadata",
        description=(
            "Inspect basic metadata about a PDF file, including page count. Example: "
            "{\"file_path\": \"/docs/report.pdf\"}."
        ),
        structured_output=True,
    )
    async def pdf_metadata(file_path: str) -> PdfMetadata:
        resolved_path = _resolve_pdf_path(file_path)
        reader = PdfReader(str(resolved_path))
        info = reader.metadata
        title = info.title if info else None
        author = info.author if info else None
        subject = info.subject if info else None

        return PdfMetadata(
            path=str(resolved_path),
            total_pages=len(reader.pages),
            title=title,
            author=author,
            subject=subject,
        )

    @server.tool(
        name="render_pdf_pages",
        title="Render PDF pages",
        description=(
            "Render selected PDF pages to PNG images stored next to the source file. Examples: "
            "single page -> {\"file_path\": \"/docs/report.pdf\", \"pages\": [2]}; "
            "range -> {\"file_path\": \"/docs/report.pdf\", \"start_page\": 3, \"end_page\": 4}."
        ),
        structured_output=True,
    )
    async def render_pdf_pages(
        file_path: str,
        pages: Sequence[int] | None = None,
        start_page: int | None = None,
        end_page: int | None = None,
        scale: float | None = None,
        *,
        context: Context,
    ) -> RenderPdfResult:
        resolved_path = _resolve_pdf_path(file_path)
        document = fitz.open(str(resolved_path))
        total_pages = document.page_count

        normalized_pages = _collect_requested_pages(total_pages, pages, start_page, end_page)
        if len(normalized_pages) > 25:
            raise ValueError("Rendering more than 25 pages per request is not supported")

        output_root = resolved_path.parent
        file_extension = "png"

        scale_value = scale if scale is not None else 1.0
        if scale_value <= 0:
            raise ValueError("scale must be greater than zero")
        matrix = fitz.Matrix(scale_value, scale_value)

        rendered_pages: list[RenderedPage] = []
        total_requested = len(normalized_pages)
        for idx, page_number in enumerate(normalized_pages, start=1):
            page = document.load_page(page_number - 1)
            pix = page.get_pixmap(matrix=matrix)

            filename = f"{resolved_path.stem}-page-{page_number:04d}.{file_extension}"
            destination = output_root / filename
            pix.save(destination)

            rendered_pages.append(RenderedPage(page=page_number, image_path=str(destination)))
            await context.report_progress(idx, total_requested, f"Rendered page {page_number}")

        document.close()

        return RenderPdfResult(
            path=str(resolved_path),
            format=cast(Literal["png"], "png"),
            output_dir=str(output_root),
            pages=rendered_pages,
        )

    return server

def main() -> None:
    server = create_server()
    server.run()

if __name__ == "__main__":
    main()
