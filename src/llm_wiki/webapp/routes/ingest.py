"""Ingest route — drag-drop file upload + live SSE streaming of the pipeline."""

from __future__ import annotations

import json
import queue
import shutil
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ... import config as cfg
from ... import ingest_llm
from ... import ingest_raw
from ...llm import OllamaClient

router = APIRouter()


@router.get("/ingest", response_class=HTMLResponse)
async def ingest_page(request: Request) -> HTMLResponse:
    """Render the ingest page with drag-drop + pending source list."""
    paths: cfg.WikiPaths = request.app.state.wiki_paths
    pending = ingest_raw.list_sources(paths, status_filter="pending")
    return request.app.state.templates.TemplateResponse(
        request,
        "ingest.html",
        {"page": "ingest", "pending_sources": pending},
    )


@router.post("/ingest/upload")
async def ingest_upload(
    request: Request, files: list[UploadFile] = File(...)
) -> JSONResponse:
    """Receive uploaded files, save to raw/, register in DB.

    Does NOT auto-ingest — that's a separate step the user triggers.
    """
    paths: cfg.WikiPaths = request.app.state.wiki_paths
    paths.raw.mkdir(parents=True, exist_ok=True)

    results = []
    for upload in files:
        # Sanitize filename — keep just the basename
        safe_name = Path(upload.filename or "upload.bin").name
        if not safe_name:
            results.append({"name": upload.filename, "ok": False, "error": "empty filename"})
            continue

        dest = paths.raw / safe_name
        try:
            with dest.open("wb") as out:
                shutil.copyfileobj(upload.file, out)
        except OSError as e:
            results.append({"name": safe_name, "ok": False, "error": str(e)})
            continue
        finally:
            try:
                upload.file.close()
            except Exception:
                pass

        # Register the now-on-disk file via add_file (won't re-copy)
        outcome = ingest_raw.add_file(paths, dest, copy=False)
        results.append(
            {
                "name": safe_name,
                "ok": outcome.result == ingest_raw.AddResult.ADDED,
                "result": outcome.result.value,
                "message": outcome.message,
                "source_id": outcome.source_id,
            }
        )

    return JSONResponse({"uploads": results})


def _sse_format(event: str, data: dict | str) -> str:
    if isinstance(data, str):
        payload = json.dumps({"text": data})
    else:
        payload = json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


class _SSEIngestCallbacks(ingest_llm.IngestCallbacks):
    """Push ingest pipeline events into a queue for SSE streaming."""

    def __init__(self, q: "queue.Queue[tuple[str, Any]]") -> None:
        self.q = q

    def on_start(self, source_id: int, source_title: str, file_path: str) -> None:
        self.q.put(
            (
                "start",
                {
                    "source_id": source_id,
                    "title": source_title,
                    "file_path": file_path,
                },
            )
        )

    def on_parsing(self) -> None:
        self.q.put(("status", {"text": "Parsing source…"}))

    def on_extracting(self) -> None:
        self.q.put(("status", {"text": "Extracting entities and concepts (thinking mode)…"}))

    def on_extracted(self, extraction: ingest_llm.Extraction) -> None:
        self.q.put(
            (
                "extracted",
                {
                    "title": extraction.title,
                    "summary": extraction.summary,
                    "entities": [
                        {"name": e.name, "kind": e.kind} for e in extraction.entities
                    ],
                    "concepts": [
                        {"name": c.name} for c in extraction.concepts
                    ],
                    "tags": extraction.tags,
                },
            )
        )

    def on_extraction_failed(self, error: str) -> None:
        self.q.put(("error", {"text": f"Extraction failed: {error}"}))

    def ask_confirm(self, extraction: ingest_llm.Extraction) -> bool:
        # In the web UI we always proceed (the user already clicked "Ingest")
        return True

    def on_drafting_page(self, kind: str, slug: str, operation: str) -> None:
        self.q.put(
            ("drafting", {"kind": kind, "slug": slug, "operation": operation})
        )

    def on_page_written(self, page: ingest_llm.PageChange) -> None:
        self.q.put(
            (
                "page_written",
                {
                    "kind": page.kind,
                    "slug": page.slug,
                    "operation": page.operation,
                    "path": page.path,
                },
            )
        )

    def on_finalizing(self) -> None:
        self.q.put(("status", {"text": "Finalizing — rebuilding index, updating log…"}))

    def on_complete(self, result: ingest_llm.IngestResult) -> None:
        self.q.put(
            (
                "complete",
                {
                    "title": result.source_title,
                    "slug": result.source_slug,
                    "created": result.pages_created,
                    "updated": result.pages_updated,
                    "ok": result.error is None,
                },
            )
        )

    def on_error(self, error: str) -> None:
        self.q.put(("error", {"text": error}))


@router.get("/ingest/stream/{source_id}")
async def ingest_stream(request: Request, source_id: int) -> StreamingResponse:
    """SSE stream the 3-pass ingest pipeline for a single source."""
    paths: cfg.WikiPaths = request.app.state.wiki_paths
    config = cfg.load_config(paths)
    llm_cfg = config.get("llm", {})

    event_q: "queue.Queue[tuple[str, Any]]" = queue.Queue()
    done_event = threading.Event()

    def worker() -> None:
        client = OllamaClient(
            host=llm_cfg.get("host", "http://localhost:11434"),
            model=llm_cfg.get("model", "qwen3:14b"),
        )
        try:
            try:
                client.ensure_ready()
            except Exception as e:
                event_q.put(("error", {"text": f"Ollama not ready: {e}"}))
                return

            callbacks = _SSEIngestCallbacks(event_q)
            try:
                ingest_llm.ingest_source(
                    paths,
                    source_id,
                    client,
                    callbacks,
                    mode="batch",  # web UI never prompts
                    thinking_for_extraction=True,
                )
            except Exception as e:
                event_q.put(("error", {"text": f"Ingest failed: {e}"}))
        finally:
            try:
                client.close()
            except Exception:
                pass
            done_event.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    async def event_generator():
        import asyncio

        yield _sse_format("status", {"text": "Connecting to Ollama…"})

        loop = asyncio.get_event_loop()
        while True:
            try:
                event_name, payload = await loop.run_in_executor(
                    None, lambda: event_q.get(timeout=0.5)
                )
                yield _sse_format(event_name, payload)
                if event_name in ("complete", "error"):
                    return
            except queue.Empty:
                if done_event.is_set():
                    yield _sse_format("done", {"text": ""})
                    return
                continue

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
