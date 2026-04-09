"""Lint route — health check report with one-click auto-fix.

Reuses lint.run_lint() and lint.apply_fixes() directly. Deep checks
(LLM-powered contradiction detection) are CLI-only — too slow for the UI.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import config as cfg
from ... import lint as lint_module

router = APIRouter()


def _group_issues_by_severity(report: lint_module.LintReport) -> dict:
    """Group issues into errors / warnings / infos for template rendering."""
    grouped: dict[str, list] = {"errors": [], "warnings": [], "infos": []}
    for issue in report.issues:
        if issue.severity == lint_module.Severity.ERROR:
            grouped["errors"].append(issue)
        elif issue.severity == lint_module.Severity.WARNING:
            grouped["warnings"].append(issue)
        else:
            grouped["infos"].append(issue)
    return grouped


def _decorate_issues(issues: list) -> list:
    """Convert LintIssue dataclasses to template-friendly dicts."""
    return [
        {
            "check": issue.check.value,
            "severity": issue.severity.value,
            "page": issue.page,
            "message": issue.message,
            "suggestion": issue.suggestion,
            "fixable": issue.fixable,
        }
        for issue in issues
    ]


@router.get("/lint", response_class=HTMLResponse)
async def lint_page(request: Request) -> HTMLResponse:
    """Run fast lint checks and render the report."""
    paths: cfg.WikiPaths = request.app.state.wiki_paths
    report = lint_module.run_lint(paths, deep=False)
    grouped = _group_issues_by_severity(report)

    # Group warnings by page for tidier rendering when there are many
    warnings_by_page: dict[str, list] = defaultdict(list)
    for issue in grouped["warnings"]:
        warnings_by_page[issue.page].append(issue)

    fixable_count = sum(1 for i in report.issues if i.fixable)

    return request.app.state.templates.TemplateResponse(
        request,
        "lint.html",
        {
            "page": "lint",
            "report": {
                "score": report.health_score,
                "pages_checked": report.pages_checked,
                "duration": report.duration_seconds,
                "errors_count": len(grouped["errors"]),
                "warnings_count": len(grouped["warnings"]),
                "infos_count": len(grouped["infos"]),
                "auto_fixed": report.auto_fixed,
            },
            "errors": _decorate_issues(grouped["errors"]),
            "warnings": _decorate_issues(grouped["warnings"]),
            "infos": _decorate_issues(grouped["infos"]),
            "warnings_by_page": {
                page: _decorate_issues(issues)
                for page, issues in warnings_by_page.items()
            },
            "fixable_count": fixable_count,
            "just_fixed": False,
        },
    )


@router.post("/lint/fix", response_class=HTMLResponse)
async def lint_fix(request: Request) -> HTMLResponse:
    """Run lint, apply fixable issues, then re-render the report."""
    paths: cfg.WikiPaths = request.app.state.wiki_paths

    initial = lint_module.run_lint(paths, deep=False)
    fixed_count = lint_module.apply_fixes(paths, initial.issues)

    # Re-lint to get the post-fix state
    report = lint_module.run_lint(paths, deep=False)
    report.auto_fixed = fixed_count

    grouped = _group_issues_by_severity(report)
    warnings_by_page: dict[str, list] = defaultdict(list)
    for issue in grouped["warnings"]:
        warnings_by_page[issue.page].append(issue)

    fixable_count = sum(1 for i in report.issues if i.fixable)

    return request.app.state.templates.TemplateResponse(
        request,
        "lint.html",
        {
            "page": "lint",
            "report": {
                "score": report.health_score,
                "pages_checked": report.pages_checked,
                "duration": report.duration_seconds,
                "errors_count": len(grouped["errors"]),
                "warnings_count": len(grouped["warnings"]),
                "infos_count": len(grouped["infos"]),
                "auto_fixed": fixed_count,
            },
            "errors": _decorate_issues(grouped["errors"]),
            "warnings": _decorate_issues(grouped["warnings"]),
            "infos": _decorate_issues(grouped["infos"]),
            "warnings_by_page": {
                page: _decorate_issues(issues)
                for page, issues in warnings_by_page.items()
            },
            "fixable_count": fixable_count,
            "just_fixed": True,
        },
    )
