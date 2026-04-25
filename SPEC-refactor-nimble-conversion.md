# Spec: Refactor Nimble Conversion Tools — Remove Internal LLM Calls

## Context

The Tome MCP server (`/home/mumble/Desktop/TTRPG/Tome/`) is a local MCP server for TTRPG Game Masters.
It currently has two tools that convert D&D 5e monsters to Nimble RPG 2e format:

- `convert_5e_monster_to_nimble` (in `server.py`, implemented in `obsidian_tools.py`)
- `convert_5e_bestiary_to_nimble` (in `server.py`, implemented in `nimble_tools.py`)

Both tools internally call a separate LLM API (Anthropic/Gemini/OpenAI) to do the conversion work.
This is wasteful — the tools are always invoked *by* a capable LLM (Claude Code), which can do the
conversion itself if given the right reference material. The internal API calls add latency, cost,
and a fragile external dependency.

## Goal

Remove the internal LLM calls from both conversion tools. Instead, each tool should:
1. Load the relevant source data (statblock or bestiary files)
2. Load the Nimble 2e reference material from `references/nimble/`
3. Return all of that as structured context to the calling LLM (Claude Code)

The calling LLM then does the conversion and writes the output file(s) directly.

## Reference Material

Nimble 2e reference docs live at `references/nimble/`:
- `nimble_core_mechanics.md`
- `nimble_monster_creation.md`
- `nimble_monster_roles.md`
- `nimble_conditions.md`
- `nimble_damage_types.md`

The `_render_nimble_monster()` function in `obsidian_tools.py` defines the exact Obsidian markdown
output format. Keep this function — the calling LLM should be told to produce output matching it.

## Changes Required

### 1. `convert_5e_monster_to_nimble` in `obsidian_tools.py`

**Current behaviour:** Takes a raw statblock string, wraps it in an entities dict, calls
`convert_entities_to_nimble()` (which fires an LLM API call), then renders the result.

**New behaviour:** 
- Accept the same `statblock: str` input
- Load and concatenate all files from `references/nimble/` into a reference string
- Return a plain dict with:
  ```python
  {
      "statblock": <the input statblock>,
      "nimble_reference": <concatenated reference material>,
      "output_format": <the markdown template — i.e. describe _render_nimble_monster's format>,
      "instructions": "Convert the statblock to Nimble 2e using the reference material. Output Obsidian markdown matching the output_format."
  }
  ```
- Do NOT call `_get_llm_response` or `convert_entities_to_nimble`
- Do NOT write any files — just return context

### 2. `convert_5e_bestiary_to_nimble` in `nimble_tools.py`

**Current behaviour:** Reads markdown files from an input dir in batches, calls `extract_entities_llm`
then `convert_entities_to_nimble` (both LLM calls), then calls `generate_obsidian` to write files.

**New behaviour:**
- Accept the same `input_dir: str` and `output_dir: str` inputs (drop `provider` and `batch_size`)
- Read all `.md` files from `input_dir`
- Load and concatenate all files from `references/nimble/`
- Return a dict with:
  ```python
  {
      "statblocks": [{"filename": <name>, "content": <text>}, ...],
      "nimble_reference": <concatenated reference material>,
      "output_dir": <output_dir>,
      "output_format": <describe _render_nimble_monster's format>,
      "instructions": "Convert each statblock to Nimble 2e using the reference material. Write one Obsidian markdown file per monster to output_dir, named <monster-name-kebab-case>.md."
  }
  ```
- Do NOT call any LLM functions
- Do NOT write any files — just return context

### 3. `convert_entities_to_nimble` in `nimble_tools.py`

This function exists solely to drive the LLM conversion loop. Once the above changes are made it has
no callers. **Delete it.**

### 4. `_get_llm_response` in `nimble_tools.py`

Check for remaining callers after the above changes. If none remain, **delete it** along with the
`import anthropic`, `import openai`, and `from google import genai` imports.

### 5. `server.py` — MCP tool signatures

Update the docstrings for both MCP-exposed tools to reflect their new behaviour:
they now return context for the calling LLM rather than performing the conversion themselves.
Remove any mention of `provider` or `batch_size` parameters from the `convert_5e_bestiary_to_nimble`
tool registration if those params are dropped.

### 6. `CLAUDE.md` — update environment variable docs

`ANTHROPIC_API_KEY` is no longer required for Nimble conversion. Update the relevant bullet point.
If no other tools require it either, remove the entry entirely.

## What NOT to change

- `_render_nimble_monster()` — keep as-is; it defines the canonical output format
- `generate_obsidian()` — keep as-is; used by other pipelines
- `extract_entities_llm()` / `extract_entities_heuristic()` — keep as-is; used by other pipelines
- `references/nimble/` — do not modify reference docs
- `.env` — do not modify

## Validation

After refactoring, call `convert_5e_monster_to_nimble` with the Bronze Skeleton JSON from
`/home/mumble/Desktop/TTRPG/Campaigns/sci-fi/Dark-Matter-Bestiary/bronze-skeleton-alchemy.json`
and confirm:
- The tool returns a dict containing `statblock`, `nimble_reference`, and `instructions`
- No outbound API call is made
- The existing unit tests in `test_obsidian.py` still pass (`venv/bin/python -m unittest test_obsidian.py -v`)
