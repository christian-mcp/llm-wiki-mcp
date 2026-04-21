"""Prompt templates for the LLM ingest and quality-review pipelines.

Passes:
    1. extract — read source, return structured JSON with entities/concepts/
                 facts/hypotheses
    2. draft_page — generate a single wiki page
    3. merge_page — update an existing page
    4. source_page — summarize the raw source with explicit research sections

Deep lint also reuses the prompts in this module for contradiction detection
and skeptical quality review.
"""

from __future__ import annotations

from .llm import ChatMessage


# ---------------------------------------------------------------------------
# System prompt — shared across all passes
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the LLM agent that maintains an LLM-Wiki research knowledge base.

You follow these conventions strictly:

1. Wiki pages use YAML frontmatter with these fields:
   - title: "Page Title"
   - type: source | entity | concept | fact | hypothesis | synthesis
   - tags: [tag1, tag2]
   - created: YYYY-MM-DD
   - updated: YYYY-MM-DD
   - sources: ["sources/source-slug.md"]
   - confidence: high | medium | low

2. Always use [[wikilinks]] for cross-references between wiki pages.
   Never use plain markdown links for internal wiki pages.
   Plain markdown links are allowed only for raw source files outside wiki/.

3. Slugs are kebab-case lowercase ASCII (e.g. andrej-karpathy, not Karpathy.md).
   Use the canonical name. Acronyms stay together (rag, llm, not r-a-g).

4. Be factual. Never invent citations or claims not present in the source.
   If the source is suggestive but not conclusive, represent that uncertainty.

5. Keep a clear separation between:
   - raw source metadata
   - extracted facts / findings
   - summaries
   - hypotheses / open questions
   - quality concerns or evidence gaps

6. Preserve existing content when updating a page. Add new info in new
   sections or under an '## Updates' or '## Quality Notes' heading. Never
   silently overwrite prior claims.

7. Cite every non-trivial section or bullet by linking back to the relevant
   [[sources/...]] page.
"""


# ---------------------------------------------------------------------------
# Pass 1 — Extraction
# ---------------------------------------------------------------------------

EXTRACTION_INSTRUCTIONS = """Read the source document below and extract a structured research summary.

Return ONLY a valid JSON object matching this exact schema:

{
  "title": "A clear, specific title for this source (max 80 chars)",
  "source_slug": "kebab-case-slug-for-this-source",
  "summary": "A 2-3 sentence paragraph summarizing the source",
  "key_takeaways": [
    "Bullet 1 — a substantive takeaway (1-2 sentences)",
    "Bullet 2",
    "Bullet 3"
  ],
  "entities": [
    {
      "name": "Canonical name as it would appear in a wiki",
      "slug": "kebab-case-slug",
      "type": "person | organization | model | product | place",
      "description": "1-2 sentences describing this entity based on the source"
    }
  ],
  "concepts": [
    {
      "name": "Canonical name",
      "slug": "kebab-case-slug",
      "type": "concept",
      "description": "1-2 sentences describing this concept based on the source"
    }
  ],
  "facts": [
    {
      "name": "Short title for a concrete finding or claim",
      "slug": "kebab-case-slug",
      "description": "1-3 sentences capturing the evidence-backed finding",
      "confidence": "high | medium | low"
    }
  ],
  "hypotheses": [
    {
      "name": "Short title for a tentative claim or open hypothesis",
      "slug": "kebab-case-slug",
      "description": "1-3 sentences explaining the hypothesis or open question",
      "confidence": "medium | low"
    }
  ],
  "quality_watchouts": [
    "Possible weakness, confounder, missing evidence, or caveat"
  ],
  "tags": ["tag1", "tag2", "tag3"]
}

