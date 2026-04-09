# LLM-Wiki

An LLM-maintained personal wiki built on Karpathy's pattern: instead of retrieving from raw docs every time, an LLM incrementally compiles your sources into a persistent, interlinked markdown wiki that you browse in Obsidian.

**Status:** Stage 1 of 8 — scaffolding only. Ingest, query, lint, and web UI come in later stages.

## Quick start

```bash
# Install (editable mode — code changes reflect immediately)
uv pip install -e .

# Initialize a wiki in the current folder
wiki init

# Check status
wiki status
```

## Architecture

Three layers, per Karpathy:

- **`raw/`** — your source documents. Immutable. The LLM reads but never modifies.
- **`wiki/`** — LLM-maintained markdown. Open this folder in Obsidian as a vault.
- **`schema/AGENTS.md`** — the rules file telling the LLM how to maintain the wiki.

Internal state lives in `.wiki/` (git-ignored).

## Stack

- **LLM:** Ollama + Qwen3-14B (local, 9.3GB, 40K context, thinking mode)
- **Search:** QMD (BM25 + vector + LLM rerank, all local)
- **Backend:** Python 3.11+, FastAPI
- **Frontend:** HTMX + Tailwind, Obsidian for the vault view

## License

MIT
