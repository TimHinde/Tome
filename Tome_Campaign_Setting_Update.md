# Tome MCP — Campaign Setting Support Update

I've completed the implementation for Phases 1 through 4 of the Campaign Setting Support feature! The codebase has been updated to support global entity extraction, a composable tool workflow, and campaign setting folder structures. 

Here is a summary of the completed work for handoff:

## Artifacts for Context

- **Implementation Plan:** [/home/mumble/.gemini/antigravity/brain/d599583f-9143-4789-a0fe-b4c0186eae7f/implementation_plan.md](file:///home/mumble/.gemini/antigravity/brain/d599583f-9143-4789-a0fe-b4c0186eae7f/implementation_plan.md)
- **Task List:** [/home/mumble/.gemini/antigravity/brain/d599583f-9143-4789-a0fe-b4c0186eae7f/task.md](file:///home/mumble/.gemini/antigravity/brain/d599583f-9143-4789-a0fe-b4c0186eae7f/task.md)

---

## Completed Phases

### 1. Phase 1: Entity Types & Extraction (`obsidian_tools.py`)
- Expanded `extract_entities_llm` to instruct the LLM to extract 8 new global entity types (`races`, `classes`, `spells`, `deities`, `backgrounds`, `feats`, `factions`, `lore_entries`) alongside the existing `chapters` array.
- Updated `extract_entities_heuristic` (regex fallback) to recognize and extract these new types into top-level lists.

### 2. Phase 2: Folder Structure & Markdown Writers (`obsidian_tools.py`)
- Added a `mode` parameter to `generate_obsidian` with auto-detection logic (if global entities or top-level monsters are present, it uses `campaign_setting` mode).
- Implemented 8 new Markdown writers for the global entity types, outputting files to top-level category folders (e.g., `Races/Elf.md`, `Spells/Fireball.md`).
- Added idempotency dedup logic (`if not filepath.exists()`) to all 14 entity writers to support safe re-running during multi-chunk merges.

### 3. Phase 3: Home Page & Detection Fixes (`pdf_tools.py` & `obsidian_tools.py`)
- Replaced the static table in `_Home.md` with dynamic, idempotent Dataview queries for `Chapters`, `NPCs`, `Encounters`, `Items`, `Locations`, and `Bestiary`.
- Added corresponding Dataview queries for the new global entity types, which are only appended in `campaign_setting` mode.
- Added heuristic detection in `pdf_tools.py` `analyze_pdf_structure` to guess `Campaign Setting` and `Supplement` document types based on TOC keywords.

### 4. Phase 4: MCP Server — Composable Tools (`server.py` & `WORKFLOWS.md`)
- Re-architected the orchestration approach from a monolithic pipeline to composable tools.
- Added a `suggest_pdf_chunks` tool to break down PDFs based on TOC boundaries.
- Added a `merge_entity_dicts` tool to combine multiple extraction results (applying first-write-wins dedup).
- Created `WORKFLOWS.md` in the project root providing a detailed 7-step guide (Discover, Plan, Chunk, Extract, Merge, Enrich, Generate) for AI agents to follow.

### 5. Verification & State
- Ran targeted import checks (using the project's venv) to ensure no syntax or circular dependency errors were introduced in the updated files.
- Updated the `task.md` artifact to check off Phases 1 through 4.

## Remaining for Handoff (Phase 5):
- Update existing `pytest` files to handle the new `mode` parameter and newly added global entities.
- Write new tests for the folder structures, deduplication logic, and `suggest_chunks`.
- Update `CLAUDE.md` to document the new `mode` and data shapes.

The workspace is stable and ready for the next agent to pick up Phase 5.