Rules:
- Extract 3-8 key takeaways, each substantive.
- Extract 2-10 entities (people, organizations, models, products, places mentioned).
- Extract 2-10 concepts (techniques, ideas, topics discussed).
- Extract 2-8 facts that are important enough to retrieve directly later.
- Extract 0-4 hypotheses or open questions. Use an empty list if none.
- Extract 0-5 quality_watchouts. Use an empty list if the source is unusually clean.
- Facts should be evidence-backed claims from the source, not your own conclusions.
- Hypotheses should be tentative claims, open questions, or conjectures the source suggests.
- Tags should be 3-6 broad topic labels for the whole source.
- Do NOT extract trivial mentions — only things substantive enough to deserve their own wiki page.
- Return ONLY the JSON object. No preamble, no explanation, no markdown fences.
"""


def build_extraction_messages(source_title: str, source_text: str) -> list[ChatMessage]:
    """Pass 1 — extract structured information from a source document."""
    user_content = (
        f"{EXTRACTION_INSTRUCTIONS}\n\n"
        f"---SOURCE TITLE---\n{source_title}\n\n"
        f"---SOURCE TEXT---\n{source_text}\n"
    )
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


def build_extraction_retry_messages(
    source_title: str, source_text: str, bad_response: str
) -> list[ChatMessage]:
    """Retry prompt after a JSON parse failure."""
    user_content = (
        "Your previous response was not valid JSON. Return ONLY a valid JSON "
        "object matching the schema — no markdown fences, no preamble.\n\n"
        f"{EXTRACTION_INSTRUCTIONS}\n\n"
        f"---SOURCE TITLE---\n{source_title}\n\n"
        f"---SOURCE TEXT---\n{source_text}\n"
    )
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
        ChatMessage(role="assistant", content=bad_response[:2000]),
        ChatMessage(
            role="user",
            content="That was not valid JSON. Try again. Return ONLY the JSON object.",
        ),
    ]


# ---------------------------------------------------------------------------
# Pass 2 — Draft a new page
# ---------------------------------------------------------------------------

NEW_ENTITY_PAGE_TEMPLATE = """Draft a wiki entity page for '{name}'.

This entity was extracted from the source: '{source_title}' (sources/{source_slug}.md)

The source describes it as:
{description}

Here are some relevant excerpts from the source:
{excerpts}

Related pages also mentioned in this source (use [[wikilinks]] to connect to them):
{related}

Write a complete markdown page with:
1. YAML frontmatter (title, type: entity, tags, created: {today}, updated: {today}, sources: ["sources/{source_slug}.md"], confidence)
2. An H1 heading matching the title
3. A concise 2-3 paragraph body that explains who/what this entity is in the research context
4. Use [[wikilinks]] when referencing related pages
5. Cite each non-trivial paragraph with [[sources/{source_slug}]]
6. End with a '## Sources' section listing [[sources/{source_slug}]]

Do not invent facts. Only use information from the excerpts. Return ONLY the markdown content — no preamble, no code fences.
"""


NEW_CONCEPT_PAGE_TEMPLATE = """Draft a wiki concept page for '{name}'.

This concept was extracted from the source: '{source_title}' (sources/{source_slug}.md)

The source describes it as:
{description}

Here are some relevant excerpts from the source:
{excerpts}

Related pages also mentioned in this source (use [[wikilinks]] to connect to them):
{related}

Write a complete markdown page with:
1. YAML frontmatter (title, type: concept, tags, created: {today}, updated: {today}, sources: ["sources/{source_slug}.md"], confidence)
2. An H1 heading matching the title
3. A concise 2-4 paragraph body explaining:
   - what the concept is
   - why it matters for this research area
   - how it connects to related pages
4. Cite each non-trivial paragraph with [[sources/{source_slug}]]
5. End with a '## Sources' section listing [[sources/{source_slug}]]

Do not invent facts. Only use information from the excerpts. Return ONLY the markdown content — no preamble, no code fences.
"""


NEW_FACT_PAGE_TEMPLATE = """Draft a wiki fact page for '{name}'.

This fact was extracted from the source: '{source_title}' (sources/{source_slug}.md)

The source describes it as:
{description}

Here are some relevant excerpts from the source:
{excerpts}

Related pages also mentioned in this source (use [[wikilinks]] to connect to them):
{related}

Use the supplied confidence level as a hint: {confidence}

Write a complete markdown page with:
1. YAML frontmatter (title, type: fact, tags, created: {today}, updated: {today}, sources: ["sources/{source_slug}.md"], confidence)
2. An H1 heading matching the title
3. These sections:
   - ## Claim
   - ## Evidence
   - ## Why It Matters
4. Keep the wording precise and evidence-backed. If the source is suggestive rather than conclusive, say so.
5. Cite every section with [[sources/{source_slug}]]
6. Link relevant entities, concepts, facts, or hypotheses using [[wikilinks]]
7. End with a '## Sources' section listing [[sources/{source_slug}]]

Do not invent facts. Only use information from the excerpts. Return ONLY the markdown content — no preamble, no code fences.
"""


NEW_HYPOTHESIS_PAGE_TEMPLATE = """Draft a wiki hypothesis page for '{name}'.

This hypothesis was extracted from the source: '{source_title}' (sources/{source_slug}.md)

The source describes it as:
{description}

Here are some relevant excerpts from the source:
{excerpts}

Related pages also mentioned in this source (use [[wikilinks]] to connect to them):
{related}

Use the supplied confidence level as a hint: {confidence}

