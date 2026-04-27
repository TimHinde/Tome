import os
import re
import json
from pathlib import Path
from reference_tools import query_reference

EXTRACTION_SYSTEM_PROMPT = """
You are an AI assistant helping a Game Master.
Review the provided TTRPG text and extract ALL key entities. The text may be from an adventure module, a campaign setting, a supplement, or a combination.

Return a JSON object with TWO kinds of content:

1. CHAPTER-SCOPED content (adventure/narrative) — goes inside a "chapters" array.
2. GLOBAL REFERENCE content (player options, bestiary, world lore) — goes in TOP-LEVEL arrays, NOT inside any chapter.

=== CHAPTER-SCOPED ENTITIES (inside "chapters") ===

Use these STRICT definitions — every scene goes in exactly ONE category:
- ENCOUNTER: Any scene where the party faces an active challenge requiring dice rolls — combat, skill challenge, chase, puzzle, trap, or social conflict with mechanics.
- EVENT: A pure narrative beat with no active dice-roll challenge — story transitions, chapter setup/intro, lore reveals, consequence text, or GM housekeeping notes.
- LOCATION: A physical place the party can explore, distinct from the encounter that happens there. Only create a location if it has descriptive value beyond being "the room where encounter X happens."
- Do NOT put the same scene in both encounters and events. If something has mechanics, it is an encounter only.

Each chapter: name, overview, reading_order (flat ordered list with {name, type: event|location|encounter, note}), npcs, locations, encounters, events, items, monsters.

NPC schema: {name, motivation, secret, statblock, location}
Location schema: {name, description, encounters: [str], loot: [str], exits: [str]}
Encounter schema: {name, read_aloud, description, mechanics, monsters: [str], npcs_present: [str]}
Event schema: {name, read_aloud, description, mechanics, next_steps, npcs_present: [str]}
Item schema: {name, rarity, description, mechanics}
Monster (chapter) schema: {name, statblock}

=== GLOBAL REFERENCE ENTITIES (top-level arrays, NOT inside chapters) ===

races: {name, description, subraces: [str], asi: {STR,DEX,...}, speed, size, traits: [{name,description}], languages: [str], source_chapter}
classes: {name, base_class, type: class|subclass, description, features: [{name,level,description}], source_chapter}
spells: {name, level, school, casting_time, range, components, duration, classes: [str], description, higher_levels, source_chapter}
deities: {name, title, alignment, domains: [str], symbol, worshippers, description, myths, appearance, personality, source_chapter}
backgrounds: {name, description, skill_proficiencies: [str], tool_proficiencies: [str], languages, equipment: [str], feature: {name,description}, source_chapter}
feats: {name, prerequisite, description, benefits: [str], source_chapter}
factions: {name, type, description, goals, members: [str], base_of_operations, allies: [str], enemies: [str], source_chapter}
lore_entries: {name, category: Cosmology|History|Culture|Geography, description, related_entities: [str], source_chapter}
monsters (top-level bestiary): {name, statblock}

=== RULES ===
- Deities are NEVER NPCs. If worshipped / has domains+symbol → deities array.
- Bestiary creatures with full stat blocks → top-level monsters, NOT inside chapters.
- No chapter structure in text → empty "chapters" array.
- No reference content → omit global arrays.
- Narrative content without chapters → single chapter named "Arc: Uncategorized".
- Return ONLY valid JSON. No markdown fences or extra text.

Output structure:
{"chapters": [...], "races": [...], "classes": [...], "spells": [...], "deities": [...], "backgrounds": [...], "feats": [...], "factions": [...], "lore_entries": [...], "monsters": [...]}
Omit any top-level array that has no entries. Always include "chapters" even if empty.
"""

# All entity type keys that can appear at the top level (global) or inside chapters
GLOBAL_ENTITY_KEYS = ["races", "classes", "spells", "deities", "backgrounds", "feats", "factions", "lore_entries"]
CHAPTER_ENTITY_KEYS = ["npcs", "locations", "encounters", "events", "items", "monsters"]


def merge_entities(entity_dicts: list) -> dict:
    """
    Merge multiple entity extraction results into a single dict.
    Deduplication: first-write-wins by entity name within each type.
    Chapters are merged by name; global arrays are combined and deduped.
    """
    merged = {"chapters": []}
    
    # Initialize global arrays
    for key in GLOBAL_ENTITY_KEYS:
        merged[key] = []
    # Top-level monsters (bestiary)
    merged["monsters"] = []

    seen_names = {}  # key -> set of names already added
    for key in GLOBAL_ENTITY_KEYS + ["monsters"]:
        seen_names[key] = set()

    chapter_map = {}  # chapter name -> merged chapter dict

    for entity_dict in entity_dicts:
        if not isinstance(entity_dict, dict):
            continue

        # Merge chapters
        for chapter in entity_dict.get("chapters", []):
            if not isinstance(chapter, dict):
                continue
            chap_name = chapter.get("name", "Arc: Uncategorized")
            if chap_name not in chapter_map:
                chapter_map[chap_name] = {
                    "name": chap_name,
                    "overview": chapter.get("overview", chapter.get("description", "")),
                    "reading_order": chapter.get("reading_order", []),
                }
                for key in CHAPTER_ENTITY_KEYS:
                    chapter_map[chap_name][key] = []

            target = chapter_map[chap_name]
            # Merge chapter-scoped entities by name
            for key in CHAPTER_ENTITY_KEYS:
                existing_names = {e.get("name", "").lower() for e in target[key] if isinstance(e, dict)}
                for entity in chapter.get(key, []):
                    if isinstance(entity, dict):
                        ename = entity.get("name", "").lower()
                        if ename and ename not in existing_names:
                            target[key].append(entity)
                            existing_names.add(ename)

        # Merge global entity arrays
        for key in GLOBAL_ENTITY_KEYS + ["monsters"]:
            for entity in entity_dict.get(key, []):
                if isinstance(entity, dict):
                    ename = entity.get("name", "").lower()
                    if ename and ename not in seen_names[key]:
                        merged[key].append(entity)
                        seen_names[key].add(ename)

    merged["chapters"] = list(chapter_map.values())
    
    # Remove empty global arrays to keep output clean
    for key in GLOBAL_ENTITY_KEYS + ["monsters"]:
        if not merged[key]:
            del merged[key]

    return merged



