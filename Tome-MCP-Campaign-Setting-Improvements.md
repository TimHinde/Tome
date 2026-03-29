# Tome MCP — Campaign Setting Support: Design Spec

**For:** Claude Opus
**Repo:** `/home/mumble/Desktop/TTRPG/Tome/`
**Primary files to modify:** `obsidian_tools.py`, `pdf_tools.py`, `server.py`
**Context:** The Tome MCP was built around adventure modules (Chapter → encounters/events/NPCs/items). This spec extends it to handle full **campaign setting** documents that include races, classes, spells, deities, factions, and lore — content that has no natural "chapter scope" and should live in global cross-cutting folders.

---

## Background: What the Current Code Does

### `pdf_tools.py`
- `analyze_pdf_structure()` — reads the PDF TOC and heuristically classifies the document type ("Adventure", "Rulebook", "Bestiary", "Unknown").
- `extract_pdf_section()` — raw text extraction by page range.

### `obsidian_tools.py`
- `extract_entities_llm(text, provider)` — sends text to an LLM with a prompt that extracts: **chapters → { npcs, locations, encounters, events, items, monsters }**. Returns a JSON dict.
- `extract_entities_heuristic(text)` — regex fallback.
- `enrich_with_references(entities, reference_dirs)` — enriches entities by querying the SRD reference tools.
- `generate_obsidian(entities, output_dir)` — writes Markdown files. For each chapter, creates a `ChapterName/` subdirectory with subfolders: `NPCs/`, `Locations/`, `Encounters/`, `Events/`, `Items/`, `Monsters/`. Writes `_Home.md` with a chapter stats table and Dataview queries.

### Key gaps revealed by processing Humblewood:
1. **No entity types** for races, classes, spells, deities, backgrounds, feats, or factions.
2. **Everything is chapter-scoped** — reference content (races, spells, bestiary) ends up orphaned in `Arc: Uncategorized` or gets force-fit into NPCs/monsters.
3. **No "Campaign Setting" document type** — detection never fires for setting books.
4. **`_Home.md` accumulates duplicate rows** when called once per chunk.
5. **Deduplication** — the same entity extracted from two overlapping chunks creates two files.
6. **Deity pages** become NPCs with stat blocks, losing all domain/symbol/worship information.
7. **Bestiary creatures** lose stat block structure (stored as a raw string blob).
8. **Races** disappear entirely — no schema captures racial traits, ASIs, speed, or subraces.

---

## Goal

Extend the MCP to support three processing modes via a new `mode` parameter on `generate_obsidian`:

| Mode | Folder Structure | When to Use |
|---|---|---|
| `"adventure"` | Current behavior — chapter-scoped subfolders | Pure adventure modules |
| `"campaign_setting"` | Global folders for reference content; chapter folders for adventure content | Campaign settings, sourcebooks |
| `"auto"` (default) | Detected from document type | General use |

---

## Part 1: New Entity Types

### 1.1 Update the LLM extraction prompt in `extract_entities_llm()`

Add the following entity types to the JSON schema the LLM returns. These should be **top-level siblings of `chapters`** in the returned JSON object — they are global, not chapter-scoped:

```json
{
  "chapters": [...],           // existing — adventure/narrative content
  "races": [...],              // NEW
  "classes": [...],            // NEW
  "spells": [...],             // NEW
  "deities": [...],            // NEW
  "backgrounds": [...],        // NEW
  "feats": [...],              // NEW
  "factions": [...],           // NEW (optional)
  "lore_entries": [...]        // NEW (optional)
}
```

#### Schema for each new type:

**races**
```json
{
  "name": "Corvum",
  "description": "Full flavour text / lore paragraph",
  "subraces": ["Bright Corvum", "Cinder Corvum", "Stat Corvum"],
  "asi": {"WIS": 2, "CHA": 1},
  "speed": 25,
  "size": "Medium",
  "traits": [
    {"name": "Glide", "description": "When falling at least 10 feet..."},
    {"name": "Talons", "description": "Your talons are natural weapons..."}
  ],
  "languages": ["Common", "Birdfolk", "Auran"],
  "source_chapter": "Chapter 1: Welcome to the Wood"
}
```

