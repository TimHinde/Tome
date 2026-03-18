import os
import re
import json
from pathlib import Path
from reference_tools import query_reference

def extract_entities_llm(text: str, provider: str = "gemini") -> dict:
    """
    Uses an LLM to extract entities from the raw adventure text.
    Returns a dictionary of structured data.
    """
    prompt = f"""
    You are an AI assistant helping a Game Master. 
    Review the following TTRPG adventure text and extract the key entities, organizing them hierarchically by Chapter or Arc.

    Use these STRICT definitions — every scene goes in exactly ONE category:
    - ENCOUNTER: Any scene where the party faces an active challenge requiring dice rolls — combat, skill challenge, chase, puzzle, trap, or social conflict with mechanics. Caravan road encounters, boss fights, and multi-stage challenges are all encounters.
    - EVENT: A pure narrative beat with no active dice-roll challenge — story transitions, chapter setup/intro, lore reveals, consequence text (what happens after), or GM housekeeping notes.
    - LOCATION: A physical place the party can explore, distinct from the encounter that happens there. Only create a location if it has descriptive value beyond being "the room where encounter X happens."
    - Do NOT put the same scene in both encounters and events. If something has mechanics, it is an encounter only.

    Return ONLY a valid JSON object with a single "chapters" array. Each chapter should contain:
    - name: "Chapter 1: The Beginning"
    - overview: "A detailed narrative summary of the chapter's storyline and events"
    - reading_order: A flat, ordered list reflecting the sequence a GM would read these documents during play. ONLY include types "location", "encounter", and "event" — do NOT include npc, monster, or item entries. Each entry: {{"name": "...", "type": "event|location|encounter", "note": "One sentence: why the GM reads this now / what it triggers"}}. Optional entries should be labeled "(Optional)" at the start of their note.
    - npcs: [{{"name": "...", "motivation": "...", "secret": "...", "statblock": "...", "location": "..."}}]
    - locations: [{{"name": "...", "description": "...", "encounters": ["..."], "loot": ["..."], "exits": ["..."]}}]
    - encounters: [{{"name": "...", "read_aloud": "Exact text to read aloud to players, or empty string if none", "description": "Full GM-facing context: setup, what is really happening, tactics, branching outcomes", "mechanics": "All DCs, rolls, conditions, turn structure, success/failure consequences", "monsters": ["Monster Name"], "npcs_present": ["NPC Name"]}}]
    - events: [{{"name": "...", "read_aloud": "Player-facing text if applicable, else empty string", "description": "Full GM text for this event including all context and options", "mechanics": "DCs, checks, triggers, conditions", "next_steps": "What happens after / branching paths", "npcs_present": ["NPC Name"]}}]
    - items: [{{"name": "...", "rarity": "...", "description": "...", "mechanics": "..."}}]
    - monsters: [{{"name": "...", "statblock": "Full text of the stat block if it is explicitly provided in the text"}}]

    If the text doesn't explicitly have chapters, put everything under a single chapter named "Arc: Uncategorized".
    Return ONLY valid JSON. Do not include markdown formatting or other text around the JSON.
    Text to analyze:
    {text}
    """

    content = ""
    if provider.lower() == "gemini":
        try:
            from google import genai
        except ImportError:
            return {"error": "google-genai SDK not installed"}
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {"error": "GEMINI_API_KEY environment variable not set"}
        
        client = genai.Client(api_key=api_key)
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
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
                model="claude-sonnet-4-5",
                max_tokens=16000,
                messages=[{"role": "user", "content": prompt}]
            )
            content = message.content[0].text
        except Exception as e:
            return {"error": f"Failed to call Claude API: {e}"}
    else:
        return {"error": f"Unsupported provider: {provider}"}
        
    # Clean up code blocks if needed
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
        }]
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


def generate_obsidian(entities: dict, output_dir: str) -> list[str]:
    """
    Generates Obsidian Markdown files from nested chapter entities.
    Includes enriched YAML frontmatter for Dataview and a _Home.md index.
    Returns a list of generated file paths.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    generated_files = []
    
    if "chapters" not in entities:
        return []

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
                
                content = f"---\ntags: [Monster, Bestiary]\n"
                content += f"chapter: {_yaml_escape(chap_name)}\n"
                content += f"---\n\n"
                content += f"# {name}\n\n"
                content += f"{monster.get('statblock', '')}\n\n"
                
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

    # Generate _Home.md at vault root
    home_path = out_path / "_Home.md"
    home_content = "---\ntags: [Index]\n---\n\n"
    home_content += "# 📖 Vault Index\n\n"

    # Static chapter table
    home_content += "## Chapters\n\n"
    home_content += "| Chapter | Encounters | NPCs | Locations | Events | Items | Monsters |\n"
    home_content += "|---|---|---|---|---|---|---|\n"
    for stats in chapter_stats:
        home_content += f"| [[{stats['name']}]] | {stats['encounters']} | {stats['npcs']} | {stats['locations']} | {stats['events']} | {stats['items']} | {stats['monsters']} |\n"
    home_content += "\n"

    # Dataview query blocks
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
    home_content += "```\n"

    with open(home_path, "w", encoding="utf-8") as f:
        f.write(home_content)
    generated_files.append(str(home_path))

    return generated_files