Write a complete markdown page with:
1. YAML frontmatter (title, type: hypothesis, tags, created: {today}, updated: {today}, sources: ["sources/{source_slug}.md"], confidence)
2. An H1 heading matching the title
3. These sections:
   - ## Hypothesis
   - ## Why It Might Matter
   - ## Evidence Needed
   - ## Open Questions
4. Keep the tone explicitly tentative. Hypotheses are not established facts.
5. Cite every section with [[sources/{source_slug}]]
6. Link relevant entities, concepts, facts, or hypotheses using [[wikilinks]]
7. End with a '## Sources' section listing [[sources/{source_slug}]]

Do not invent facts. Only use information from the excerpts. Return ONLY the markdown content — no preamble, no code fences.
"""


NEW_PAGE_TEMPLATES = {
    "entity": NEW_ENTITY_PAGE_TEMPLATE,
    "concept": NEW_CONCEPT_PAGE_TEMPLATE,
    "fact": NEW_FACT_PAGE_TEMPLATE,
    "hypothesis": NEW_HYPOTHESIS_PAGE_TEMPLATE,
}


def build_draft_page_messages(
    kind: str,
    name: str,
    source_title: str,
    source_slug: str,
    description: str,
    excerpts: str,
    related: list[str],
    today: str,
    confidence: str = "medium",
) -> list[ChatMessage]:
    """Pass 2 — draft a single new page."""
    template = NEW_PAGE_TEMPLATES[kind]
    related_str = "\n".join(f"  - [[{r}]]" for r in related) if related else "  (none)"
    user_content = template.format(
        name=name,
        source_title=source_title,
        source_slug=source_slug,
        description=description,
        excerpts=excerpts,
        related=related_str,
        today=today,
        confidence=confidence,
    )
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Pass 2b — Merge new info into an existing page
# ---------------------------------------------------------------------------

MERGE_PAGE_TEMPLATE = """Update the following existing wiki page with new information from a new source.

---EXISTING PAGE---
{existing_content}
---END EXISTING PAGE---

---NEW SOURCE---
Title: {source_title}
Source slug: {source_slug}

The source describes '{name}' as:
{description}

Relevant excerpts from the new source:
{excerpts}
---END NEW SOURCE---

Update the page by:
1. Preserving ALL existing content — do not delete or silently rewrite existing paragraphs.
2. Adding new information in an appropriate section. If the new source creates tension or uncertainty, add an '## Updates' or '## Quality Notes' section.
3. Updating the 'updated:' date in frontmatter to {today}.
4. Adding "sources/{source_slug}.md" to the 'sources:' list in frontmatter (keep existing entries).
5. Keeping the page's distinction between established facts and tentative hypotheses.
6. Adding [[sources/{source_slug}]] to the '## Sources' section at the bottom.
7. Keeping any existing [[wikilinks]] intact.

Return ONLY the complete updated markdown page — no preamble, no code fences.
"""


def build_merge_page_messages(
    name: str,
    existing_content: str,
    source_title: str,
    source_slug: str,
    description: str,
    excerpts: str,
    today: str,
) -> list[ChatMessage]:
    """Pass 2b — merge new information into an existing page."""
    user_content = MERGE_PAGE_TEMPLATE.format(
        name=name,
        existing_content=existing_content,
        source_title=source_title,
        source_slug=source_slug,
        description=description,
        excerpts=excerpts,
        today=today,
    )
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Pass 3 — Source summary page
# ---------------------------------------------------------------------------

SOURCE_PAGE_TEMPLATE = """Draft a source summary page for the ingested research document.

Source details:
- Title: {source_title}
- Slug: {source_slug}
- File path: {file_path}
- Raw file link: {raw_relative_link}
- File type: {file_type}
- Ingested: {today}

Summary: {summary}

Key takeaways:
{key_takeaways}

Extracted facts:
{facts}

Hypotheses / open questions:
{hypotheses}

Quality watchouts:
{quality_watchouts}

Tags: {tags}

Entity pages created/updated from this source:
{entity_links}

Concept pages created/updated from this source:
{concept_links}

Fact pages created/updated from this source:
{fact_links}

Hypothesis pages created/updated from this source:
{hypothesis_links}

