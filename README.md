# Tome

**Parse any TTRPG adventure PDF into a ready-to-use Obsidian vault.**

Tome is a local MCP (Model Context Protocol) server that helps Game Masters process existing tabletop RPG materials — not generate new content. It acts as a librarian: parsing, organizing, and reformatting content from adventure books into interconnected, searchable Obsidian notes.

## Quick Start

```bash
# Run the MCP server (stdio transport, for use with Claude Desktop, Gemini, etc.)
venv/bin/python server.py

# Run tests
venv/bin/python -m unittest test_obsidian.py -v
```

Environment variables (`.env` file at project root):
- `GEMINI_API_KEY` — required for entity extraction with Gemini (default)
- `ANTHROPIC_API_KEY` — required for entity extraction with Claude

## The Pipeline

Tome processes adventures through a 3-step pipeline:

```
Adventure PDF → Extract Entities → Enrich with References → Obsidian Vault
```

### Step 1: Extract Entities (`extract_entities_llm`)
Send raw adventure text to an LLM (Gemini or Claude). Returns structured JSON with chapters containing NPCs, Locations, Encounters, Events, Items, and Monsters.

### Step 2: Enrich with References (`enrich_with_references`)
Walks through extracted entities and cross-references them against local reference material (e.g. the D&D 5.2e SRD). Injects statblocks and rules text directly into the data. *Optional — works with any system's reference docs.*

### Step 3: Generate Obsidian (`generate_obsidian`)
Writes the enriched data to disk as a nested Obsidian vault with:
- **YAML frontmatter** with `chapter`, `location`, `motivation`, `monsters`, `rarity` fields for Dataview queries
- **`[[wikilinks]]`** connecting entities across the vault
- **`_Home.md`** index page with static summary tables and live Dataview query blocks
- **Chapter folders** with subfolders for NPCs, Locations, Encounters, Events, Items, Monsters

## MCP Tools

| Tool | Purpose |
|---|---|
| `analyze_pdf` | Extract TOC and detect document type from a PDF |
| `extract_pdf_text` | Extract raw text from a page range |
| `extract_entities_with_llm` | LLM-powered entity extraction → structured JSON |
| `extract_entities_with_heuristics` | Regex fallback when no LLM is available |
| `enrich_entities` | Cross-reference entities against local reference material |
| `generate_obsidian_markdown` | Write enriched entities as an Obsidian vault |
| `query_references` | Search local reference markdown files |
| `list_references` | List available reference topics |

## Entity Model

- **NPCs:** Name, Motivation, Secret, Statblock Reference, Location
- **Locations:** Name, Read-Aloud Description, Encounters, Loot, Exits
- **Encounters:** Name, Read-Aloud, Description, Mechanics, Monsters, NPCs Present
- **Events:** Name, Description, Mechanics, Next Steps
- **Items:** Name, Rarity, Description, Mechanics
- **Monsters:** Name, Statblock

## Reference Material

The D&D 5.2e SRD ships as the default reference pack in `references/SRD/`. Tome is system-agnostic — you can point the `reference_dir` parameter at any folder of markdown files to use reference material from Pathfinder, Call of Cthulhu, or any other system.

> *This work includes material from the System Reference Document 5.2 ("SRD 5.2") by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2 is licensed under the Creative Commons Attribution 4.0 International License.*

## Architecture

```
server.py              FastMCP entrypoint — registers all tools
├── pdf_tools.py       PDF → text (PyMuPDF)
├── reference_tools.py Local reference search (header-priority regex)
└── obsidian_tools.py  LLM extraction + enrichment + Obsidian generation
```

## Privacy

RPG materials are often copyrighted. Tome processes everything locally. The only external call is the LLM API for entity extraction.