**classes** (also handles subclasses)
```json
{
  "name": "College of the Road",
  "base_class": "Bard",
  "type": "subclass",
  "description": "Bards of the College of the Road...",
  "features": [
    {"name": "Bonus Proficiencies", "level": 3, "description": "..."},
    {"name": "Wandering Lore", "level": 6, "description": "..."}
  ],
  "source_chapter": "Chapter 1: Welcome to the Wood"
}
```

**spells**
```json
{
  "name": "Invoke the Amaranthine",
  "level": 5,
  "school": "Evocation",
  "casting_time": "1 action",
  "range": "Self",
  "components": "V, S",
  "duration": "Concentration, up to 1 minute",
  "classes": ["Cleric", "Druid"],
  "description": "Full spell description text",
  "higher_levels": "When cast at 6th level or higher...",
  "source_chapter": "Chapter 1: Welcome to the Wood"
}
```

**deities**
```json
{
  "name": "Ardea",
  "title": "The Pale Shepherd",
  "alignment": "Neutral Good",
  "domains": ["Life", "Light"],
  "symbol": "A white heron in flight",
  "worshippers": "Birdfolk, healers, midwives",
  "description": "Full lore text",
  "myths": "Relevant creation myth or tale",
  "appearance": "Physical/spiritual description",
  "personality": "How the deity manifests / their disposition",
  "source_chapter": "Chapter 2: Religion in the Wood"
}
```

**backgrounds**
```json
{
  "name": "Bandit Defector",
  "description": "You once ran with a bandit gang...",
  "skill_proficiencies": ["Deception", "Stealth"],
  "tool_proficiencies": ["Thieves' tools"],
  "languages": 1,
  "equipment": ["A set of dark common clothes...", "10 gp"],
  "feature": {"name": "Criminal Contact", "description": "..."},
  "personality_traits": ["I always have a plan...", "..."],
  "ideals": ["Freedom. Chains are meant to be broken."],
  "bonds": ["I'm trying to make up for..."],
  "flaws": ["I turn tail when things look bad."],
  "source_chapter": "Chapter 1: Welcome to the Wood"
}
```

**feats**
```json
{
  "name": "Glide Mastery",
  "prerequisite": "Birdfolk race",
  "description": "Full feat description text",
  "benefits": ["You can glide up to twice your movement speed...", "..."],
  "source_chapter": "Chapter 1: Welcome to the Wood"
}
```

**factions** (optional — include if text clearly describes an organization)
```json
{
  "name": "The Tenders",
  "type": "Religious Order",
  "description": "The Tenders are druids who maintain...",
  "goals": "Preserve the Great Rhythm and the health of the Wood",
  "members": ["Gallus Druid", "Oakheart"],
  "base_of_operations": "The Scorched Grove",
  "allies": ["The Birdfolk Council"],
  "enemies": ["Bandit Coalition"],
  "source_chapter": "Chapter 3: Traversing the Wood"
}
```

**lore_entries** (optional — world history, creation myths, cultural context)
```json
{
  "name": "The Great Rhythm",
  "category": "Cosmology",
  "description": "Full lore text",
  "related_entities": ["Ardea", "Tyton", "The Amaranthine"],
  "source_chapter": "Chapter 2: Religion in the Wood"
}
```

### 1.2 Update the extraction prompt

The LLM prompt in `extract_entities_llm()` must be updated with:

1. Definitions for each new entity type (when to use each one).
2. Guidance that races/classes/spells/deities/backgrounds/feats go in the **top-level global arrays**, not inside any chapter.
3. Guidance that campaign setting lore text that doesn't fit an encounter/event still has a home as a `lore_entry`.
4. Clarification that deity stat blocks should NOT be placed in `npcs` — they belong in `deities`.
5. Clarification that creatures with full stat blocks from a bestiary section belong in top-level `monsters` (see Part 2), not in chapter `monsters`.