Write a complete markdown page with:
1. YAML frontmatter: title, type: source, tags, created: {today}, updated: {today}, file_path, file_type
2. An H1 heading matching the title
3. A 'Raw Resource' section that lists the file path and includes a markdown link to the raw file
4. A 'Summary' section with the summary paragraph
5. A 'Key Takeaways' section with the takeaways as bullets, each cited with [[sources/{source_slug}]]
6. An 'Extracted Facts' section with bullets linking to the fact pages
7. A 'Hypotheses' section with bullets linking to the hypothesis pages
8. A 'Quality Watchouts' section with bullets for confounders, missing evidence, or caveats
9. A 'Related Pages' section with subsections for Entities, Concepts, Facts, Hypotheses
10. No made-up facts — only use what's provided above

Return ONLY the markdown content — no preamble, no code fences.
"""


def build_source_page_messages(
    source_title: str,
    source_slug: str,
    file_path: str,
    raw_relative_link: str,
    file_type: str,
    summary: str,
    key_takeaways: list[str],
    tags: list[str],
    entity_slugs: list[str],
    concept_slugs: list[str],
    fact_slugs: list[str],
    hypothesis_slugs: list[str],
    facts: list[tuple[str, str, str]],
    hypotheses: list[tuple[str, str, str]],
    quality_watchouts: list[str],
    today: str,
) -> list[ChatMessage]:
    """Pass 3 — draft the sources/<slug>.md summary page."""
    takeaways_str = "\n".join(f"- {t}" for t in key_takeaways) or "- (none)"
    facts_str = (
        "\n".join(f"- [[facts/{slug}|{name}]] — {description}" for slug, name, description in facts)
        if facts
        else "- (none)"
    )
    hypotheses_str = (
        "\n".join(
            f"- [[hypotheses/{slug}|{name}]] — {description}"
            for slug, name, description in hypotheses
        )
        if hypotheses
        else "- (none)"
    )
    watchouts_str = (
        "\n".join(f"- {item}" for item in quality_watchouts)
        if quality_watchouts
        else "- (none noted)"
    )
    entity_links = (
        "\n".join(f"- [[entities/{s}]]" for s in entity_slugs)
        if entity_slugs
        else "- (none)"
    )
    concept_links = (
        "\n".join(f"- [[concepts/{s}]]" for s in concept_slugs)
        if concept_slugs
        else "- (none)"
    )
    fact_links = (
        "\n".join(f"- [[facts/{s}]]" for s in fact_slugs)
        if fact_slugs
        else "- (none)"
    )
    hypothesis_links = (
        "\n".join(f"- [[hypotheses/{s}]]" for s in hypothesis_slugs)
        if hypothesis_slugs
        else "- (none)"
    )
    user_content = SOURCE_PAGE_TEMPLATE.format(
        source_title=source_title,
        source_slug=source_slug,
        file_path=file_path,
        raw_relative_link=raw_relative_link,
        file_type=file_type,
        summary=summary,
        key_takeaways=takeaways_str,
        facts=facts_str,
        hypotheses=hypotheses_str,
        quality_watchouts=watchouts_str,
        tags=", ".join(tags),
        entity_links=entity_links,
        concept_links=concept_links,
        fact_links=fact_links,
        hypothesis_links=hypothesis_links,
        today=today,
    )
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Deep lint prompts
# ---------------------------------------------------------------------------

CONTRADICTION_DETECTION_PROMPT = """You are reviewing two wiki pages for potential contradictions.

Page A: {path_a}
---
{content_a}
---

Page B: {path_b}
---
{content_b}
---

Compare the factual claims made in these two pages. If you find a clear
contradiction between them, describe it concisely in 1-3 sentences, naming
the specific conflicting claims.

Only flag REAL contradictions — direct factual disagreements, not stylistic
differences or different levels of detail. If a claim in one page simply
elaborates on a claim in the other, that's NOT a contradiction.

If there is no contradiction, respond with exactly the word: NONE

Otherwise, respond with a brief description of the contradiction. Do not
include preamble like "I found" — just state the conflict directly.
"""


QUALITY_REVIEW_PROMPT = """You are the skeptic / quality-review agent for an LLM-compiled research wiki.

Review the page below for:
- unsupported or weakly supported claims
- overgeneralization or drift beyond what the cited sources justify
- hypotheses stated too confidently
- missing evidence or unclear provenance
- internal inconsistencies

Page: {path}
---
{content}
---

Return ONLY valid JSON matching this schema:

{
  "issues": [
    {
      "severity": "warning | info",
      "kind": "lack_of_evidence | overgeneralization | hypothesis_as_fact | internal_inconsistency | weak_provenance",
      "message": "A concise description of the problem",
      "suggestion": "A concise fix or follow-up action"
    }
  ]
}

Rules:
- If the page looks solid, return {"issues": []}
- Only flag issues with a concrete basis in the page content
- Keep each issue short and actionable
- Do not include markdown fences or explanatory prose
"""
