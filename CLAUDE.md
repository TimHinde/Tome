# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

**Tome** is a local **MCP (Model Context Protocol) server** for TTRPG Game Masters. It parses existing tabletop RPG materials into structured Obsidian vaults. The AI acts as a librarian: parsing, organizing, and reformatting content — **never inventing new game content**.

## Core Rule: No Hallucination

**Do not invent game rules, stats, NPC motives, spells, or any other TTRPG content.** All output must be strictly derived from provided source material. If information is not present in the source, say so. Our fundamental purpose is to *parse human written content*, not generate AI content.

## Commands

All commands use the project virtualenv at `venv/`:

```bash
# Run the MCP server (stdio transport)
venv/bin/python server.py

# Run the full test suite
venv/bin/python -m unittest test_obsidian.py test_merge.py -v

# Run individual test scripts
venv/bin/python test_pdf.py
venv/bin/python test_reference.py
```

Environment variables (`.env` file at project root):
- `GEMINI_API_KEY` — required for `extract_entities_llm` with `provider="gemini"` (default)
- `ANTHROPIC_API_KEY` — required for `extract_entities_llm` with `provider="claude"`
- `OPENAI_API_KEY` — required for `extract_entities_llm` with `provider="openai"`

## Architecture

The MCP server (`server.py`) wraps tool modules and exposes them via `FastMCP("tome")`:

| Module | Purpose |
|---|---|
| `pdf_tools.py` | PDF → text via PyMuPDF. TOC analysis, page-range extraction, chunk suggestion. |
| `reference_tools.py` | System-agnostic reference search. Reads markdown files from any reference directory. Ships with D&D 5.2e SRD as default. |
| `obsidian_tools.py` | LLM entity extraction, entity merging, reference enrichment, Obsidian vault generation with `_Home.md` index. |
| `server.py` | FastMCP entrypoint. Registers all tools and runs stdio transport. |

### Composable Tool Workflow

See `WORKFLOWS.md` for the full 7-step orchestration guide. The core tools:

1. **`analyze_pdf`** / **`suggest_pdf_chunks`** — Discover document structure and plan extraction chunks.
2. **`extract_pdf_text`** — Pull raw text for a page range.
3. **`extract_entities_with_llm`** — LLM extracts both chapter-scoped and global reference entities.
4. **`merge_entity_dicts`** — Combine + deduplicate results from multiple extraction chunks.
5. **`enrich_entities`** — Cross-reference against local reference material (statblocks, rules text).
6. **`generate_obsidian_markdown(entities, output_dir, mode)`** — Write Obsidian vault. Modes: `"adventure"`, `"campaign_setting"`, `"auto"` (default, detects from data).

### Data Shape

```json
{
  "chapters": [{
    "name": "Chapter 1: ...",
    "overview": "...",
    "npcs": [{"name":"", "motivation":"", "secret":"", "statblock":"", "location":""}],
    "locations": [{"name":"", "description":"", "encounters":[], "loot":[], "exits":[]}],
    "encounters": [{"name":"", "read_aloud":"", "description":"", "mechanics":"", "monsters":[], "npcs_present":[]}],
    "events": [{"name":"", "read_aloud":"", "description":"", "mechanics":"", "next_steps":"", "npcs_present":[]}],
    "items": [{"name":"", "rarity":"", "description":"", "mechanics":""}],
    "monsters": [{"name":"", "statblock":""}]
  }],
  "races": [{"name":"", "description":"", "subraces":[], "asi":{}, "speed":30, "size":"Medium", "traits":[], "languages":[]}],
  "classes": [{"name":"", "base_class":"", "type":"class|subclass", "description":"", "features":[]}],
  "spells": [{"name":"", "level":0, "school":"", "casting_time":"", "range":"", "components":"", "duration":"", "classes":[], "description":""}],
  "deities": [{"name":"", "alignment":"", "domains":[], "symbol":"", "description":""}],
  "backgrounds": [{"name":"", "description":"", "skill_proficiencies":[], "tool_proficiencies":[]}],
  "feats": [{"name":"", "prerequisite":"", "description":"", "benefits":[]}],
  "factions": [{"name":"", "type":"", "description":"", "goals":"", "members":[], "base_of_operations":""}],
  "lore_entries": [{"name":"", "category":"", "description":"", "related_entities":[]}]
}
```

## Reference Material

Local reference material is in `references/`. The D&D 5.2e SRD ships as default at `references/SRD/dndsrd5.2_markdown/src/`. Tome is system-agnostic — point `reference_dir` at any folder of markdown files.

> *This work includes material from the System Reference Document 5.2 ("SRD 5.2") by Wizards of the Coast LLC. Licensed under CC BY 4.0.*

## Output Style

GM notes should be punchy, bulleted, and action-focused. Prioritize "what you need to know right now" over flowing prose.

## Privacy

RPG materials are often copyrighted. Processing must remain local. The only external call is the LLM API for entity extraction.