Example prompt additions:
```
GLOBAL (top-level) arrays — these are reference content that exists outside any single chapter:
- RACES: Any playable species/race writeup. Capture all traits, ASIs, speeds, subraces. Do NOT place in chapters.
- CLASSES/SUBCLASSES: Class options, archetypes, subclasses. Capture all features by level. Do NOT place in chapters.
- SPELLS: Spell entries with full mechanics. Capture level, school, components, duration, full description. Do NOT place in chapters.
- DEITIES: Divine beings, gods, patron spirits. Capture domains, symbols, myths, personality — NOT as NPCs. Do NOT place in chapters.
- BACKGROUNDS: PC background options with tables. Do NOT place in chapters.
- FEATS: Feat writeups with prerequisites. Do NOT place in chapters.
- FACTIONS: Only if clearly described as an organization — capture goals, membership, allegiances. Optional.
- LORE_ENTRIES: World history, creation myths, cosmological exposition that doesn't fit an encounter or event. Optional.
```

---

## Part 2: Global Folder Structure in `generate_obsidian()`

### 2.1 Add a `mode` parameter

```python
def generate_obsidian(entities: dict, output_dir: str, mode: str = "auto") -> list[str]:
```

Resolve `"auto"` to `"campaign_setting"` if the entities dict contains any non-empty top-level global arrays (`races`, `spells`, `deities`, etc.), otherwise resolve to `"adventure"`.

### 2.2 Campaign Setting folder layout

In `"campaign_setting"` mode, global entities write to flat top-level directories **instead of** being nested under chapter subdirs:

```
output_dir/
├── _Home.md
├── Races/
│   ├── Corvum.md
│   ├── Gallus.md
│   └── ...
├── Classes/
│   ├── College of the Road.md
│   └── ...
├── Spells/
│   ├── Invoke the Amaranthine.md
│   └── ...
├── Deities/
│   ├── Ardea.md
│   ├── Tyton.md
│   └── ...
├── Bestiary/                   ← top-level monsters with full stat blocks
│   ├── Ashsnake.md
│   ├── Aspect of Fire.md
│   └── ...
├── Backgrounds/
│   └── Bandit Defector.md
├── Feats/
│   └── Glide Mastery.md
├── Factions/                   ← optional, only if entities present
│   └── The Tenders.md
├── Lore/                       ← optional
│   └── The Great Rhythm.md
├── Part 1 The Adventure Begins/
│   ├── Part 1 The Adventure Begins.md
│   ├── NPCs/
│   ├── Locations/
│   ├── Encounters/
│   ├── Events/
│   └── Items/
│       (no Monsters/ here — they link to /Bestiary/)
└── ...
```

Adventure chapters still use their current per-chapter structure, but their `monsters` lists should **link** to `/Bestiary/<name>` rather than creating local copies.

### 2.3 Markdown templates for new entity types

#### Race file (`Races/Corvum.md`)
```markdown
---
tags: [Race]
source_chapter: "Chapter 1: Welcome to the Wood"
size: Medium
speed: 25
asi: {WIS: 2, CHA: 1}
subraces:
  - Bright Corvum
  - Cinder Corvum
  - Stat Corvum
---

# Corvum

> [!info] At a Glance
> **Size:** Medium | **Speed:** 25 ft. | **ASI:** WIS +2, CHA +1

{description}

## Racial Traits

### Trait Name
{trait description}

## Subraces

### Bright Corvum
{subrace content if available}

## Languages
{languages}
```

#### Deity file (`Deities/Ardea.md`)
```markdown
---
tags: [Deity, Amaranthine]
source_chapter: "Chapter 2: Religion in the Wood"
alignment: Neutral Good
domains:
  - Life
  - Light
symbol: "A white heron in flight"
---

# Ardea — The Pale Shepherd

> [!info] Divine Profile
> **Alignment:** Neutral Good | **Domains:** Life, Light
> **Symbol:** A white heron in flight
> **Worshippers:** {worshippers}

{description}

## Myths & Stories
{myths}

## Appearance
{appearance}

## Personality
{personality}
```

