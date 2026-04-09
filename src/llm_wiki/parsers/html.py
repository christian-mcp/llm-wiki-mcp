"""Parser for HTML files using BeautifulSoup.

Strips boilerplate (scripts, styles, nav, footer) and preserves headings as
markdown-style hashes to retain structural signal. Works well with Obsidian
Web Clipper output.
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    ParsedDocument,
    ParserError,
    compute_hash,
    fallback_title_from_path,
    normalize_text,
)

# Tags whose content should be removed entirely
_JUNK_TAGS = ("script", "style", "nav", "footer", "aside", "form", "noscript")

# Tags whose text should be prefixed with markdown hashes
_HEADING_TAGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}


def parse(path: Path) -> ParsedDocument:
    """Parse a .html or .htm file."""
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise ParserError(
            "beautifulsoup4 is not installed. Run `uv pip install -e .`."
        ) from e

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise ParserError(f"Cannot read {path}: {e}") from e

    # Prefer lxml if available, fall back to the stdlib parser
    try:
        soup = BeautifulSoup(raw, "lxml")
    except Exception:
        soup = BeautifulSoup(raw, "html.parser")

    # Strip junk tags
    for tag_name in _JUNK_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Extract title from <title>, then first <h1>, then filename
    title: str | None = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            title = h1.get_text(strip=True)
    if not title:
        title = fallback_title_from_path(path)

    # Walk the body (or whole soup if no body) and build a text representation
    # that preserves heading structure with markdown hashes.
    body = soup.body or soup
    lines: list[str] = []

    def _walk(node, skip_if_heading: bool = False) -> None:
        """Depth-first walk collecting text with heading markers."""
        from bs4 import NavigableString, Tag

        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text and not skip_if_heading:
                lines.append(text)
            return

        if not isinstance(node, Tag):
            return

        tag_name = node.name.lower() if node.name else ""
        if tag_name in _HEADING_TAGS:
            heading_text = node.get_text(separator=" ", strip=True)
            if heading_text:
                lines.append(_HEADING_TAGS[tag_name] + heading_text)
            return  # Don't recurse into children
        elif tag_name in {"p", "li", "blockquote", "div", "td"}:
            block_text = node.get_text(separator=" ", strip=True)
            if block_text:
                lines.append(block_text)
            return
        elif tag_name == "br":
            return
        else:
            for child in node.children:
                _walk(child)

    _walk(body)

    # Deduplicate consecutive identical lines (BS sometimes yields repeats)
    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)

    full_text = "\n".join(deduped)
    text = normalize_text(full_text)

    metadata: dict = {}
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author and meta_author.get("content"):
        metadata["author"] = meta_author["content"]
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        metadata["description"] = meta_desc["content"]

    return ParsedDocument(
        source_path=path,
        file_type="html",
        title=title,
        text=text,
        content_hash=compute_hash(text),
        bytes=path.stat().st_size,
        metadata=metadata,
    )
