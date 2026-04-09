"""Dashboard route — home page with project stats and recent activity."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .. import main as webapp_main  # noqa: F401  (for type checker)
from ... import config as cfg
from ... import db
from ... import lint as lint_module
from ... import search

router = APIRouter()


def _count_md(folder: Path) -> int:
    """Count markdown pages in a folder, excluding hidden files and
    lint-report files (which are meta-content, not real wiki knowledge).
    """
    if not folder.exists():
        return 0
    return sum(
        1
        for p in folder.glob("*.md")
        if not p.name.startswith(".")
        and not p.name.startswith("lint-report-")
    )


def _parse_log_entries(log_path: Path, limit: int = 15) -> list[dict]:
    """Parse `wiki/log.md` for recent entries.

    Each entry has the form:
        ## [YYYY-MM-DD] action | title
        - bullet
        - bullet
    """
    if not log_path.exists():
        return []
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    entries: list[dict] = []
    header_re = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\]\s+(\w+)\s*\|\s*(.+?)\s*$")
    current: dict | None = None

    for line in content.splitlines():
        header = header_re.match(line)
        if header:
            if current is not None:
                entries.append(current)
            current = {
                "date": header.group(1),
                "action": header.group(2),
                "title": header.group(3),
                "bullets": [],
            }
            continue
        if current and line.startswith("- "):
            current["bullets"].append(line[2:].strip())

    if current is not None:
        entries.append(current)

    # Return newest-first, up to `limit`
    return list(reversed(entries))[:limit]


def _collect_stats(paths: cfg.WikiPaths) -> dict:
    """Gather everything the dashboard displays in a single dict."""
    # Page counts by type
    sources_pages = _count_md(paths.wiki / "sources")
    entities_pages = _count_md(paths.wiki / "entities")
    concepts_pages = _count_md(paths.wiki / "concepts")
    synthesis_pages = _count_md(paths.wiki / "synthesis")
    total_pages = sources_pages + entities_pages + concepts_pages + synthesis_pages

    # Raw files
    raw_files = 0
    if paths.raw.exists():
        raw_files = sum(
            1
            for p in paths.raw.rglob("*")
            if p.is_file() and not p.name.startswith(".")
        )

    # DB stats
    db_stats = db.get_stats(paths.state_db)

    # Search backend
    qmd_available = search.is_available()
    qmd_version = search.get_version() if qmd_available else None

    # Recent activity from log.md
    recent = _parse_log_entries(paths.log, limit=8)

    # Quick lint health (fast checks only, cached-ish — this runs on every
    # dashboard load but fast checks take <100ms for a typical wiki)
    try:
        report = lint_module.run_lint(paths, deep=False)
        health_score = report.health_score
        errors = len(report.errors)
        warnings = len(report.warnings)
    except Exception:
        health_score = None
        errors = warnings = 0

    # Last updated: most recent file mtime in wiki/
    last_updated: str | None = None
    try:
        latest = 0.0
        for sub in ("sources", "entities", "concepts", "synthesis"):
            d = paths.wiki / sub
            if not d.exists():
                continue
            for p in d.glob("*.md"):
                if p.stat().st_mtime > latest:
                    latest = p.stat().st_mtime
        if latest > 0:
            dt = datetime.fromtimestamp(latest, tz=timezone.utc)
            last_updated = dt.strftime("%Y-%m-%d %H:%M")
    except OSError:
        pass

    return {
        "pages": {
            "sources": sources_pages,
            "entities": entities_pages,
            "concepts": concepts_pages,
            "synthesis": synthesis_pages,
            "total": total_pages,
        },
        "raw_files": raw_files,
        "db": db_stats,
        "qmd": {"available": qmd_available, "version": qmd_version},
        "recent_activity": recent,
        "health": {
            "score": health_score,
            "errors": errors,
            "warnings": warnings,
        },
        "last_updated": last_updated,
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard home page."""
    paths: cfg.WikiPaths = request.app.state.wiki_paths
    stats = _collect_stats(paths)

    return request.app.state.templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "project_root": str(paths.root),
            "version": request.app.state.version,
            "page": "dashboard",
        },
    )
