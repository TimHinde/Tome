# Req Spec: Nimble 2e Batch Conversion Pipeline for tome MCP

## Problem Statement

The tome MCP currently has two separate concerns that don't connect:

1. A general entity extraction + enrichment + markdown pipeline (`extract_entities_with_llm` → `enrich_entities` → `generate_obsidian_markdown`) — designed for processing adventure text, not system conversion.
2. A single-statblock conversion utility (`convert_5e_monster_to_nimble`) — produces shallow output (stat relabelling only), has no batch capability, and sits outside the pipeline.

Neither path produces a complete, rules-accurate Nimble 2e statblock at scale. The reference library contains only 5e SRD material. There is no Nimble 2e reference material loaded.

---

## Goals

- Convert an entire 5e bestiary directory to Nimble 2e format in a single tool call or minimal calls.
- Output quality must reflect actual Nimble 2e mechanics (not just relabelled 5e stats).
- Token cost must scale sublinearly with creature count (batch processing, not 1 call per creature).
- Output must be Obsidian-ready markdown with correct frontmatter tags.

---

## Out of Scope

- Converting spells, magic items, or PC class features.
- Converting non-5e systems.
- PDF ingestion (covered by existing `extract_pdf_text`).

---

## Required Changes

### 1. Nimble 2e Reference Material

**What:** A reference directory for Nimble 2e rules, parallel to the existing 5e SRD reference library.

**Minimum required files:**
- `nimble_core_mechanics.md` — action economy, attack resolution (hits unless rolling 1, crit on max die), saves, conditions
- `nimble_monster_roles.md` — role definitions and what they mean mechanically (Artillery, Bruiser, Skirmisher, Controller, Support, Solo, etc.)
- `nimble_monster_creation.md` — how HP, armor, damage, and level are derived; role-based stat targets by level
- `nimble_conditions.md` — full condition list and mechanical effects
- `nimble_damage_types.md` — any system-specific damage handling

**Format:** Same markdown format as existing reference files so `query_references` and `enrich_entities` can consume them without modification.

**Acceptance criteria:**
- `list_references(reference_dir="nimble")` returns the above files.
- `query_references("what does Artillery role mean", reference_dir="nimble")` returns a useful answer.

---

### 2. New Tool: `convert_5e_bestiary_to_nimble`

**Purpose:** Single entry point that wraps the full pipeline for bulk bestiary conversion.

**Signature:**
```python
convert_5e_bestiary_to_nimble(
    input_dir: str,              # path to directory of 5e .md statblock files
    output_dir: str,             # where to write converted Nimble .md files
    tag: str = "Monster",        # frontmatter tag applied to all outputs
    provider: str = "claude",    # LLM provider for extraction step
    batch_size: int = 20,        # creatures per extraction batch
) -> dict                        # summary: {converted: int, failed: [], output_dir: str}
```

**Internal pipeline:**

```
read input_dir files
  → chunk into batches of `batch_size`
  → for each batch:
      extract_entities_with_llm(concatenated statblock text)
      → convert_entities_to_nimble(entities, reference_dir="nimble")   ← NEW
      → accumulate into master entities dict
  → generate_obsidian_markdown(all_entities, output_dir)
```

**Returns:** A summary dict, not individual file contents. Errors per creature should be non-fatal (log to `failed` list, continue).

---

### 3. New Tool: `convert_entities_to_nimble`

This is the core missing piece — a transform step that sits between extraction and markdown generation.

**Purpose:** Takes a structured entities dict (output of `extract_entities_with_llm`) and converts each monster entity from 5e mechanics to Nimble 2e mechanics, using the Nimble reference material for accuracy.

**Signature:**
```python
convert_entities_to_nimble(
    entities: dict,              # structured entity dict from extract_entities_with_llm
    reference_dir: str = "nimble",
) -> dict                        # same shape as input, with Nimble 2e fields populated
```

**Conversion rules to apply per monster (derived from Nimble reference material):**