#### Spell file (`Spells/Invoke the Amaranthine.md`)
```markdown
---
tags: [Spell]
source_chapter: "Chapter 1: Welcome to the Wood"
level: 5
school: Evocation
casting_time: "1 action"
range: Self
components: "V, S"
duration: "Concentration, up to 1 minute"
classes:
  - Cleric
  - Druid
---

# Invoke the Amaranthine
*5th-level Evocation*

**Casting Time:** 1 action
**Range:** Self
**Components:** V, S
**Duration:** Concentration, up to 1 minute
**Classes:** Cleric, Druid

{description}

**At Higher Levels.** {higher_levels}
```

#### Bestiary creature file (`Bestiary/Ashsnake.md`)
```markdown
---
tags: [Monster, Bestiary]
cr: "5"
type: Beast
habitat: "Scorched Grove"
source_chapter: "Appendix A: Bestiary"
---

# Ashsnake

> [!danger]- Stat Block
> {statblock}

## Tactical Notes
{Any GM notes extracted about tactics, lair actions, etc.}

## Appears In
- [[Part 3 An Urgent Summons]]
```

---

## Part 3: Deduplication Registry

### Problem
When `generate_obsidian` is called multiple times (once per chunk), the same entity (e.g. "Eliza Pennygleam") gets written multiple times. Currently the code checks `if not m_filepath.exists()` only for SRD-matched monsters — this pattern should be extended.

### Fix
Add a simple file-existence check before writing **any** entity file. If the file already exists, skip writing it (or optionally merge — skip for now, existence-check is sufficient).

The `if not filepath.exists(): write` pattern already used for SRD monsters should be the default for **all** entity writers, not just monsters.

---

## Part 4: `_Home.md` — Idempotent Index

### Problem
`_Home.md` is overwritten on each call to `generate_obsidian`, accumulating duplicate chapter rows in the stats table (one row per chunk, not one per chapter).

### Fix
Change the static stats table in `_Home.md` to a **Dataview query** instead of a manually built table. This makes it fully dynamic and immune to chunk-order issues:

```markdown
## Chapters

```dataview
TABLE length(rows) AS "Total Files"
FROM ""
GROUP BY chapter
SORT chapter ASC
```
```

For the summary stats section, consider replacing the static table with:

```markdown
## Content Summary

```dataview
TABLE
  length(filter(rows, (r) => contains(r.tags, "Encounter"))) AS "Encounters",
  length(filter(rows, (r) => contains(r.tags, "NPC"))) AS "NPCs",
  length(filter(rows, (r) => contains(r.tags, "Location"))) AS "Locations",
  length(filter(rows, (r) => contains(r.tags, "Event"))) AS "Events",
  length(filter(rows, (r) => contains(r.tags, "Item"))) AS "Items",
  length(filter(rows, (r) => contains(r.tags, "Monster"))) AS "Monsters"
FROM ""
GROUP BY chapter
SORT chapter ASC
```
```

Also add Dataview sections for the new entity types:

```markdown
## Races
```dataview
TABLE size AS "Size", speed AS "Speed", asi AS "ASI"
FROM #Race
SORT file.name ASC
```

## Deities
```dataview
TABLE alignment AS "Alignment", domains AS "Domains", symbol AS "Symbol"
FROM #Deity
SORT file.name ASC
```

## Spells
```dataview
TABLE level AS "Level", school AS "School", classes AS "Classes"
FROM #Spell
SORT level ASC, file.name ASC
```

## Factions
```dataview
TABLE type AS "Type", base_of_operations AS "Base"
FROM #Faction
SORT file.name ASC
```
```

---

## Part 5: Document Type Detection in `pdf_tools.py`

