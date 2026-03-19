# Tome — TTRPG Document Parsing Workflow

A generic, step-by-step guide for parsing any TTRPG PDF into Obsidian Markdown notes. This workflow is designed to be followed by an LLM assistant using Tome's composable MCP tools.

## Available Tools

| Tool | Purpose |
|---|---|
| `analyze_pdf` | Extract TOC and detect document type |
| `suggest_pdf_chunks` | Get TOC-aware page-range suggestions |
| `extract_pdf_text` | Pull raw text from a page range |
| `extract_entities_with_llm` | LLM-powered entity extraction |
| `extract_entities_with_heuristics` | Regex fallback extraction |
| `merge_entity_dicts` | Combine & deduplicate extraction results |
| `enrich_entities` | Cross-reference against SRD/rules |
| `generate_obsidian_markdown` | Write Obsidian vault files |
| `query_references` | Search reference material |
| `list_references` | Browse available reference topics |

---

## Step 1: Discover

**Goal:** Understand the document structure and type.

```
result = analyze_pdf(pdf_path)
```

Review the output:
- **Document Type** — Adventure, Campaign Setting, Supplement, Rulebook, or Bestiary
- **Table of Contents** — Chapter/section names and page numbers

> [!TIP]
> The document type is a heuristic guess. Use your own judgement to override if needed.

---

## Step 2: Plan

**Goal:** Decide what to extract and what to skip.

Based on the TOC and document type, decide:

| Document Type | What to Extract | What to Skip |
|---|---|---|
| **Adventure** | Story chapters, encounters, NPCs, maps | Appendices with reprinted rules, ads |
| **Campaign Setting** | World lore, races, classes, deities, factions, spells, player options | Index pages, credits, reprinted core rules |
| **Supplement** | Player options (races, classes, spells, feats, backgrounds) | Previews of other products |
| **Rulebook** | Reference chapters relevant to play | Everything (these are for SRD reference, not vault notes) |
| **Bestiary** | Monster entries | Ecology essays, habitat descriptions (unless desired) |

> [!NOTE]
> Many books are hybrid (e.g., a Campaign Setting with adventure chapters). Plan accordingly — the LLM extraction will classify entities into the right buckets automatically.

---

## Step 3: Chunk

**Goal:** Get smart page ranges for extraction.

```
chunks = suggest_pdf_chunks(pdf_path)
```

This returns a list of `{name, start_page, end_page}` based on the TOC.

**Adjust as needed:**
- Merge small adjacent chapters into one chunk
- Split very large chapters (50+ pages) into sub-ranges
- Remove chunks you decided to skip in Step 2

> [!IMPORTANT]
> Keep chunks under ~30 pages for best LLM extraction quality. Larger chunks may cause the LLM to miss entities or lose context.

---

## Step 4: Extract

**Goal:** Pull text and extract entities from each chunk.

For each chunk you want to process:

```python
# 1. Get the raw text
text = extract_pdf_text(pdf_path, chunk.start_page, chunk.end_page)

# 2. Extract entities
entities = extract_entities_with_llm(text, provider="gemini")
```

Repeat for all chunks. Store each extraction result.

> [!TIP]
> If the LLM API is unavailable, use `extract_entities_with_heuristics(text)` as a fallback. Quality will be lower but the pipeline continues.

---

## Step 5: Merge

**Goal:** Combine all extraction results and deduplicate.

```
merged = merge_entity_dicts([chunk1_entities, chunk2_entities, ...])
```

This:
- Combines chapters by name
- Deduplicates entities within each type (first-write-wins by name)
- Merges global arrays (races, spells, deities, etc.)

---

## Step 6: Enrich

**Goal:** Cross-reference entities with SRD/reference material.

```
enriched = enrich_entities(merged)
```

This queries the bundled reference material (D&D 5e SRD by default) to add:
- NPC statblocks
- Monster stats for encounters
- Item rules text

Pass `reference_dirs` for custom systems (Pathfinder, homebrew, etc.).

---

## Step 7: Generate

**Goal:** Write the Obsidian vault.

```
files = generate_obsidian_markdown(enriched, output_dir, mode="auto")
```

**Modes:**
- `auto` (default) — Detects from entity data. Uses `campaign_setting` if global arrays (races, spells, etc.) are present, otherwise `adventure`.
- `adventure` — Chapter-scoped subfolders only.
- `campaign_setting` — Top-level folders for global entities (Races/, Spells/, Deities/, etc.) plus chapter folders for adventure content.

The output includes:
- `_Home.md` — Vault index with Dataview queries
- Chapter files with entity indexes and session flow
- Individual entity notes with YAML frontmatter for Dataview

---

## Quick Reference: Full Pipeline

```
# 1. Discover
toc = analyze_pdf("/path/to/book.pdf")

# 2. Plan (you decide what to extract)

# 3. Chunk
chunks = suggest_pdf_chunks("/path/to/book.pdf")

# 4. Extract
results = []
for chunk in selected_chunks:
    text = extract_pdf_text("/path/to/book.pdf", chunk.start_page, chunk.end_page)
    entities = extract_entities_with_llm(text)
    results.append(entities)

# 5. Merge
merged = merge_entity_dicts(results)

# 6. Enrich
enriched = enrich_entities(merged)

# 7. Generate
files = generate_obsidian_markdown(enriched, "/path/to/vault")
```
