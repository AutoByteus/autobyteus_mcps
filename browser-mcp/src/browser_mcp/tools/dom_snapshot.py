from typing import cast

from mcp.server.fastmcp import FastMCP

from browser_mcp.tabs import TabManager, get_tab_or_raise
from browser_mcp.types import DomSnapshotElement, DomSnapshotResult

_DOM_SNAPSHOT_SCRIPT = """
({ includeNonInteractive, includeBoundingBoxes, maxElements }) => {
  const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
  const cssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\\\$&");
  };

  const isVisible = (el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return false;
    }
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") {
      return false;
    }
    if (Number(style.opacity || 1) === 0) {
      return false;
    }
    return true;
  };

  const buildSelector = (el) => {
    if (el.id) {
      return `#${cssEscape(el.id)}`;
    }

    const parts = [];
    let node = el;
    let depth = 0;

    while (node && node.nodeType === Node.ELEMENT_NODE && depth < 6) {
      const tagName = node.tagName.toLowerCase();
      let part = tagName;

      if (node.classList && node.classList.length > 0) {
        const classes = Array.from(node.classList).slice(0, 2).map(cssEscape);
        if (classes.length > 0) {
          part += `.${classes.join(".")}`;
        }
      }

      let nth = 1;
      let sibling = node.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === node.tagName) {
          nth += 1;
        }
        sibling = sibling.previousElementSibling;
      }
      part += `:nth-of-type(${nth})`;
      parts.unshift(part);

      if (node.parentElement && node.parentElement.id) {
        parts.unshift(`#${cssEscape(node.parentElement.id)}`);
        break;
      }
      node = node.parentElement;
      depth += 1;
    }

    return parts.join(" > ");
  };

  const interactiveSelector = [
    "a[href]",
    "button",
    "input",
    "select",
    "textarea",
    "summary",
    "[role='button']",
    "[role='link']",
    "[role='checkbox']",
    "[role='radio']",
    "[role='tab']",
    "[onclick]",
    "[contenteditable='']",
    "[contenteditable='true']",
    "[tabindex]"
  ].join(",");

  const selector = includeNonInteractive ? "*" : interactiveSelector;
  const candidates = Array.from(document.querySelectorAll(selector));
  const elements = [];
  const seenSelectors = new Set();

  for (const el of candidates) {
    if (elements.length >= maxElements) {
      break;
    }
    if (!isVisible(el)) {
      continue;
    }

    const cssSelector = buildSelector(el);
    if (!cssSelector || seenSelectors.has(cssSelector)) {
      continue;
    }
    seenSelectors.add(cssSelector);

    const rect = el.getBoundingClientRect();
    const text = normalize(el.innerText || el.textContent).slice(0, 240) || null;
    const name = normalize(
      el.getAttribute("aria-label") ||
      el.getAttribute("title") ||
      el.getAttribute("placeholder") ||
      el.getAttribute("alt")
    ) || null;
    const href = el.getAttribute("href");
    const value =
      "value" in el && typeof el.value === "string"
        ? normalize(el.value).slice(0, 240) || null
        : null;

    elements.push({
      element_id: `e${elements.length + 1}`,
      tag_name: el.tagName.toLowerCase(),
      dom_id: el.id || null,
      css_selector: cssSelector,
      role: el.getAttribute("role"),
      name,
      text,
      href: href ? String(href) : null,
      value,
      bounding_box: includeBoundingBoxes
        ? {
            x: Number(rect.x),
            y: Number(rect.y),
            width: Number(rect.width),
            height: Number(rect.height)
          }
        : null
    });
  }

  return {
    schema_version: "autobyteus-dom-snapshot-v1",
    total_candidates: candidates.length,
    returned_elements: elements.length,
    truncated: candidates.length > elements.length,
    elements
  };
}
"""


def register(server: FastMCP, tab_manager: TabManager) -> None:
    async def _dom_snapshot(
        tab_id: str,
        include_non_interactive: bool = False,
        include_bounding_boxes: bool = True,
        max_elements: int = 200,
    ) -> DomSnapshotResult:
        if max_elements < 1 or max_elements > 2000:
            raise ValueError("max_elements must be between 1 and 2000")

        tab = await get_tab_or_raise(tab_manager, tab_id)
        page = tab.integrator.page
        if not page:
            raise RuntimeError("Playwright page not initialized")
        if not tab.last_url:
            raise ValueError("Tab has no previous navigation. Call navigate_to first.")

        snapshot_raw = await page.evaluate(
            _DOM_SNAPSHOT_SCRIPT,
            {
                "schemaVersion": "autobyteus-dom-snapshot-v1",
                "includeNonInteractive": include_non_interactive,
                "includeBoundingBoxes": include_bounding_boxes,
                "maxElements": max_elements,
            },
        )

        snapshot = snapshot_raw if isinstance(snapshot_raw, dict) else {}
        raw_elements = snapshot.get("elements")
        elements = cast(list[DomSnapshotElement], raw_elements if isinstance(raw_elements, list) else [])

        total_candidates = snapshot.get("total_candidates")
        returned_elements = snapshot.get("returned_elements")
        truncated = snapshot.get("truncated")

        return DomSnapshotResult(
            url=page.url,
            tab_id=tab_id,
            elements=elements,
            total_candidates=int(total_candidates) if isinstance(total_candidates, int) else len(elements),
            returned_elements=int(returned_elements) if isinstance(returned_elements, int) else len(elements),
            truncated=bool(truncated) if isinstance(truncated, bool) else (len(elements) >= max_elements),
        )

    @server.tool(
        name="dom_snapshot",
        title="DOM snapshot",
        description=(
            "Capture a structured DOM snapshot for agent actions. "
            "Returns stable element IDs, CSS selectors, and optional bounding boxes."
        ),
        structured_output=True,
    )
    async def dom_snapshot(
        tab_id: str,
        include_non_interactive: bool = False,
        include_bounding_boxes: bool = True,
        max_elements: int = 200,
    ) -> DomSnapshotResult:
        return await _dom_snapshot(
            tab_id=tab_id,
            include_non_interactive=include_non_interactive,
            include_bounding_boxes=include_bounding_boxes,
            max_elements=max_elements,
        )