### Update `analyze_pdf_structure()` heuristics

Add "Campaign Setting" as a document type:

```python
if any(kw in toc_lower for kw in ["race", "class", "spell", "background", "feat"]) and \
   any(kw in toc_lower for kw in ["religion", "deity", "lore", "world", "setting", "region"]):
    doc_type = "Campaign Setting"
```

The returned string should include the detected type so callers (including the MCP server) can pass the appropriate `mode` to `generate_obsidian`.

---

## Part 6: MCP Server (`server.py`) Updates

### New tool: `parse_campaign_setting`

Expose a **single high-level tool** that orchestrates the full pipeline for a campaign setting document, in addition to the existing granular tools:

```
mcp__tome__parse_campaign_setting(pdf_path, output_dir, provider="gemini", chunk_size=20)
```

This tool:
1. Calls `analyze_pdf_structure()` to get the TOC and page ranges.
2. Splits the PDF into logical chunks using the TOC (by chapter/section, not arbitrary page counts).
3. Calls `extract_entities_llm()` on each chunk with the updated prompt.
4. Merges all resulting entity dicts (de-duped).
5. Calls `generate_obsidian(merged_entities, output_dir, mode="campaign_setting")`.
6. Returns a summary: counts per entity type, list of generated files.

This saves the user from having to orchestrate chunking manually (which was the main pain point in the Humblewood run — 36 chunks, manual page range math, multiple `generate_obsidian` calls producing duplicate `_Home.md` rows).

### Update `generate_obsidian_markdown` tool signature

Add `mode` parameter:
```
mcp__tome__generate_obsidian_markdown(entities, output_dir, mode="auto")
```

---

## Part 7: Flexibility Notes for Opus

These are judgment calls — implement them if the scope feels right, skip if not:

### 7a. Deity "stat blocks" (optional but recommended)
Some settings give deities combat stats for divine encounters. If a deity entity has a `statblock` field with content, emit a `> [!danger]- Divine Stat Block` callout in the deity file, similar to how NPC stat blocks are handled now. Don't create a separate Monster file for deities — keep it in the Deity file.

### 7b. Race → Class cross-links (optional)
If a race file mentions class options (e.g. "Corvum Necromancer"), add a `## Typical Classes` section linking to those class files. The LLM prompt can be asked to populate a `typical_classes` array on the race entity.

### 7c. Faction → NPC cross-links (optional)
Faction files should link to NPCs who are members. The LLM already extracts `members: [...]` on factions — use those names to generate `[[NPC Name]]` wikilinks in the Faction file.

### 7d. Lore entries as a "canvas" alternative (skip for now)
Obsidian Canvas files could theoretically map lore relationships visually. This is out of scope for this implementation but noted for future consideration.

### 7e. `enrich_with_references()` for spells (optional)
The current enrichment only queries SRD for NPCs, encounters, and items. Spells could also be enriched — if a spell name matches an SRD spell, append the SRD description. Lower priority since Humblewood spells are all custom.

---

## Summary of Changes

| File | Change |
|---|---|
| `obsidian_tools.py` | Add global entity arrays to extraction schema and prompt |
| `obsidian_tools.py` | Add `mode` param to `generate_obsidian()` |
| `obsidian_tools.py` | Add writers for Races, Classes, Spells, Deities, Backgrounds, Feats, Factions, Lore |
| `obsidian_tools.py` | Global folder structure in `"campaign_setting"` mode |
| `obsidian_tools.py` | Deduplication: `if not filepath.exists()` on all writers |
| `obsidian_tools.py` | `_Home.md`: replace static table with Dataview queries |
| `obsidian_tools.py` | `_Home.md`: add sections for Races, Deities, Spells, Factions |
| `pdf_tools.py` | Add "Campaign Setting" to document type heuristics |
| `server.py` | Add `mode` param to `generate_obsidian_markdown` tool |
| `server.py` | Add new `parse_campaign_setting` orchestration tool |
