# Plan: Add Vertical Image Concatenation Tool

## Goal
Add a new MCP tool `concatenate_images_vertically` that takes a list of images and stacks them vertically into a single output image.

## Context
- User wants a simpler way to share multiple images without creating a full PPTX.
- Existing image processing relies on `PIL` (Pillow).

## Steps
- [x] Implement `concatenate_images_vertically` in `app/main.py`
    - Validate inputs.
    - Calculate total height and max width.
    - Create new image.
    - Paste images.
    - Save output.
- [x] Add test case to verify functionality.
