# AGENTS.md — Research Wiki Schema & Conventions

> This file is the contract between you and the LLM agent that maintains
> this wiki. The wiki is optimized for research tracking, not just generic
> note-taking: keep raw sources immutable, separate extracted facts from
> hypotheses, cite everything, and let a skeptic pass audit quality.

## 1. Project layout

```
.
├── raw/         ← Source documents. IMMUTABLE. Read-only for the agent.
├── wiki/        ← LLM-maintained markdown. The agent owns this layer entirely.
│   ├── index.md
│   ├── log.md
│   ├── sources/       ← One summary page per ingested source.
│   ├── entities/      ← People, places, organizations, models, products.
│   ├── concepts/      ← Topics, techniques, theories, ideas.
│   ├── facts/         ← Evidence-backed claims or findings.
│   ├── hypotheses/    ← Tentative claims, conjectures, open questions.
│   └── synthesis/     ← Cross-source summaries, comparisons, evolving theses.
└── schema/AGENTS.md   ← This file.
```

## 2. Page conventions

Every wiki page must:

1. Start with YAML frontmatter containing at minimum:
   ```yaml
   ---
   title: "Page Title"
   type: source | entity | concept | fact | hypothesis | synthesis
   tags: [tag1, tag2]
   created: YYYY-MM-DD
   updated: YYYY-MM-DD
   sources: ["sources/source-slug.md"]
   confidence: high | medium | low
   ---
   ```

2. Use `[[wikilinks]]` for internal page references. Plain markdown links are
   allowed only for raw files outside `wiki/`.

3. Keep a clear separation between:
   - raw source metadata
   - extracted facts / findings
   - summaries
   - hypotheses / open questions
   - quality concerns or evidence gaps

4. Preserve provenance. Never silently overwrite earlier claims; use
   `## Updates` or `## Quality Notes` when new evidence changes the picture.

## 3. Page types

### `sources/<slug>.md`
Summarize one ingested source. Include:
- raw file path and raw file link
- concise summary
- key takeaways
- extracted facts
- hypotheses / open questions
- quality watchouts
- related pages

### `entities/<slug>.md`
Named things such as authors, labs, datasets, products, models, firms, or
people. Explain the entity in the relevant research context.

### `concepts/<slug>.md`
Ideas, methods, theories, or topics. Explain what they are, why they matter,
and how they connect to other pages.

### `facts/<slug>.md`
Evidence-backed claims or findings. Keep these precise and cite the supporting
source pages clearly.

### `hypotheses/<slug>.md`
Tentative ideas, open questions, or conjectures. Keep these explicitly
tentative and describe what evidence would strengthen or falsify them.

### `synthesis/<slug>.md`
Cross-source analysis, comparisons, rolling theses, topic digests, and other
compressed retrieval-friendly pages.

## 4. Ingest workflow

When a new source arrives in `raw/`:

1. Read the full source.
2. Extract entities, concepts, facts, hypotheses, and quality watchouts.
3. Write `sources/<slug>.md` with explicit raw/facts/summary/hypothesis sections.
4. Update or create entity pages.
5. Update or create concept pages.
6. Update or create fact pages.
7. Update or create hypothesis pages.
8. Update `synthesis/` when the source changes the broader picture.
9. Append to `log.md`.
10. Update `index.md`.

## 5. Query workflow

When the user asks a question:

1. Search the compiled wiki first.
2. Prefer concise, high-signal pages such as `facts/`, `hypotheses/`, and
   `synthesis/` when they answer the question well.
3. Cite claims with `[[wikilinks]]` back to the supporting pages.
4. If the compiled wiki is insufficient, acknowledge the gap and suggest what
   raw sources or follow-up ingests would help.

## 6. Lint / quality workflow

The quality-review agent is a skeptic, not a drafter. It should look for:
- contradictions
- overgeneralization or drift
- weak provenance
- missing evidence
- hypotheses stated as facts

## 7. What the agent must never do

- Never edit `raw/`.
- Never delete a wiki page without explicit user confirmation.
- Never present a hypothesis as established fact.
- Never invent citations or supporting evidence.
- Never use plain markdown links between wiki pages.
