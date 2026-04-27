import logging
from pathlib import Path

def _load_reference_material(reference_dir: str) -> str:
    ref_path = Path(reference_dir)
    if not ref_path.exists():
        return "No reference material found."
    
    docs = []
    for filepath in ref_path.glob("*.md"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                docs.append(f"--- {filepath.name} ---\n{f.read()}\n")
        except Exception as e:
            logging.error(f"Error reading {filepath.name}: {e}")
    return "\n".join(docs)

def convert_5e_bestiary_to_nimble(input_dir: str, output_dir: str) -> dict:
    """
    Returns context for the calling LLM to bulk-convert a directory of 5e statblocks to Nimble 2e.
    Reads all .md files from input_dir and loads Nimble 2e reference material.
    No LLM call is made — the calling LLM performs the conversion and writes output files.
    """
    in_path = Path(input_dir)

    if not in_path.exists():
        return {"error": f"Input directory {input_dir} not found"}

    statblocks = []
    for filepath in sorted(in_path.glob("*.md")):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                statblocks.append({"filename": filepath.name, "content": f.read()})
        except Exception as e:
            logging.error(f"Error reading {filepath.name}: {e}")

    nimble_ref_dir = Path(__file__).parent / "references" / "nimble"
    nimble_reference = _load_reference_material(str(nimble_ref_dir))

    output_format = """One Obsidian markdown file per monster, named <monster-name-kebab-case>.md, with this structure:

---
tags: [Monster, Nimble, <role>]
source_system: "D&D 5e (converted to Nimble 2e)"
cr_original: <original CR>
---

# <Monster Name>

> [!info]- Nimble Stat Block
> **Level:** <level> | **Role:** <role> | **HP:** <hp> | **Armor:** <armor> | **Speed:** <speed>
> **Saves:** <saves>
> **Damage Traits:** <damage_traits>
> **Condition Immunities:** <condition_immunities>
> **Senses:** <senses>
>
> **Traits**
> <Trait Name>. <description>
>
> **Actions**
> <Action Name>. <description>

> [!warning]- Conversion Notes
> - <note line>

Conversion rules:
- level: max(1, CR)
- armor: Unarmored (AC <=13), Medium Armor (AC 14-17), Heavy Armor (AC 18+)
- role: pick from Melee / Ranged / Controller / Support / AoE / Summoner / Striker / Ambusher / Defender (can combine two)
- saves: relevant saving throw bonuses
- damage_traits: resistances, immunities, vulnerabilities in Nimble format
- actions: converted from 5e attacks — add "hits unless roll of 1, crits on max die"
- traits: passive abilities; legendary resistances become Boss traits
- conversion_notes: flag anything requiring GM review"""

    return {
        "statblocks": statblocks,
        "nimble_reference": nimble_reference,
        "output_dir": output_dir,
        "output_format": output_format,
        "instructions": "Convert each statblock to Nimble 2e using the reference material. Write one Obsidian markdown file per monster to output_dir, named <monster-name-kebab-case>.md.",
    }