def extract_entities_llm(text: str, provider: str = "gemini") -> dict:
    """
    Uses an LLM to extract entities from the raw adventure text.
    System prompt is separated from user content to enable prompt caching.
    Returns a dictionary of structured data.
    """
    content = ""
    if provider.lower() == "gemini":
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            return {"error": "google-genai SDK not installed"}
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {"error": "GEMINI_API_KEY environment variable not set"}

        client = genai.Client(api_key=api_key)
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                config=genai_types.GenerateContentConfig(
                    system_instruction=EXTRACTION_SYSTEM_PROMPT,
                ),
                contents=text,
            )
            content = response.text
        except Exception as e:
            return {"error": f"Failed to call Gemini API: {e}"}

    elif provider.lower() == "claude":
        try:
            import anthropic
        except ImportError:
            return {"error": "anthropic SDK not installed"}
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return {"error": "ANTHROPIC_API_KEY environment variable not set"}

        client = anthropic.Anthropic(api_key=api_key)
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                system=[{
                    "type": "text",
                    "text": EXTRACTION_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": text}],
            )
            content = message.content[0].text
        except Exception as e:
            return {"error": f"Failed to call Claude API: {e}"}

    elif provider.lower() == "openai":
        try:
            import openai
        except ImportError:
            return {"error": "openai SDK not installed. Please install it with: pip install openai"}

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {"error": "OPENAI_API_KEY environment variable not set"}

        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
            content = response.choices[0].message.content
        except Exception as e:
            return {"error": f"Failed to call OpenAI API: {e}"}

    else:
        return {"error": f"Unsupported provider: {provider}"}

    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse JSON: {e}", "raw": content}

def convert_5e_to_nimble(statblock: str) -> dict:
    """
    Returns context for the calling LLM to convert a D&D 5e monster statblock to Nimble RPG 2e.
    Loads Nimble 2e reference material and describes the required output format.
    No LLM call is made — the calling LLM performs the conversion.
    """
    nimble_ref_dir = Path(__file__).parent / "references" / "nimble"
    docs = []
    for filepath in sorted(nimble_ref_dir.glob("*.md")):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                docs.append(f"--- {filepath.name} ---\n{f.read()}\n")
        except Exception:
            pass
    nimble_reference = "\n".join(docs)

    output_format = """Obsidian markdown with this exact structure:

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
        "statblock": statblock,
        "nimble_reference": nimble_reference,
        "output_format": output_format,
        "instructions": "Convert the statblock to Nimble 2e using the reference material. Output Obsidian markdown matching the output_format.",
    }

def extract_entities_heuristic(text: str) -> dict:
    """
    Fallback tool that uses heuristics (regex) to extract basic entities.
    Very rudimentary. Best used when an LLM isn't available.
    """
    entities = {
        "chapters": [{
            "name": "Arc: Uncategorized",
            "overview": "Auto-extracted content",
            "npcs": [],
            "locations": [],
            "encounters": [],
            "events": [],
            "items": [],
            "monsters": []
        }],
        "races": [],
        "classes": [],
        "spells": [],
        "deities": [],
        "backgrounds": [],
        "feats": [],
        "factions": [],
        "lore_entries": []
    }
    chapter = entities["chapters"][0]
    
    lines = text.splitlines()
    for line in lines:
        lower_line = line.lower()
        if "npc:" in lower_line or "**npc:**" in lower_line:
            chapter["npcs"].append({"name": line.replace("NPC:", "").replace("**NPC:**", "").strip(), "motivation": "", "secret": "", "statblock": "", "location": ""})
        elif "location:" in lower_line or "scene:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            chapter["locations"].append({"name": name, "description": "", "encounters": [], "loot": [], "exits": []})
        elif "encounter:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            chapter["encounters"].append({"name": name, "description": "", "mechanics": "", "monsters": []})
        elif "event:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            chapter["events"].append({"name": name, "description": "", "mechanics": "", "next_steps": ""})
        elif "item:" in lower_line or "loot:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            chapter["items"].append({"name": name, "rarity": "", "description": "", "mechanics": ""})
        # Global entity types
        elif "race:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            entities["races"].append({"name": name, "description": "", "subraces": [], "asi": {}, "speed": 30, "size": "Medium", "traits": [], "languages": [], "source_chapter": ""})
        elif "spell:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            entities["spells"].append({"name": name, "level": 0, "school": "", "casting_time": "", "range": "", "components": "", "duration": "", "classes": [], "description": "", "source_chapter": ""})
        elif "deity:" in lower_line or "god:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            entities["deities"].append({"name": name, "title": "", "alignment": "", "domains": [], "symbol": "", "worshippers": "", "description": "", "source_chapter": ""})
        elif "class:" in lower_line or "subclass:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            entities["classes"].append({"name": name, "base_class": "", "type": "class", "description": "", "features": [], "source_chapter": ""})
        elif "background:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            entities["backgrounds"].append({"name": name, "description": "", "skill_proficiencies": [], "tool_proficiencies": [], "source_chapter": ""})
        elif "feat:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            entities["feats"].append({"name": name, "prerequisite": "", "description": "", "benefits": [], "source_chapter": ""})
        elif "faction:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            entities["factions"].append({"name": name, "type": "", "description": "", "goals": "", "members": [], "source_chapter": ""})
        elif "lore:" in lower_line:
            name_part = line.split(":", 1)
            name = name_part[1].strip() if len(name_part) > 1 else line.strip()
            entities["lore_entries"].append({"name": name, "category": "", "description": "", "related_entities": [], "source_chapter": ""})
            
    return entities

def enrich_with_references(entities: dict, reference_dirs: list[str]) -> dict:
    """
    Iterates through extracted entities (nested in chapters) and calls query_srd_logic to find SRD references.
    """
    enriched = entities.copy()
    
    if "chapters" not in enriched:
        return enriched

    for chapter in enriched["chapters"]:
        # Enrich NPCs by looking up their statblock
        if "npcs" in chapter:
            for npc in chapter["npcs"]:
                if isinstance(npc, dict) and "statblock" in npc and npc["statblock"]:
                    statblock_name = npc["statblock"]
                    if statblock_name.lower() != "none" and statblock_name.strip():
                        srd_result = query_reference(statblock_name)
                        if "No results found" not in srd_result and "Error:" not in srd_result:
                            npc["srd_reference"] = srd_result

        # Enrich Encounters by looking up required monsters
        if "encounters" in chapter:
            for enc in chapter["encounters"]:
                if isinstance(enc, dict) and "monsters" in enc:
                    enc["srd_references"] = []
                    for monster in enc["monsters"]:
                        if isinstance(monster, dict) and 'name' in monster:
                            m_name = monster['name']
                        else:
                            m_name = str(monster)
                        if m_name.strip():
                            srd_result = query_reference(m_name)
                            if "No results found" not in srd_result and "Error:" not in srd_result:
                                enc["srd_references"].append({"name": m_name, "data": srd_result})

        # Enrich Items
        if "items" in chapter:
            for item in chapter["items"]:
                if isinstance(item, dict) and "name" in item:
                    item_name = item["name"]
                    if item_name.strip():
                        srd_result = query_reference(item_name)
                        if "No results found" not in srd_result and "Error:" not in srd_result:
                            item["srd_reference"] = srd_result
                        
    return enriched

def _yaml_escape(value: str) -> str:
    """Escape a string value for safe YAML output."""
    if not value:
        return '""'
    # Wrap in quotes if it contains YAML-special characters
    if any(c in value for c in ':[]{}#&*!|>\'"%@`'):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _render_nimble_monster(monster: dict, chap_name: str = "") -> str:
    name = monster.get("name", "Unknown Monster")
    tag = monster.get("tag_override", "Monster")
    role = monster.get("role", "Unknown Role")

    content = f"---\n"
    content += f"tags: [{tag}, Nimble, {role}]\n"
    content += f"source_system: \"D&D 5e (converted to Nimble 2e)\"\n"
    content += f"cr_original: {_yaml_escape(str(monster.get('cr_original', '')))}\n"
    if chap_name:
        content += f"chapter: {_yaml_escape(chap_name)}\n"
    content += f"---\n\n"
    content += f"# {name}\n\n"

    content += f"> [!info]- Nimble Stat Block\n"
    content += f"> **Level:** {monster.get('level', '?')} | **Role:** {role} | **HP:** {monster.get('hp', '?')} | **Armor:** {monster.get('armor', '?')} | **Speed:** {monster.get('speed', '?')}\n"

    saves = monster.get("saves", "—")
    if isinstance(saves, list): saves = ", ".join(saves)
    content += f"> **Saves:** {saves}\n"

    damage_traits = monster.get("damage_traits", "—")
    if damage_traits:
        content += f"> **Damage Traits:** {damage_traits}\n"

    cond_imm = monster.get("condition_immunities", "—")
    if cond_imm:
        content += f"> **Condition Immunities:** {cond_imm}\n"

    senses = monster.get("senses", "—")
    if senses:
        content += f"> **Senses:** {senses}\n"

    content += ">\n"

    traits = monster.get("traits", [])
    if traits:
        content += "> **Traits**\n"
        if isinstance(traits, list):
            for t in traits:
                if isinstance(t, dict):
                    content += f"> {t.get('name', '')}. {t.get('description', '')}\n"
                else:
                    content += f"> {t}\n"
        else:
            content += f"> {traits}\n"
        content += ">\n"

    actions = monster.get("actions", [])
    if actions:
        content += "> **Actions**\n"
        if isinstance(actions, list):
            for a in actions:
                if isinstance(a, dict):
                    content += f"> {a.get('name', '')}. {a.get('description', '')}\n"
                else:
                    content += f"> {a}\n"
        else:
            content += f"> {actions}\n"

    notes = monster.get("conversion_notes", "No mechanics flagged for review.")
    content += f"\n> [!warning]- Conversion Notes\n"
    for line in notes.splitlines():
        content += f"> - {line}\n"

    return content

def generate_obsidian(entities: dict, output_dir: str, mode: str = "auto") -> list[str]:
    """
    Generates Obsidian Markdown files from nested chapter entities.
    Includes enriched YAML frontmatter for Dataview and a _Home.md index.
    
    Modes:
    - "adventure": Chapter-scoped subfolders only (original behavior)
    - "campaign_setting": Global folders for reference content + chapter folders for adventure content
    - "auto" (default): Detects from entity data — campaign_setting if global arrays present, else adventure
    
    Returns a list of generated file paths.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    generated_files = []
    
    if "chapters" not in entities:
        entities["chapters"] = []

    # Resolve auto mode
    GLOBAL_ENTITY_TYPES = ["races", "classes", "spells", "deities", "backgrounds", "feats", "factions", "lore_entries"]
    if mode == "auto":
        has_global = any(len(entities.get(t, [])) > 0 for t in GLOBAL_ENTITY_TYPES)
        # Also check for top-level monsters (bestiary)
        has_toplevel_monsters = len(entities.get("monsters", [])) > 0 and len(entities.get("chapters", [])) == 0
        mode = "campaign_setting" if (has_global or has_toplevel_monsters) else "adventure"

    def sanitize_filename(name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_\- ]', '', name).strip()

    # Track chapter stats for _Home.md
    chapter_stats = []

    for chapter in entities["chapters"]:
        chap_name = chapter.get("name", "Unknown Chapter")
        chap_filename = f"{sanitize_filename(chap_name)}.md"
        chap_dir = out_path / chap_filename.replace(".md", "")
        chap_dir.mkdir(parents=True, exist_ok=True)
        chap_filepath = chap_dir / chap_filename
        
        chap_content = f"---\ntags: [Chapter]\n---\n\n# {chap_name}\n\n## Story Overview\n{chapter.get('overview', chapter.get('description', ''))}\n\n"

        child_links = {"Locations": [], "Encounters": [], "Events": [], "NPCs": [], "Items": [], "Monsters": []}
        reading_order = chapter.get("reading_order", [])

        # Build a set of encounter names (sanitized) to deduplicate against events
        encounter_names = {
            sanitize_filename(e.get("name", "")).lower()
            for e in chapter.get("encounters", [])
            if isinstance(e, dict) and e.get("name", "").strip()
        }

        # Generate NPCs
        if "npcs" in chapter and isinstance(chapter["npcs"], list):
            for npc in chapter["npcs"]:
                if not isinstance(npc, dict) or "name" not in npc or not npc["name"].strip(): continue
                name = npc["name"]
                filename = f"{sanitize_filename(name)}.md"
                cat_dir = chap_dir / "NPCs"
                cat_dir.mkdir(exist_ok=True)
                filepath = cat_dir / filename
                child_links["NPCs"].append(f"[[{name}]]")
                
                if not filepath.exists():
                    content = f"---\ntags: [NPC]\n"
                    content += f"chapter: {_yaml_escape(chap_name)}\n"
                    content += f"location: {_yaml_escape(npc.get('location', ''))}\n"
                    content += f"statblock: {_yaml_escape(npc.get('statblock', ''))}\n"
                    content += f"motivation: {_yaml_escape(npc.get('motivation', ''))}\n"
                    content += f"---\n\n"
                    content += f"# {name}\n\n"
                    content += f"**Motivation:** {npc.get('motivation', '')}\n\n"
                    content += f"**Secret:** {npc.get('secret', '')}\n\n"
                    
                    if "srd_reference" in npc:
                        content += "## Reference Statblock\n"
                        content += f"> [!info]- Statblock\n"
                        for line in npc['srd_reference'].splitlines():
                            content += f"> {line}\n"
                            
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    generated_files.append(str(filepath))

        # Generate Locations
        if "locations" in chapter and isinstance(chapter["locations"], list):
            for loc in chapter["locations"]:
                if not isinstance(loc, dict) or "name" not in loc or not loc["name"].strip(): continue
                name = loc["name"]
                filename = f"{sanitize_filename(name)}.md"
                cat_dir = chap_dir / "Locations"
                cat_dir.mkdir(exist_ok=True)
                filepath = cat_dir / filename
                child_links["Locations"].append(f"[[{name}]]")
                
                if not filepath.exists():
                    content = f"---\ntags: [Location]\n"
                    content += f"chapter: {_yaml_escape(chap_name)}\n"
                    content += f"---\n\n"
                    content += f"# {name}\n\n"
                    content += f"> {loc.get('description', '')}\n\n"
                    
                    encounters = loc.get("encounters", [])
                    if encounters:
                        content += "## Encounters\n"
                        for enc in encounters:
                            link_name = enc['name'] if isinstance(enc, dict) and 'name' in enc else str(enc)
                            content += f"- [[{link_name}]]\n"
                    
                    loot = loc.get("loot", [])
                    if loot:
                        content += "## Loot\n"
                        for l in loot:
                            link_name = l['name'] if isinstance(l, dict) and 'name' in l else str(l)
                            content += f"- [[{link_name}]]\n"
                            
                    exits = loc.get("exits", [])
                    if exits:
                        content += "## Exits\n"
                        for ex in exits:
                            link_name = ex['name'] if isinstance(ex, dict) and 'name' in ex else str(ex)
                            content += f"- [[{link_name}]]\n"
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    generated_files.append(str(filepath))

        # Generate Encounters
        if "encounters" in chapter and isinstance(chapter["encounters"], list):
            for enc in chapter["encounters"]:
                if not isinstance(enc, dict) or "name" not in enc or not enc["name"].strip(): continue
                name = enc["name"]
                filename = f"{sanitize_filename(name)}.md"
                cat_dir = chap_dir / "Encounters"
                cat_dir.mkdir(exist_ok=True)
                filepath = cat_dir / filename
                child_links["Encounters"].append(f"[[{name}]]")

                # Collect monster names for frontmatter
                monster_names = []
                for m in enc.get("monsters", []):
                    m_name = m['name'] if isinstance(m, dict) and 'name' in m else str(m)
                    if m_name.strip():
                        monster_names.append(m_name)

                # Collect NPC names for frontmatter
                npc_names = enc.get("npcs_present", [])

                content = f"---\ntags: [Encounter]\n"
                content += f"chapter: {_yaml_escape(chap_name)}\n"
                if monster_names:
                    content += f"monsters:\n"
                    for mn in monster_names:
                        content += f"  - {_yaml_escape(mn)}\n"
                if npc_names:
                    content += f"npcs_present:\n"
                    for nn in npc_names:
                        content += f"  - {_yaml_escape(nn)}\n"
                content += f"---\n\n"
                content += f"# {name}\n\n"

                read_aloud = enc.get("read_aloud", "").strip()
                if read_aloud:
                    content += f"> [!quote] Read Aloud\n"
                    for line in read_aloud.splitlines():
                        content += f"> {line}\n"
                    content += "\n"

                description = enc.get("description", "").strip()
                if description:
                    content += f"{description}\n\n"

                mechanics = enc.get("mechanics", "").strip()
                if mechanics:
                    content += f"## Mechanics\n{mechanics}\n\n"

                # Write SRD-matched creatures as standalone Monster files and collect links
                monster_dir = chap_dir / "Monsters"
                if "srd_references" in enc and enc["srd_references"]:
                    monster_dir.mkdir(exist_ok=True)
                    for ref in enc["srd_references"]:
                        m_name = ref["name"]
                        m_filename = f"{sanitize_filename(m_name)}.md"
                        m_filepath = monster_dir / m_filename
                        if not m_filepath.exists():
                            m_content = f"---\ntags: [Monster, SRD]\n"
                            m_content += f"chapter: {_yaml_escape(chap_name)}\n"
                            m_content += f"---\n\n# {m_name}\n\n"
                            m_content += ref["data"]
                            with open(m_filepath, "w", encoding="utf-8") as f:
                                f.write(m_content)
                            generated_files.append(str(m_filepath))
                        if f"[[{m_name}]]" not in child_links["Monsters"]:
                            child_links["Monsters"].append(f"[[{m_name}]]")
                        if m_name not in monster_names:
                            monster_names.append(m_name)

                if monster_names:
                    content += "## Creatures\n"
                    for m_name in monster_names:
                        content += f"- [[{m_name}]]\n"
                    content += "\n"

                if npc_names:
                    content += "## NPCs Present\n"
                    for npc_name in npc_names:
                        content += f"- [[{npc_name}]]\n"
                    content += "\n"

                if not filepath.exists():
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    generated_files.append(str(filepath))

        # Generate Events (skip any whose name duplicates an encounter)
        if "events" in chapter and isinstance(chapter["events"], list):
            for evt in chapter["events"]:
                if not isinstance(evt, dict) or "name" not in evt or not evt["name"].strip(): continue
                name = evt["name"]
                if sanitize_filename(name).lower() in encounter_names:
                    continue  # already written as a richer encounter file
                filename = f"{sanitize_filename(name)}.md"
                cat_dir = chap_dir / "Events"
                cat_dir.mkdir(exist_ok=True)
                filepath = cat_dir / filename
                child_links["Events"].append(f"[[{name}]]")

                next_steps = evt.get("next_steps", "").strip()

                content = f"---\ntags: [Event]\n"
                content += f"chapter: {_yaml_escape(chap_name)}\n"
                if next_steps:
                    content += f"next_steps: {_yaml_escape(next_steps)}\n"
                content += f"---\n\n"
                content += f"# {name}\n\n"

                read_aloud = evt.get("read_aloud", "").strip()
                if read_aloud:
                    content += f"> [!quote] Read Aloud\n"
                    for line in read_aloud.splitlines():
                        content += f"> {line}\n"
                    content += "\n"

                description = evt.get("description", "").strip()
                if description:
                    content += f"{description}\n\n"

                mechanics = evt.get("mechanics", "").strip()
                if mechanics:
                    content += f"## Mechanics\n{mechanics}\n\n"

                if next_steps:
                    content += f"## Next Steps\n{next_steps}\n\n"

                npcs_present = evt.get("npcs_present", [])
                if npcs_present:
                    content += "## NPCs Present\n"
                    for npc_name in npcs_present:
                        content += f"- [[{npc_name}]]\n"
                    content += "\n"

                if not filepath.exists():
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    generated_files.append(str(filepath))

        # Generate Items
        if "items" in chapter and isinstance(chapter["items"], list):
            for item in chapter["items"]:
                if not isinstance(item, dict) or "name" not in item or not item["name"].strip(): continue
                name = item["name"]
                filename = f"{sanitize_filename(name)}.md"
                cat_dir = chap_dir / "Items"
                cat_dir.mkdir(exist_ok=True)
                filepath = cat_dir / filename
                child_links["Items"].append(f"[[{name}]]")
                
                content = f"---\ntags: [Item]\n"
                content += f"chapter: {_yaml_escape(chap_name)}\n"
                content += f"rarity: {_yaml_escape(item.get('rarity', ''))}\n"
                content += f"---\n\n"
                content += f"# {name}\n\n"
                content += f"{item.get('description', '')}\n\n"
                content += f"**Mechanics:** {item.get('mechanics', '')}\n\n"
                
                if "srd_reference" in item:
                    content += "## Reference\n"
                    content += f"> [!info]- Rules text\n"
                    for line in item['srd_reference'].splitlines():
                        content += f"> {line}\n"
                        
                if not filepath.exists():
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    generated_files.append(str(filepath))

        # Generate Monsters
        if "monsters" in chapter and isinstance(chapter["monsters"], list):
            for monster in chapter["monsters"]:
                if not isinstance(monster, dict) or "name" not in monster or not monster["name"].strip(): continue
                name = monster["name"]
                filename = f"{sanitize_filename(name)}.md"
                cat_dir = chap_dir / "Monsters"
                cat_dir.mkdir(exist_ok=True)
                filepath = cat_dir / filename
                child_links["Monsters"].append(f"[[{name}]]")
                
                system = monster.get("system", "")
                if "Nimble 2e" in system:
                    content = _render_nimble_monster(monster, chap_name)
                else:
                    content = f"---\ntags: [Monster, Bestiary]\n"
                    content += f"chapter: {_yaml_escape(chap_name)}\n"
                    content += f"---\n\n"
                    content += f"# {name}\n\n"
                    content += f"{monster.get('statblock', '')}\n\n"
                
                if not filepath.exists():
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    generated_files.append(str(filepath))

        # Complete Chapter File — Session Flow first, then compact index
        flow_entries = [
            e for e in reading_order
            if isinstance(e, dict) and e.get("type", "").lower() in ("location", "encounter", "event")
        ]
        if flow_entries:
            chap_content += "## Session Flow\n"
            for i, entry in enumerate(flow_entries, 1):
                name = entry.get("name", "")
                kind = entry.get("type", "").capitalize()
                note = entry.get("note", "")
                chap_content += f"{i}. [[{name}]] *({kind})* — {note}\n"
            chap_content += "\n"

        # Compact entity index grouped by category (deduplicated)
        chap_content += "## Entity Index\n"
        for category, links in child_links.items():
            seen = []
            for l in links:
                if l not in seen:
                    seen.append(l)
            if seen:
                chap_content += f"**{category}:** {', '.join(seen)}\n"
        chap_content += "\n"

        with open(chap_filepath, "w", encoding="utf-8") as f:
            f.write(chap_content)
        generated_files.append(str(chap_filepath))

        # Track stats for _Home.md
        chapter_stats.append({
            "name": chap_name,
            "encounters": len([l for l in child_links["Encounters"] if l]),
            "npcs": len([l for l in child_links["NPCs"] if l]),
            "locations": len([l for l in child_links["Locations"] if l]),
            "events": len([l for l in child_links["Events"] if l]),
            "items": len([l for l in child_links["Items"] if l]),
            "monsters": len([l for l in child_links["Monsters"] if l]),
        })

    # === GLOBAL ENTITY WRITERS (campaign_setting mode) ===
    if mode == "campaign_setting":
        # Races
        for race in entities.get("races", []):
            if not isinstance(race, dict) or not race.get("name", "").strip(): continue
            name = race["name"]
            cat_dir = out_path / "Races"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                asi = race.get("asi", {})
                asi_str = ", ".join(f"{k} +{v}" for k, v in asi.items() if v) if isinstance(asi, dict) else str(asi)
                content = f"---\ntags: [Race]\nsource_chapter: {_yaml_escape(race.get('source_chapter', ''))}\n"
                content += f"size: {race.get('size', 'Medium')}\nspeed: {race.get('speed', 30)}\n"
                if isinstance(asi, dict) and asi:
                    content += "asi:\n"
                    for stat, val in asi.items():
                        content += f"  {stat}: {val}\n"
                subraces = race.get("subraces", [])
                if subraces:
                    content += "subraces:\n"
                    for sr in subraces:
                        content += f"  - {_yaml_escape(str(sr))}\n"
                content += f"---\n\n# {name}\n\n"
                content += f"> [!info] At a Glance\n> **Size:** {race.get('size', 'Medium')} | **Speed:** {race.get('speed', 30)} ft. | **ASI:** {asi_str}\n\n"
                content += f"{race.get('description', '')}\n\n"
                for trait in race.get("traits", []):
                    if isinstance(trait, dict):
                        content += f"### {trait.get('name', '')}\n{trait.get('description', '')}\n\n"
                if subraces:
                    content += "## Subraces\n"
                    for sr in subraces:
                        content += f"### {sr}\n\n"
                langs = race.get("languages", [])
                if langs:
                    content += f"## Languages\n{', '.join(str(l) for l in langs)}\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

        # Classes / Subclasses
        for cls in entities.get("classes", []):
            if not isinstance(cls, dict) or not cls.get("name", "").strip(): continue
            name = cls["name"]
            cat_dir = out_path / "Classes"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                content = f"---\ntags: [Class]\nsource_chapter: {_yaml_escape(cls.get('source_chapter', ''))}\n"
                content += f"base_class: {_yaml_escape(cls.get('base_class', ''))}\ntype: {cls.get('type', 'class')}\n"
                content += f"---\n\n# {name}\n"
                if cls.get("base_class"):
                    content += f"*{cls.get('type', 'Subclass').capitalize()} of {cls['base_class']}*\n"
                content += f"\n{cls.get('description', '')}\n\n"
                for feat in cls.get("features", []):
                    if isinstance(feat, dict):
                        lvl = feat.get("level", "")
                        lvl_str = f" (Level {lvl})" if lvl else ""
                        content += f"### {feat.get('name', '')}{lvl_str}\n{feat.get('description', '')}\n\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

        # Spells
        for spell in entities.get("spells", []):
            if not isinstance(spell, dict) or not spell.get("name", "").strip(): continue
            name = spell["name"]
            cat_dir = out_path / "Spells"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                lvl = spell.get("level", 0)
                school = spell.get("school", "")
                lvl_label = "Cantrip" if lvl == 0 else f"{lvl}{'st' if lvl == 1 else 'nd' if lvl == 2 else 'rd' if lvl == 3 else 'th'}-level {school}"
                classes = spell.get("classes", [])
                content = f"---\ntags: [Spell]\nsource_chapter: {_yaml_escape(spell.get('source_chapter', ''))}\n"
                content += f"level: {lvl}\nschool: {_yaml_escape(school)}\n"
                content += f"casting_time: {_yaml_escape(spell.get('casting_time', ''))}\n"
                content += f"range: {_yaml_escape(spell.get('range', ''))}\n"
                content += f"components: {_yaml_escape(spell.get('components', ''))}\n"
                content += f"duration: {_yaml_escape(spell.get('duration', ''))}\n"
                if classes:
                    content += "classes:\n"
                    for c in classes:
                        content += f"  - {_yaml_escape(str(c))}\n"
                content += f"---\n\n# {name}\n*{lvl_label}*\n\n"
                content += f"**Casting Time:** {spell.get('casting_time', '')}\n"
                content += f"**Range:** {spell.get('range', '')}\n"
                content += f"**Components:** {spell.get('components', '')}\n"
                content += f"**Duration:** {spell.get('duration', '')}\n"
                if classes:
                    content += f"**Classes:** {', '.join(str(c) for c in classes)}\n"
                content += f"\n{spell.get('description', '')}\n\n"
                higher = spell.get("higher_levels", "")
                if higher:
                    content += f"**At Higher Levels.** {higher}\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

        # Deities
        for deity in entities.get("deities", []):
            if not isinstance(deity, dict) or not deity.get("name", "").strip(): continue
            name = deity["name"]
            title = deity.get("title", "")
            cat_dir = out_path / "Deities"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                domains = deity.get("domains", [])
                content = f"---\ntags: [Deity]\nsource_chapter: {_yaml_escape(deity.get('source_chapter', ''))}\n"
                content += f"alignment: {_yaml_escape(deity.get('alignment', ''))}\n"
                if domains:
                    content += "domains:\n"
                    for d in domains:
                        content += f"  - {_yaml_escape(str(d))}\n"
                content += f"symbol: {_yaml_escape(deity.get('symbol', ''))}\n"
                heading = f"# {name}" + (f" — {title}" if title else "")
                content += f"---\n\n{heading}\n\n"
                content += f"> [!info] Divine Profile\n"
                content += f"> **Alignment:** {deity.get('alignment', '')} | **Domains:** {', '.join(str(d) for d in domains)}\n"
                content += f"> **Symbol:** {deity.get('symbol', '')}\n"
                content += f"> **Worshippers:** {deity.get('worshippers', '')}\n\n"
                content += f"{deity.get('description', '')}\n\n"
                myths = deity.get("myths", "")
                if myths:
                    content += f"## Myths & Stories\n{myths}\n\n"
                appearance = deity.get("appearance", "")
                if appearance:
                    content += f"## Appearance\n{appearance}\n\n"
                personality = deity.get("personality", "")
                if personality:
                    content += f"## Personality\n{personality}\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

        # Backgrounds
        for bg in entities.get("backgrounds", []):
            if not isinstance(bg, dict) or not bg.get("name", "").strip(): continue
            name = bg["name"]
            cat_dir = out_path / "Backgrounds"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                content = f"---\ntags: [Background]\nsource_chapter: {_yaml_escape(bg.get('source_chapter', ''))}\n"
                skills = bg.get("skill_proficiencies", [])
                if skills:
                    content += "skill_proficiencies:\n"
                    for s in skills:
                        content += f"  - {_yaml_escape(str(s))}\n"
                tools = bg.get("tool_proficiencies", [])
                if tools:
                    content += "tool_proficiencies:\n"
                    for t in tools:
                        content += f"  - {_yaml_escape(str(t))}\n"
                content += f"---\n\n# {name}\n\n{bg.get('description', '')}\n\n"
                feature = bg.get("feature", {})
                if isinstance(feature, dict) and feature.get("name"):
                    content += f"## Feature: {feature['name']}\n{feature.get('description', '')}\n\n"
                if skills:
                    content += f"**Skill Proficiencies:** {', '.join(str(s) for s in skills)}\n"
                if tools:
                    content += f"**Tool Proficiencies:** {', '.join(str(t) for t in tools)}\n"
                equip = bg.get("equipment", [])
                if equip:
                    content += f"\n**Equipment:** {', '.join(str(e) for e in equip)}\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

        # Feats
        for feat in entities.get("feats", []):
            if not isinstance(feat, dict) or not feat.get("name", "").strip(): continue
            name = feat["name"]
            cat_dir = out_path / "Feats"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                content = f"---\ntags: [Feat]\nsource_chapter: {_yaml_escape(feat.get('source_chapter', ''))}\n"
                content += f"prerequisite: {_yaml_escape(feat.get('prerequisite', ''))}\n"
                content += f"---\n\n# {name}\n\n"
                prereq = feat.get("prerequisite", "")
                if prereq:
                    content += f"*Prerequisite: {prereq}*\n\n"
                content += f"{feat.get('description', '')}\n\n"
                benefits = feat.get("benefits", [])
                if benefits:
                    for b in benefits:
                        content += f"- {b}\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

        # Factions
        for faction in entities.get("factions", []):
            if not isinstance(faction, dict) or not faction.get("name", "").strip(): continue
            name = faction["name"]
            cat_dir = out_path / "Factions"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                members = faction.get("members", [])
                content = f"---\ntags: [Faction]\nsource_chapter: {_yaml_escape(faction.get('source_chapter', ''))}\n"
                content += f"type: {_yaml_escape(faction.get('type', ''))}\n"
                content += f"base_of_operations: {_yaml_escape(faction.get('base_of_operations', ''))}\n"
                content += f"---\n\n# {name}\n\n{faction.get('description', '')}\n\n"
                content += f"**Goals:** {faction.get('goals', '')}\n\n"
                if members:
                    content += "## Members\n"
                    for m in members:
                        content += f"- [[{m}]]\n"
                    content += "\n"
                allies = faction.get("allies", [])
                if allies:
                    content += f"**Allies:** {', '.join(f'[[{a}]]' for a in allies)}\n"
                enemies = faction.get("enemies", [])
                if enemies:
                    content += f"**Enemies:** {', '.join(f'[[{e}]]' for e in enemies)}\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

        # Lore Entries
        for lore in entities.get("lore_entries", []):
            if not isinstance(lore, dict) or not lore.get("name", "").strip(): continue
            name = lore["name"]
            cat_dir = out_path / "Lore"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                related = lore.get("related_entities", [])
                content = f"---\ntags: [Lore]\nsource_chapter: {_yaml_escape(lore.get('source_chapter', ''))}\n"
                content += f"category: {_yaml_escape(lore.get('category', ''))}\n"
                content += f"---\n\n# {name}\n\n{lore.get('description', '')}\n\n"
                if related:
                    content += "## Related\n"
                    for r in related:
                        content += f"- [[{r}]]\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

        # Top-level Bestiary (monsters from global array)
        for monster in entities.get("monsters", []):
            if not isinstance(monster, dict) or not monster.get("name", "").strip(): continue
            name = monster["name"]
            cat_dir = out_path / "Bestiary"
            cat_dir.mkdir(exist_ok=True)
            filepath = cat_dir / f"{sanitize_filename(name)}.md"
            if not filepath.exists():
                content = f"---\ntags: [Monster, Bestiary]\n"
                content += f"source_chapter: {_yaml_escape(monster.get('source_chapter', ''))}\n"
                content += f"---\n\n# {name}\n\n"
                statblock = monster.get("statblock", "")
                if statblock:
                    content += f"> [!danger]- Stat Block\n"
                    for line in str(statblock).splitlines():
                        content += f"> {line}\n"
                    content += "\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_files.append(str(filepath))

    # Generate _Home.md at vault root
    home_path = out_path / "_Home.md"
    home_content = "---\ntags: [Index]\n---\n\n"
    home_content += "# 📖 Vault Index\n\n"

    # Chapters — Dataview query (idempotent, no duplicate rows)
    home_content += "## Chapters\n\n"
    home_content += "```dataview\n"
    home_content += "TABLE length(file.inlinks) AS \"Links\"\n"
    home_content += "FROM #Chapter\n"
    home_content += "SORT file.name ASC\n"
    home_content += "```\n\n"

    # Dataview query blocks for chapter-scoped entities
    home_content += "## NPCs\n\n"
    home_content += "```dataview\n"
    home_content += "TABLE location AS \"Location\", motivation AS \"Motivation\", chapter AS \"Chapter\"\n"
    home_content += "FROM #NPC\n"
    home_content += "SORT chapter ASC, file.name ASC\n"
    home_content += "```\n\n"

    home_content += "## Encounters\n\n"
    home_content += "```dataview\n"
    home_content += "TABLE monsters AS \"Monsters\", chapter AS \"Chapter\"\n"
    home_content += "FROM #Encounter\n"
    home_content += "SORT chapter ASC, file.name ASC\n"
    home_content += "```\n\n"

    home_content += "## Items & Loot\n\n"
    home_content += "```dataview\n"
    home_content += "TABLE rarity AS \"Rarity\", chapter AS \"Chapter\"\n"
    home_content += "FROM #Item\n"
    home_content += "SORT rarity ASC, file.name ASC\n"
    home_content += "```\n\n"

    home_content += "## Bestiary\n\n"
    home_content += "```dataview\n"
    home_content += "TABLE chapter AS \"Appears In\"\n"
    home_content += "FROM #Monster\n"
    home_content += "SORT file.name ASC\n"
    home_content += "```\n\n"

    home_content += "## Locations\n\n"
    home_content += "```dataview\n"
    home_content += "TABLE chapter AS \"Chapter\"\n"
    home_content += "FROM #Location\n"
    home_content += "SORT chapter ASC, file.name ASC\n"
    home_content += "```\n\n"

    # Campaign setting entity sections (only if in campaign_setting mode)
    if mode == "campaign_setting":
        home_content += "## Races\n\n"
        home_content += "```dataview\n"
        home_content += "TABLE size AS \"Size\", speed AS \"Speed\", asi AS \"ASI\"\n"
        home_content += "FROM #Race\n"
        home_content += "SORT file.name ASC\n"
        home_content += "```\n\n"

        home_content += "## Deities\n\n"
        home_content += "```dataview\n"
        home_content += "TABLE alignment AS \"Alignment\", domains AS \"Domains\", symbol AS \"Symbol\"\n"
        home_content += "FROM #Deity\n"
        home_content += "SORT file.name ASC\n"
        home_content += "```\n\n"

        home_content += "## Spells\n\n"
        home_content += "```dataview\n"
        home_content += "TABLE level AS \"Level\", school AS \"School\", classes AS \"Classes\"\n"
        home_content += "FROM #Spell\n"
        home_content += "SORT level ASC, file.name ASC\n"
        home_content += "```\n\n"

        home_content += "## Classes\n\n"
        home_content += "```dataview\n"
        home_content += "TABLE base_class AS \"Base Class\", type AS \"Type\"\n"
        home_content += "FROM #Class\n"
        home_content += "SORT file.name ASC\n"
        home_content += "```\n\n"

        home_content += "## Backgrounds\n\n"
        home_content += "```dataview\n"
        home_content += "TABLE skill_proficiencies AS \"Skills\"\n"
        home_content += "FROM #Background\n"
        home_content += "SORT file.name ASC\n"
        home_content += "```\n\n"

        home_content += "## Feats\n\n"
        home_content += "```dataview\n"
        home_content += "TABLE prerequisite AS \"Prerequisite\"\n"
        home_content += "FROM #Feat\n"
        home_content += "SORT file.name ASC\n"
        home_content += "```\n\n"

        home_content += "## Factions\n\n"
        home_content += "```dataview\n"
        home_content += "TABLE type AS \"Type\", base_of_operations AS \"Base\"\n"
        home_content += "FROM #Faction\n"
        home_content += "SORT file.name ASC\n"
        home_content += "```\n\n"

        home_content += "## Lore\n\n"
        home_content += "```dataview\n"
        home_content += "TABLE category AS \"Category\"\n"
        home_content += "FROM #Lore\n"
        home_content += "SORT file.name ASC\n"
        home_content += "```\n"

    with open(home_path, "w", encoding="utf-8") as f:
        f.write(home_content)
    generated_files.append(str(home_path))

    return generated_files