| 5e Field | Nimble Output | Notes |
|---|---|---|
| CR + role tag | `level` | CR → level mapping table in reference |
| AC | `armor` | Map AC range to Nimble armor category |
| Hit Points | `hp` | Carry over directly |
| Speed | `speed` | Carry over directly |
| STR/DEX/CON/INT/WIS/CHA | dropped | Not used in Nimble 2e |
| Saving throw proficiencies | `saves` | Convert to Nimble save format |
| Damage resistances/immunities/vulnerabilities | `damage_traits` | Carry over, flag for GM review |
| Condition immunities | `condition_immunities` | Map to Nimble conditions |
| Actions | `actions` | Rewrite attack bonus → Nimble resolution note; adjust damage dice per level/role targets |
| Bonus Actions | `bonus_actions` | Carry over with Nimble action economy note |
| Reactions | `reactions` | Carry over |
| Legendary Actions | `legendary_actions` | Convert to Nimble Solo/Boss action economy if applicable |
| Traits/features | `traits` | Carry over, flag any that reference 5e-specific mechanics |
| Senses | `senses` | Carry over |
| CR | `cr_original` | Preserve for reference |
| Role (Artillery, etc.) | `role` | Carry over |

**Each converted entity must include a `conversion_notes` field** listing any mechanics that couldn't be automatically converted and need GM review (e.g. legendary resistances, lair actions, complex condition interactions).

**Acceptance criteria:**
- Output dict has same structure as input (compatible with `generate_obsidian_markdown`).
- No 5e-specific stat blocks (ability scores, proficiency bonus) in output.
- Nimble action resolution note present on all attack actions.
- `conversion_notes` populated where ambiguity exists.

---

### 4. Enhance `generate_obsidian_markdown` for Nimble Output

**Current behaviour:** Writes entities to markdown. Format is generic.

**Required change:** When entities contain a `system: "Nimble 2e"` field, output a Nimble-formatted statblock callout rather than a generic one.

**Target output format per file:**
```markdown
---
tags: [Monster, Nimble, <role>, <creature_type>]
source_system: "D&D 5e (converted to Nimble 2e)"
cr_original: <value>
---

# <Name>

> [!info]- Nimble Stat Block
> **Level:** X | **Role:** Artillery | **HP:** 13 | **Armor:** Medium | **Speed:** 30 ft.
> **Saves:** —
> **Damage Traits:** Vulnerable: bludgeoning, force, thunder | Resistant: piercing, slashing
> **Condition Immunities:** exhaustion, poisoned
> **Senses:** darkvision 60 ft.
>
> **Traits**
> Bone Weapons. ...
> Hail of Bones. ...
>
> **Actions**
> Bone Bow. Ranged attack (hits unless roll of 1, crits on max die). Range 80/320 ft., one target. Hit: 4 (1d4+2) piercing. ...
> Bone Knife. Melee attack (hits unless roll of 1, crits on max die). Reach 5 ft., one target. Hit: 4 (1d4+2) slashing. ...

> [!warning]- Conversion Notes
> - No mechanics flagged for review.
```

---

### 5. Enhance `convert_5e_monster_to_nimble` (existing tool)

The existing single-statblock tool should be updated to use the same conversion logic as `convert_entities_to_nimble` internally, so both paths produce consistent output. Currently it only relabels stats.

---

## Token Efficiency Notes

- `batch_size=20` means ~10 LLM calls for a 200-creature bestiary vs. 200 calls today.
- `generate_obsidian_markdown` already writes all files in one call — preserve this.
- The LLM call in `extract_entities_with_llm` is the primary cost driver; batch size should be tunable.
- The `enrich_entities` step is optional for conversion (it's more useful for adventure prep) — don't force it into the conversion pipeline.

---

## Acceptance Criteria (end-to-end)

Given a directory of 136 5e `.md` statblock files:

1. `convert_5e_bestiary_to_nimble(input_dir, output_dir)` completes without error.
2. Output directory contains 136 `.md` files.
3. No file contains raw ability scores (STR/DEX/CON/INT/WIS/CHA).
4. Every attack action contains a Nimble resolution note.
5. Every file has correct frontmatter tags including `Nimble`.
6. Any creature with legendary actions, lair actions, or complex conditional mechanics has a populated `conversion_notes` callout.
7. Token cost for 136 creatures is no more than 10× the cost of a single conversion.
