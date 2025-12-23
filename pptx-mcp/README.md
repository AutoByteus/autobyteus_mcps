# PPTX Image MCP Server

Create and edit PPTX files using images only. The slide size is derived from the first image's aspect ratio, and all images are scaled to fit within the slide (no cropping).

## Tools

- `create_ppt_from_images(images, output_path, base_height_inches=7.5)`
  - Creates a new deck from images.
  - Slide size is derived from the first image's aspect ratio.

- `replace_slide_with_image(pptx_path, slide_index, image_path, output_path=None)`
  - Replaces a slide (0-based index) with a single image.

- `append_images_as_slides(pptx_path, images, output_path=None)`
  - Appends images as new slides.

## Running

From source (no install):

```bash
uv run --directory /path/to/pptx-mcp python app/main.py
```

Or install locally and run the script entrypoint:

```bash
pip install -e .
start-pptx-mcp
```

## MCP Config Example (uv run)

```json
{
  "mcpServers": {
    "PPTXImageServer": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/pptx-mcp",
        "python",
        "app/main.py"
      ]
    }
  }
}
```
