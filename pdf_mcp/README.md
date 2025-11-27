# PDF MCP Server

A Python MCP server that exposes tools for reading PDF metadata and extracting text from selected pages. The server uses [FastMCP](https://github.com/modelcontextprotocol/servers/tree/main/python) and is ready to plug into MCP-aware clients such as Cursor.

## Features
- `read_pdf_pages`: return structured text content for specific PDF pages or ranges (1-indexed).
- `pdf_metadata`: fetch page counts and document metadata (title, author, subject).
- `render_pdf_pages`: rasterise selected pages to PNG images stored next to the source PDF.
- `image_to_pdf_page`: wrap a single image file into a one-page PDF.
- `add_pdf_page_numbers`: write page numbers into a copy of the PDF with configurable placement.
- `create_pdf_catalog`: insert a clickable catalog / table-of-contents page driven by story metadata.
- Tested end-to-end with an in-process MCP client.

## Installation
```bash
pip install pdf-mcp-server
```

Or, for local development:
```bash
pip install -e .[test]
```

## Running the server
By default the server runs over stdio. You can customise its behaviour with environment variables:

- `PDF_MCP_NAME`: Override the advertised server name (default `pdf-mcp`).
- `PDF_MCP_INSTRUCTIONS`: Override the short instructions string sent during MCP initialisation.

Launch the server:
```bash
python -m pdf_mcp.server
```

All tool calls must supply an absolute path to the target PDF file.

### Tool usage examples

```json
{
  "tool": "read_pdf_pages",
  "input": {
    "file_path": "/docs/report.pdf",
    "pages": [2]
  }
}
```

```json
{
  "tool": "read_pdf_pages",
  "input": {
    "file_path": "/docs/report.pdf",
    "start_page": 1,
    "end_page": 2
  }
}
```

```json
{
  "tool": "pdf_metadata",
  "input": {
    "file_path": "/docs/report.pdf"
  }
}
```

```json
{
  "tool": "add_pdf_page_numbers",
  "input": {
    "file_path": "/docs/report.pdf",
    "output_path": "/docs/report-numbered.pdf",
    "position": "bottom-center",
    "prefix": "Page "
  }
}
```

```json
{
  "tool": "create_pdf_catalog",
  "input": {
    "file_path": "/ebooks/stories.pdf",
    "output_path": "/ebooks/stories-with-toc.pdf",
    "entries": [
      {"title": "Story One", "page_count": 5},
      {"title": "Story Two", "page_count": 6}
    ],
    "insert_after_page": 1,
    "first_story_page": 2
  }
}
```

```json
{
  "tool": "render_pdf_pages",
  "input": {
    "file_path": "/docs/report.pdf",
    "pages": [2]
  }
}
```

```json
{
  "tool": "image_to_pdf_page",
  "input": {
    "image_path": "/images/photo.png",
    "output_path": "/docs/photo.pdf"
  }
}
```

The image renderer accepts optional `start_page` / `end_page` ranges and a `scale` multiplier (default 1.0). Images are always written as PNG files alongside the original PDF, and the tool enforces a 25-page limit per request to keep render workloads bounded.

The image-to-PDF tool requires absolute paths, accepts common image extensions (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.tif`, `.tiff`), and writes a single-page PDF sized to the source image dimensions.

## Cursor MCP configuration example
Add an entry to your Cursor `mcp.json` (or equivalent MCP configuration file):

```json
{
  "mcpServers": [
    {
      "name": "pdf",
      "command": "uv",
      "args": [
        "--directory",
        "/home/ryan-ai/SSD/autobyteus_org_workspace/pdf_mcp",
        "run",
        "python",
        "-m",
        "pdf_mcp.server"
      ]
    }
  ]
}
```

`uv run` ensures the server's dependencies from `pyproject.toml` are available before launching the module, so the MCP client can start the server without managing a separate virtual environment.

With this configuration in place, ask Cursor to call the `read_pdf_pages` tool (for example: "Use the pdf server to read page 2 of contracts/licence.pdf").

## Running the test suite
```bash
python -m pytest
```

The tests spawn an in-process MCP client/server pair and verify both tools end to end.
