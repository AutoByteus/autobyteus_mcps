# Plan: Refactor to 'combine_images'

## Goal
Rename `concatenate_images_vertically` to `combine_images` and add support for both vertical and horizontal layouts.

## Context
- User prefers `combine_images` as the name.
- Functionality should be extended to support horizontal layout.

## Steps
- [x] Refactor `app/main.py`:
    - Rename tool to `combine_images`.
    - Add `direction` parameter (default: "vertical").
    - Implement "horizontal" logic:
        - Max height becomes the new height.
        - Sum of widths becomes the new width.
        - Paste side-by-side.
- [x] Update `tests/test_server.py`:
    - Rename tests.
    - Add test case for horizontal combination.
    - Verify vertical combination still works.
- [x] Verify with `uv run pytest`.
