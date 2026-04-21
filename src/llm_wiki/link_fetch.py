"""Fetch linked articles from text/markdown files into raw/ as local docs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from . import config as cfg
from . import ingest_raw
from . import slugify

_URL_RE = re.compile(r"https?://[^\s<>\"]+")
_TEXT_LIKE_SUFFIXES = {".txt", ".md", ".markdown", ".html", ".htm"}
_JUNK_TAGS = ("script", "style", "nav", "footer", "aside", "form", "noscript")
_HEADING_TAGS = {
    "h1": "# ",
    "h2": "## ",
    "h3": "### ",
    "h4": "#### ",
    "h5": "##### ",
    "h6": "###### ",
}


@dataclass
class FetchOutcome:
    url: str
    result: str                 # added | updated | pending | unchanged | error
    relpath: str = ""
    source_id: int | None = None
    title: str | None = None
    message: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_url(url: str) -> str:
    return url.rstrip("),.;]>\"'")


def extract_urls_from_text(text: str) -> list[str]:
    """Extract unique URLs from arbitrary text, preserving order."""
    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_RE.finditer(text):
        url = _clean_url(match.group(0))
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def extract_urls_from_path(path: Path, recursive: bool = False) -> list[str]:
    """Extract URLs from a text-like file or folder of text-like files."""
    path = path.expanduser().resolve()
    files: list[Path] = []
    if path.is_file():
        files = [path]
    elif path.is_dir():
        iterator = path.rglob("*") if recursive else path.iterdir()
        files = [
            child
            for child in iterator
            if child.is_file()
            and not child.name.startswith(".")
            and child.suffix.lower() in _TEXT_LIKE_SUFFIXES
        ]

    seen: set[str] = set()
    urls: list[str] = []
    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for url in extract_urls_from_text(text):
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _stable_basename_for_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace(".", "-")
    path_bits = [bit for bit in parsed.path.split("/") if bit]
    tail = path_bits[-1] if path_bits else "article"
    stem = f"{host}-{tail}"
    clean = slugify.slugify(stem) or "link"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{clean}-{digest}"


def _render_text_doc(
    title: str,
    source_url: str,
    content_type: str,
    body_text: str,
) -> str:
    frontmatter = {
        "title": title,
        "source_url": source_url,
        "fetched_at": _now_iso(),
        "content_type": content_type,
        "type": "source-note",
    }
    fm_yaml = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    ).strip()
    text = body_text.strip()
    return (
        f"---\n{fm_yaml}\n---\n\n"
        f"# {title}\n\n"
        f"Source URL: {source_url}\n\n"
        f"{text}\n"
    )


def _extract_html_text(html: str, fallback_title: str) -> tuple[str, str]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return fallback_title, html

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    for tag_name in _JUNK_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    title = fallback_title
    if soup.title and soup.title.string:
        maybe = soup.title.string.strip()
        if maybe:
            title = maybe
    if title == fallback_title:
        h1 = soup.find("h1")
        if h1:
            maybe = h1.get_text(strip=True)
            if maybe:
                title = maybe

    body = soup.body or soup
    lines: list[str] = []

    def _walk(node) -> None:
        from bs4 import NavigableString, Tag

        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                lines.append(text)
            return

        if not isinstance(node, Tag):
            return

        tag_name = node.name.lower() if node.name else ""
        if tag_name in _HEADING_TAGS:
            heading_text = node.get_text(separator=" ", strip=True)
            if heading_text:
                lines.append(_HEADING_TAGS[tag_name] + heading_text)
            return
        if tag_name in {"p", "li", "blockquote", "div", "td"}:
            block_text = node.get_text(separator=" ", strip=True)
            if block_text:
                lines.append(block_text)
            return
        for child in node.children:
            _walk(child)

    _walk(body)

    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)

    body_text = "\n".join(deduped).strip() or fallback_title
    return title, body_text


def fetch_url_to_raw(
    paths: cfg.WikiPaths,
    url: str,
    *,
    timeout: float = 60.0,
) -> FetchOutcome:
    """Fetch a URL and save it into raw/fetched-links/ as a local document."""
    raw_subdir = paths.raw / "fetched-links"
    raw_subdir.mkdir(parents=True, exist_ok=True)
    base = _stable_basename_for_url(url)
    fallback_title = slugify.slugify(urlparse(url).path.rsplit("/", 1)[-1]) or base

    headers = {
        "User-Agent": "LLM-Wiki/0.8.1 (+local link fetcher)",
        "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as e:
        return FetchOutcome(
            url=url,
            result="error",
            message=f"Fetch failed: {e}",
        )

    final_url = str(response.url)
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    if content_type == "application/pdf" or final_url.lower().endswith(".pdf"):
        dest = raw_subdir / f"{base}.pdf"
        try:
            dest.write_bytes(response.content)
        except OSError as e:
            return FetchOutcome(
                url=url,
                result="error",
                message=f"Failed to write PDF: {e}",
            )
        sync = ingest_raw.sync_file(paths, dest)
        return FetchOutcome(
            url=url,
            result=sync.result,
            relpath=sync.relpath,
            source_id=sync.source_id,
            title=sync.title,
            message=sync.message,
        )

    if content_type in {"text/html", "application/xhtml+xml"} or "<html" in response.text[:500].lower():
        title, body_text = _extract_html_text(response.text, fallback_title)
        content = _render_text_doc(title, final_url, content_type or "text/html", body_text)
        dest = raw_subdir / f"{base}.md"
    else:
        text_body = response.text.strip() or final_url
        title = fallback_title
        content = _render_text_doc(title, final_url, content_type or "text/plain", text_body)
        dest = raw_subdir / f"{base}.md"

    try:
        dest.write_text(content, encoding="utf-8")
    except OSError as e:
        return FetchOutcome(
            url=url,
            result="error",
            message=f"Failed to write document: {e}",
        )

    sync = ingest_raw.sync_file(paths, dest)
    return FetchOutcome(
        url=url,
        result=sync.result,
        relpath=sync.relpath,
        source_id=sync.source_id,
        title=sync.title,
        message=sync.message,
    )
