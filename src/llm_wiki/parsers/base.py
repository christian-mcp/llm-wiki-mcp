"""Base types for parsers.

Every parser normalizes its input to a `ParsedDocument`. Downstream stages
(Stage 3's LLM ingest, Stage 4's search indexing) consume this same shape
regardless of whether the source was a PDF, HTML page, or raw markdown.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedDocument:
    """Normalized representation of an ingested source file."""

    source_path: Path           # Absolute path to the file in raw/
    file_type: str              # 'pdf' | 'md' | 'html' | 'docx' | 'txt'
    title: str                  # Best-effort extracted title
    text: str                   # Full plain-text content (normalized whitespace)
    content_hash: str           # sha256 of normalized text
    bytes: int                  # File size on disk
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text_length(self) -> int:
        return len(self.text)

    @property
    def word_count(self) -> int:
        return len(self.text.split()) if self.text else 0

    @property
    def is_empty(self) -> bool:
        """True if the parser extracted effectively no text (e.g. scanned PDF)."""
        return self.word_count < 10


class ParserError(Exception):
    """Raised when a parser cannot process a file."""


def normalize_text(text: str) -> str:
    """Normalize extracted text: collapse runs of whitespace, strip, dedupe
    blank lines. Deterministic, so the resulting hash is stable.
    """
    if not text:
        return ""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of spaces/tabs within lines
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)
    # Collapse 3+ blank lines into 2
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def compute_hash(text: str) -> str:
    """SHA-256 of the UTF-8 encoding of normalized text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fallback_title_from_path(path: Path) -> str:
    """Humanize a filename into a title: 'some_doc-v2.pdf' → 'Some Doc V2'."""
    stem = path.stem
    # Replace separators with spaces
    stem = re.sub(r"[_\-]+", " ", stem)
    # Collapse spaces
    stem = re.sub(r"\s+", " ", stem).strip()
    # Title-case while preserving all-caps acronyms of length ≤4
    words = []
    for word in stem.split():
        if len(word) <= 4 and word.isupper():
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words) or path.name
