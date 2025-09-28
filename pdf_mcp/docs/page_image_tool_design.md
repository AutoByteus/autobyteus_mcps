# PDF Page Image Tool Design
## Goal
Enable clients to convert individual PDF pages (or small ranges) into raster images and receive the filesystem paths to the generated files.

## Implementation status
- [x] Dependency added
- [x] Tool implementation
- [x] Tests
- [x] Documentation

## Proposed Tool
- **Name**: `render_pdf_pages`
- **Title**: "Render PDF pages"
- **Description**: "Render selected PDF pages to PNG images. Examples: `{\"file_path\": \"/docs/report.pdf\", \"pages\": [2]}` or `{\"file_path\": \"/docs/report.pdf\", \"start_page\": 3, \"end_page\": 4}`."
- **Structured output**: `{"path": str, "pages": [{"page": int, "image_path": str}], "output_dir": str, "format": "png"}`

## Inputs
| Field | Type | Required | Notes |
| ----- | ---- | -------- | ----- |
| `file_path` | `str` | yes | Must be an absolute path (matches existing tools). |
| `pages` | `Sequence[int] \| None` | no | Explicit page list (1-indexed). Mutually exclusive with range args; same validation as `read_pdf_pages`. |
| `start_page` / `end_page` | `int \| None` | no | Inclusive range; defaults mirror existing behaviour. |
| `scale` | `float | None` | no | Optional DPI scaling factor (default 1.0). |
| *Output location* | derived | — | Images are always written alongside the source PDF file. |

## Output
```json
{
  "path": "/docs/report.pdf",
  "pages": [
    {"page": 2, "image_path": "/tmp/pdf-mcp-images/report-page-0002.png"}
  ]
}
```

## Dependency
- Add `pymupdf>=1.24` (PyMuPDF) to the core dependencies. PyMuPDF bundles its own rendering engine (no external Poppler dependency) and exposes an API for rasterising pages to PIL images or bytes.

## Implementation Notes
- Resolve the PDF path with the existing `_resolve_pdf_path` helper.
- Use `fitz.open(str(resolved_path))` to load the document and `page.get_pixmap(matrix=fitz.Matrix(scale, scale))` for rasterisation.
- Always place outputs next to the source PDF (`resolved_path.parent`), ensuring the caller knows where to find the images without extra configuration.
- Ensure `output_dir` exists and is writable when provided; reject relative paths.
- Generate filenames using a deterministic prefix such as `"{resolved_path.stem}-page-{page_number:04d}.{format}"` to aid caching while avoiding collisions.
- Write images via `pix.save(destination_path)`.
- Report progress using `context.report_progress` just like the text-reading tool.
- Enforce a practical page-count guard (e.g., `> 25` pages raises an error) to prevent heavy misuse.

## Testing Strategy
- Extend the existing async tests:
  - Create a 2-page PDF fixture; invoke `render_pdf_pages` for a single page and assert a PNG file exists with non-zero length.
  - Invoke the range variant producing multiple images and verify filenames and extensions.
- Validate error cases: unsupported scale values and pages out of range.
- Use `tmp_path` for output so the filesystem stays isolated.

## Documentation Updates
- README: add a section describing the new tool, its inputs, and examples similar to the existing ones.
- Mention the `pymupdf` dependency and note that outputs appear alongside the PDF.
