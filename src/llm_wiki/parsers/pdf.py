"""Parser for PDF files using pypdf.

Handles text-based PDFs. Scanned/image PDFs will extract to near-empty text
and be flagged via ParsedDocument.is_empty — the caller decides whether to
skip or still register them.
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


def _first_nonempty_line(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line and len(line) <= 200:
            return line
    return None


def parse(path: Path) -> ParsedDocument:
    """Parse a .pdf file."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ParserError(
            "pypdf is not installed. Run `uv pip install -e .` to install dependencies."
        ) from e

    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise ParserError(f"Cannot open PDF {path.name}: {e}") from e

    # Extract text from all pages
    page_texts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            page_texts.append(page.extract_text() or "")
        except Exception:
            # Individual page extraction can fail on malformed PDFs; keep going
            page_texts.append("")

    full_text = "\n\n".join(p for p in page_texts if p.strip())
    text = normalize_text(full_text)

    # Title extraction: metadata first, then first non-empty line, then filename
    title: str | None = None
    try:
        meta = reader.metadata
        if meta and getattr(meta, "title", None):
            meta_title = str(meta.title).strip()
            if meta_title:
                title = meta_title
    except Exception:
        pass
    if not title:
        title = _first_nonempty_line(text)
    if not title:
        title = fallback_title_from_path(path)

    # Collect useful metadata
    metadata: dict = {"page_count": len(reader.pages)}
    try:
        meta = reader.metadata
        if meta:
            if getattr(meta, "author", None):
                metadata["author"] = str(meta.author)
            if getattr(meta, "creation_date", None):
                metadata["creation_date"] = str(meta.creation_date)
    except Exception:
        pass

    return ParsedDocument(
        source_path=path,
        file_type="pdf",
        title=title,
        text=text,
        content_hash=compute_hash(text),
        bytes=path.stat().st_size,
        metadata=metadata,
    )
