import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence, cast

from typing_extensions import TypedDict

from mcp.server.fastmcp import Context, FastMCP
from pypdf import PdfReader, PdfWriter
import fitz

DEFAULT_SERVER_NAME = "pdf-mcp"
DEFAULT_INSTRUCTIONS = (
    "Expose tools for inspecting, rendering, and combining PDF files. "
    "All page numbers are 1-indexed unless otherwise specified."
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


def _resolve_output_path(candidate: str) -> Path:
    raw_path = Path(candidate).expanduser()
    if not raw_path.is_absolute():
        raise ValueError("Output path must be absolute")

    resolved = raw_path.resolve(strict=False)
    if resolved.suffix.lower() != ".pdf":
        raise ValueError("Output file must have a .pdf extension")

    parent = resolved.parent
    if not parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {parent}")
    if not parent.is_dir():
        raise NotADirectoryError(f"Output directory is not a directory: {parent}")

    return resolved


def _resolve_image_path(candidate: str) -> Path:
    raw_path = Path(candidate).expanduser()
    if not raw_path.is_absolute():
        raise ValueError("Image path must be absolute")

    resolved = raw_path.resolve(strict=False)

    if not resolved.exists():
        raise FileNotFoundError(f"Image file not found: {resolved}")

    valid_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    if resolved.suffix.lower() not in valid_extensions:
        raise ValueError("Only image files with extensions .png, .jpg, .jpeg, .bmp, .tif, .tiff are supported")

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


class MergePdfSource(TypedDict):
    path: str
    total_pages: int


class MergePdfResult(TypedDict):
    output_path: str
    total_pages: int
    sources: list[MergePdfSource]


PageNumberPosition = Literal[
    "top-left",
    "top-center",
    "top-right",
    "bottom-left",
    "bottom-center",
    "bottom-right",
]


class NumberedPage(TypedDict):
    page: int
    number: int


class AddPageNumbersResult(TypedDict):
    path: str
    output_path: str
    total_pages: int
    position: PageNumberPosition
    font_size: float
    margin: float
    prefix: str
    suffix: str
    start_number: int
    pages: list[NumberedPage]


class CatalogEntryInput(TypedDict, total=False):
    title: str
    start_page: int
    page_count: int


class CatalogEntry(TypedDict):
    title: str
    page: int
    original_page: int


class CatalogResult(TypedDict):
    path: str
    output_path: str
    total_pages: int
    catalog_page: int
    entries: list[CatalogEntry]
    heading: str


class ImageToPdfResult(TypedDict):
    image_path: str
    output_path: str
    width: float
    height: float

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
        name="merge_pdf_files",
        title="Merge PDF files",
        description=(
            "Combine multiple PDF files into a single document. Example: "
            "{\"file_paths\": [\"/docs/one.pdf\", \"/docs/two.pdf\"], "
            "\"output_path\": \"/docs/combined.pdf\"}."
        ),
        structured_output=True,
    )
    async def merge_pdf_files(
        file_paths: Sequence[str],
        output_path: str,
        *,
        context: Context,
    ) -> MergePdfResult:
        if not file_paths:
            raise ValueError("file_paths must include at least one PDF")

        resolved_sources = [_resolve_pdf_path(path) for path in file_paths]
        resolved_output = _resolve_output_path(output_path)

        writer = PdfWriter()
        sources: list[MergePdfSource] = []

        total_inputs = len(resolved_sources)
        for idx, source_path in enumerate(resolved_sources, start=1):
            reader = PdfReader(str(source_path))
            writer.append(reader)
            pages = len(reader.pages)
            sources.append(MergePdfSource(path=str(source_path), total_pages=pages))
            await context.report_progress(idx, total_inputs, f"Merged {source_path.name}")
            reader.close()

        with resolved_output.open("wb") as handle:
            writer.write(handle)
        writer.close()

        total_pages = sum(source["total_pages"] for source in sources)

        return MergePdfResult(
            output_path=str(resolved_output),
            total_pages=total_pages,
            sources=sources,
        )

    @server.tool(
        name="add_pdf_page_numbers",
        title="Add PDF page numbers",
        description=(
            "Write page numbers into a copy of the PDF. Example: {\"file_path\": "
            "\"/docs/report.pdf\", \"output_path\": \"/docs/report-numbered.pdf\", "
            "\"position\": \"bottom-center\"}."
        ),
        structured_output=True,
    )
    async def add_pdf_page_numbers(
        file_path: str,
        output_path: str,
        pages: Sequence[int] | None = None,
        start_page: int | None = None,
        end_page: int | None = None,
        start_number: int | None = None,
        prefix: str | None = None,
        suffix: str | None = None,
        position: PageNumberPosition = "bottom-center",
        font_size: float | None = None,
        margin: float | None = None,
        *,
        context: Context,
    ) -> AddPageNumbersResult:
        resolved_path = _resolve_pdf_path(file_path)
        resolved_output = _resolve_output_path(output_path)

        prefix_text = prefix if prefix is not None else ""
        suffix_text = suffix if suffix is not None else ""
        font_size_value = font_size if font_size is not None else 12.0
        margin_value = margin if margin is not None else 36.0
        start_number_value = start_number if start_number is not None else 1

        if font_size_value <= 0:
            raise ValueError("font_size must be greater than zero")
        if margin_value < 0:
            raise ValueError("margin must be zero or greater")

        document = fitz.open(str(resolved_path))
        try:
            total_pages = document.page_count
            normalized_pages = _collect_requested_pages(total_pages, pages, start_page, end_page)

            position_map: dict[PageNumberPosition, tuple[str, str]] = {
                "top-left": ("top", "left"),
                "top-center": ("top", "center"),
                "top-right": ("top", "right"),
                "bottom-left": ("bottom", "left"),
                "bottom-center": ("bottom", "center"),
                "bottom-right": ("bottom", "right"),
            }

            if position not in position_map:
                raise ValueError(
                    "position must be one of: top-left, top-center, top-right, bottom-left, bottom-center, bottom-right"
                )

            vertical, horizontal = position_map[position]

            numbered_pages: list[NumberedPage] = []
            total_requested = len(normalized_pages)
            current_number = start_number_value

            for idx, page_number in enumerate(normalized_pages, start=1):
                page = document.load_page(page_number - 1)
                rect = page.rect
                page.wrap_contents()

                usable_width = rect.x1 - rect.x0 - (2 * margin_value)
                if usable_width <= 0:
                    raise ValueError("margin is too large for the page width")

                usable_height = rect.y1 - rect.y0 - (2 * margin_value)
                if usable_height <= 0:
                    raise ValueError("margin is too large for the page height")

                text = f"{prefix_text}{current_number}{suffix_text}"
                text_width = fitz.get_text_length(text, fontname="helv", fontsize=font_size_value)
                if text_width > usable_width:
                    raise ValueError("page number text does not fit within the available width; reduce prefix/suffix or margin")

                if horizontal == "left":
                    x = rect.x0 + margin_value
                elif horizontal == "center":
                    x = rect.x0 + margin_value + (usable_width - text_width) / 2
                else:  # right
                    x = rect.x1 - margin_value - text_width

                if vertical == "top":
                    baseline_y = rect.y0 + margin_value + font_size_value
                    if baseline_y > rect.y1 - margin_value:
                        raise ValueError("font_size and margin leave no vertical space at the top")
                else:
                    baseline_y = rect.y1 - margin_value
                    if baseline_y - font_size_value < rect.y0 + margin_value and rect.y1 - rect.y0 > 0:
                        raise ValueError("font_size and margin leave no vertical space at the bottom")

                page.insert_text(
                    fitz.Point(x, baseline_y),
                    text,
                    fontsize=font_size_value,
                    fontname="helv",
                    color=(0, 0, 0),
                    overlay=True,
                )

                numbered_pages.append(NumberedPage(page=page_number, number=current_number))
                await context.report_progress(idx, total_requested, f"Numbered page {page_number}")
                current_number += 1

            document.save(str(resolved_output))
        finally:
            document.close()

        return AddPageNumbersResult(
            path=str(resolved_path),
            output_path=str(resolved_output),
            total_pages=total_pages,
            position=position,
            font_size=font_size_value,
            margin=margin_value,
            prefix=prefix_text,
            suffix=suffix_text,
            start_number=start_number_value,
            pages=numbered_pages,
        )

    @server.tool(
        name="create_pdf_catalog",
        title="Create PDF catalog page",
        description=(
            "Insert a clickable catalog/table of contents page. Example: {\"file_path\": "
            "\"/docs/book.pdf\", \"output_path\": \"/docs/book-with-toc.pdf\", "
            "\"entries\": [{\"title\": \"Story One\", \"page_count\": 5}, ...]}"
        ),
        structured_output=True,
    )
    async def create_pdf_catalog(
        file_path: str,
        output_path: str,
        entries: Sequence[CatalogEntryInput],
        heading: str | None = None,
        insert_after_page: int | None = None,
        first_story_page: int | None = None,
        font_size: float | None = None,
        heading_font_size: float | None = None,
        margin: float | None = None,
        line_spacing: float | None = None,
        *,
        context: Context,
    ) -> CatalogResult:
        resolved_path = _resolve_pdf_path(file_path)
        resolved_output = _resolve_output_path(output_path)

        if not entries:
            raise ValueError("entries must include at least one catalog item")

        document = fitz.open(str(resolved_path))
        try:
            total_pages = document.page_count
            if total_pages == 0:
                raise ValueError("PDF must contain at least one page")
            updated_total_pages = total_pages

            insert_page_reference = insert_after_page if insert_after_page is not None else 1
            if insert_page_reference < 0:
                raise ValueError("insert_after_page must be >= 0")
            if insert_page_reference > total_pages:
                raise ValueError("insert_after_page must be <= total_pages")

            insertion_index = insert_page_reference

            base_story_page = first_story_page if first_story_page is not None else (insert_page_reference + 1)
            if base_story_page < 1:
                raise ValueError("first_story_page must be >= 1")

            computed_entries: list[CatalogEntry] = []
            current_page = base_story_page

            for idx, raw_entry in enumerate(entries, start=1):
                title = raw_entry.get("title")
                if not title:
                    raise ValueError(f"entries[{idx}] is missing a title")

                start_page = raw_entry.get("start_page")
                page_count = raw_entry.get("page_count")

                if start_page is None:
                    if page_count is None:
                        raise ValueError(
                            "Each entry must include start_page or page_count so the catalog can link to a page"
                        )
                    start_page = current_page
                else:
                    if start_page < 1:
                        raise ValueError("start_page must be >= 1")
                    current_page = start_page

                if start_page > total_pages:
                    raise ValueError(f"start_page {start_page} is beyond the PDF page count {total_pages}")

                if page_count is not None:
                    if page_count <= 0:
                        raise ValueError("page_count must be greater than zero when provided")
                    end_page = start_page + page_count - 1
                    if end_page > total_pages:
                        raise ValueError(
                            f"Entry '{title}' spans beyond the PDF (end page {end_page} > {total_pages})"
                        )

                shift = 1 if start_page > insert_page_reference else 0
                display_page = start_page + shift

                computed_entries.append(
                    CatalogEntry(title=title, page=display_page, original_page=start_page)
                )

                if page_count is None:
                    current_page = start_page
                else:
                    current_page = start_page + page_count

            heading_text = heading if heading is not None else "Contents"
            entry_font_size = font_size if font_size is not None else 14.0
            heading_size = heading_font_size if heading_font_size is not None else entry_font_size * 1.4
            margin_value = margin if margin is not None else 54.0
            line_spacing_value = line_spacing if line_spacing is not None else entry_font_size * 1.6

            template_page = document.load_page(0 if insertion_index == 0 else min(insertion_index, total_pages - 1))
            rect = template_page.rect
            if rect.width <= 0 or rect.height <= 0:
                raise ValueError("Unable to determine page dimensions for catalog page")

            catalog_page = document.new_page(
                pno=insertion_index,
                width=rect.width,
                height=rect.height,
            )

            y = rect.y0 + margin_value + heading_size
            heading_point = fitz.Point(rect.x0 + margin_value, y)
            catalog_page.insert_text(heading_point, heading_text, fontsize=heading_size, fontname="helv", color=(0, 0, 0))

            y += line_spacing_value
            link_height = entry_font_size * 1.2

            total_entries = len(computed_entries)
            for idx, entry in enumerate(computed_entries, start=1):
                if y > rect.y1 - margin_value:
                    raise ValueError("Not enough vertical space to render all catalog entries; reduce entry count or margins")
                text_point = fitz.Point(rect.x0 + margin_value, y)
                entry_text = f"{entry['title']} ...... {entry['page']}"
                catalog_page.insert_text(text_point, entry_text, fontsize=entry_font_size, fontname="helv", color=(0, 0, 0))

                link_rect = fitz.Rect(
                    rect.x0 + margin_value,
                    y - entry_font_size,
                    rect.x1 - margin_value,
                    y - entry_font_size + link_height,
                )

                target_page_index = entry["page"] - 1

                if target_page_index < 0 or target_page_index >= document.page_count:
                    raise ValueError(
                        f"Computed target page index {target_page_index + 1} is outside the updated document range"
                    )

                catalog_page.insert_link(
                    {
                        "kind": fitz.LINK_GOTO,
                        "from": link_rect,
                        "page": target_page_index,
                        "to": fitz.Point(rect.x0, rect.y0),
                    }
                )

                y += line_spacing_value
                await context.report_progress(idx, total_entries, f"Added catalog entry '{entry['title']}'")

            updated_total_pages = document.page_count
            document.save(str(resolved_output))
        finally:
            document.close()

        return CatalogResult(
            path=str(resolved_path),
            output_path=str(resolved_output),
            total_pages=updated_total_pages,
            catalog_page=insertion_index + 1,
            entries=computed_entries,
            heading=heading_text,
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

    @server.tool(
        name="image_to_pdf_page",
        title="Convert image to PDF page",
        description=(
            "Convert a single image into a one-page PDF. Example: {\"image_path\": "
            "\"/docs/photo.png\", \"output_path\": \"/docs/photo.pdf\"}."
        ),
        structured_output=True,
    )
    async def image_to_pdf_page(image_path: str, output_path: str) -> ImageToPdfResult:
        resolved_image = _resolve_image_path(image_path)
        resolved_output = _resolve_output_path(output_path)

        pix = fitz.Pixmap(str(resolved_image))
        try:
            width, height = float(pix.width), float(pix.height)
            if width <= 0 or height <= 0:
                raise ValueError("Image dimensions must be greater than zero")

            document = fitz.open()
            try:
                page = document.new_page(width=width, height=height)
                page.insert_image(page.rect, pixmap=pix)
                document.save(str(resolved_output))
            finally:
                document.close()
        finally:
            pix = None  # allow GC of the pixmap

        return ImageToPdfResult(
            image_path=str(resolved_image),
            output_path=str(resolved_output),
            width=width,
            height=height,
        )

    return server

def main() -> None:
    server = create_server()
    server.run()

if __name__ == "__main__":
    main()
