# Tome

**Parse any TTRPG adventure PDF into a ready-to-use Obsidian vault.**

> **Important Note:** Tome's purpose is to *parse human-written content*, **not** generate new AI content. It simply uses AI to help extract and organize existing text from your adventure modules into structured notes.

Tome is a local MCP (Model Context Protocol) server that helps Game Masters process existing tabletop RPG materials. It acts as a librarian: parsing, organizing, and reformatting content from adventure books into interconnected, searchable Obsidian notes.

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
- `OPENAI_API_KEY` — required for entity extraction with OpenAI (gpt-4o)

## Integrating with Chat Apps (For Non-Technical Users)

You can easily use Tome directly within your favorite AI chat applications using the Model Context Protocol (MCP). Here's how to set it up:

### Claude Desktop
1. Open Claude Desktop.
2. Go to **Settings** -> **Developer** and click **Edit Config**.
3. This will open the `claude_desktop_config.json` file. Add the following to the `mcpServers` section:
   ```json
   {
     "mcpServers": {
       "tome": {
         "command": "/absolute/path/to/Tome/venv/bin/python",
         "args": ["/absolute/path/to/Tome/server.py"],
         "env": {
           "GEMINI_API_KEY": "your_gemini_key_here",
           "OPENAI_API_KEY": "your_openai_key_here",
           "ANTHROPIC_API_KEY": "your_anthropic_key_here"
         }
       }
     }
   }
   ```
   *(Make sure to replace `/absolute/path/to/Tome` with the actual path to your Tome folder, and fill in at least one API key).*
4. Save the file and restart Claude Desktop.

### Cursor
1. Open Cursor and go to **Settings**.
2. Search for **MCP** or go to the **Features** -> **MCP** section.
3. Click **+ Add new MCP server**.
4. Set the Type to **command**.
5. Set the Name to `tome`.
6. Set the Command to: `/absolute/path/to/Tome/venv/bin/python /absolute/path/to/Tome/server.py`
7. Click Save. (Make sure you have your API keys set in a `.env` file in the Tome project root).

### Roo Code / Cline
1. Open the Roo Code settings panel.
2. Go to the **MCP Servers** tab.
3. Edit the `mcp_settings.json` file with the same configuration block shown above for Claude Desktop.

## The Pipeline

Tome processes adventures through a 3-step pipeline:

```
Adventure PDF → Extract Entities → Enrich with References → Obsidian Vault
```

### Step 1: Extract Entities (`extract_entities_llm`)
Send raw adventure text to an LLM (Gemini, Claude, or OpenAI). Returns structured JSON with chapters containing NPCs, Locations, Encounters, Events, Items, and Monsters.

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

> *Tome is an independent product published under the Nimble 3rd Party Creator License. Nimble © Nimble Co. Tome is not affiliated with, endorsed by, or officially connected to Nimble Co. in any way.*

## Architecture

```
server.py              FastMCP entrypoint — registers all tools
├── pdf_tools.py       PDF → text (PyMuPDF)
├── reference_tools.py Local reference search (header-priority regex)
└── obsidian_tools.py  LLM extraction + enrichment + Obsidian generation
```

## Privacy

RPG materials are often copyrighted. Tome processes everything locally. The only external call is the LLM API for entity extraction.
