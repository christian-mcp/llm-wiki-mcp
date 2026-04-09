"""Graph route — interactive D3.js force-directed graph of the wiki.

The HTML page is mostly static; all the data is fetched as JSON from the
companion endpoint and rendered client-side with D3 v7.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ... import config as cfg
from ... import lint as lint_module

router = APIRouter()


# Color palette matches Obsidian graph view in our app theme
_TYPE_COLORS = {
    "sources": "#8b5cf6",     # purple
    "entities": "#f59e0b",    # orange
    "concepts": "#10b981",    # green
    "synthesis": "#ec4899",   # pink
}


def _build_graph_data(paths: cfg.WikiPaths) -> dict:
    """Walk the wiki and build a node/edge graph for D3.

    Reuses lint's PageInventory which already does all the work of parsing
    pages, extracting wikilinks, and building the link graphs.
    """
    inv = lint_module._build_inventory(paths)

    nodes: list[dict] = []
    node_index: dict[str, int] = {}

    # Build nodes from each parsed page
    for relpath, parsed in inv.pages.items():
        page_type = relpath.split("/", 1)[0] if "/" in relpath else "other"
        # The slug used in wikilinks (without the .md suffix)
        slug = relpath[:-3] if relpath.endswith(".md") else relpath

        title = (
            parsed.frontmatter.get("title")
            if parsed.frontmatter
            else None
        )
        if not title:
            # Fall back to the basename
            title = slug.rsplit("/", 1)[-1].replace("-", " ").title()

        # Compute the degree (incoming + outgoing) for sizing
        outgoing_count = len(inv.outgoing_links.get(relpath, []))
        incoming_count = len(
            inv.incoming_links.get(slug, []) + inv.incoming_links.get(relpath, [])
        )
        degree = outgoing_count + incoming_count

        node = {
            "id": slug,
            "title": str(title),
            "type": page_type,
            "color": _TYPE_COLORS.get(page_type, "#6b7280"),
            "degree": degree,
            # Radius scales with degree but stays in a reasonable range
            "radius": 6 + min(degree * 1.5, 16),
            "path": relpath,
        }
        node_index[slug] = len(nodes)
        # Also index without .md suffix for matching outgoing link targets
        node_index[relpath] = node_index[slug]
        nodes.append(node)

    # Build edges from outgoing wikilinks. Skip targets that don't resolve
    # to a known node (those are broken wikilinks — already caught by lint).
    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()
    for relpath, targets in inv.outgoing_links.items():
        slug = relpath[:-3] if relpath.endswith(".md") else relpath
        if slug not in node_index:
            continue
        for target in targets:
            if not target:
                continue
            # Resolve target to a node id
            if target in node_index:
                target_id = nodes[node_index[target]]["id"]
            elif f"{target}.md" in node_index:
                target_id = nodes[node_index[f"{target}.md"]]["id"]
            else:
                continue  # broken wikilink — skip

            edge_key = (slug, target_id)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append({"source": slug, "target": target_id})

    # Stats by type for the legend
    type_counts: dict[str, int] = {}
    for node in nodes:
        type_counts[node["type"]] = type_counts.get(node["type"], 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "type_counts": type_counts,
        },
    }


@router.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request) -> HTMLResponse:
    """Render the graph page shell. Data is fetched async via the JSON endpoint."""
    return request.app.state.templates.TemplateResponse(
        request,
        "graph.html",
        {"page": "graph"},
    )


@router.get("/api/graph")
async def graph_data(request: Request) -> JSONResponse:
    """Return the wiki's node/edge graph as JSON for D3."""
    paths: cfg.WikiPaths = request.app.state.wiki_paths
    data = _build_graph_data(paths)
    return JSONResponse(data)
