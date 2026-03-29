import os
import json
import logging
from pathlib import Path

def _get_llm_response(prompt: str, provider: str = "claude") -> str:
    content = ""
    if provider.lower() == "gemini":
        try:
            from google import genai
        except ImportError:
            raise Exception("google-genai SDK not installed")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise Exception("GEMINI_API_KEY environment variable not set")
        
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        content = response.text
            
    elif provider.lower() == "claude":
        try:
            import anthropic
        except ImportError:
            raise Exception("anthropic SDK not installed")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise Exception("ANTHROPIC_API_KEY environment variable not set")
            
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}]
        )
        content = message.content[0].text
            
    elif provider.lower() == "openai":
        try:
            import openai
        except ImportError:
            raise Exception("openai SDK not installed")
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise Exception("OPENAI_API_KEY environment variable not set")
            
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
    else:
        raise Exception(f"Unsupported provider: {provider}")
        
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()

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

def convert_entities_to_nimble(entities: dict, reference_dir: str = "references/nimble", provider: str = "claude") -> dict:
    """
    Takes a structured entities dict and converts each monster entity from 5e mechanics to Nimble 2e mechanics.
    """
    if "chapters" not in entities:
        return entities

    reference_text = _load_reference_material(reference_dir)
    
    # We will only convert the 'monsters' list in each chapter.
    converted_entities = entities.copy()
    
    for chapter in converted_entities["chapters"]:
        if "monsters" in chapter and chapter["monsters"]:
            prompt = f"""
You are an expert TTRPG designer converting D&D 5e monsters to the Nimble 2e system.
Review the following Nimble 2e mechanics reference material:

{reference_text}

Here is a list of monster entities in JSON format (extracted from a 5e document). 
Your task is to convert ALL of them to Nimble 2e mechanics. For each monster:
- Change the structure to include: `level`, `armor`, `hp`, `speed`, `saves`, `damage_traits`, `condition_immunities`, `actions`, `bonus_actions`, `reactions`, `legendary_actions`, `traits`, `senses`, `cr_original`, `role`, `conversion_notes`, and `system`: "Nimble 2e".
- CR maps to `level`. CR maps directly or calculate max(1, CR).
- AC maps to `armor` (Unarmored for <=13, Medium Armor for 14-17, Heavy Armor for 18+).
- HP and Speed carry over.
- Drop STR/DEX/CON/INT/WIS/CHA.
- Convert 5e attack descriptions to Nimble style (add "hits unless roll of 1, crits on max die").
- Preserve legendary actions (as Boss actions), traits, senses.
- Add `conversion_notes` for anything requiring GM review.
- Retain the `name` field for each monster.
- If a monster's json only contains the original statblock as a string, parse it and apply the conversion, returning the structured fields.

Input Monsters JSON:
{json.dumps(chapter["monsters"], indent=2)}

Respond ONLY with valid JSON containing the converted list of monsters under the key "monsters". Do not wrap in markdown or add explanations.
"""
            try:
                result = _get_llm_response(prompt, provider=provider)
                parsed = json.loads(result)
                if isinstance(parsed, dict) and "monsters" in parsed:
                    chapter["monsters"] = parsed["monsters"]
                elif isinstance(parsed, list):
                    chapter["monsters"] = parsed
            except Exception as e:
                logging.error(f"Failed to convert monsters block: {e}")
                # Mark them as failed or unconverted
                for m in chapter["monsters"]:
                    if isinstance(m, dict):
                        m["system"] = "Nimble 2e (Failed Conversion)"
                        m["conversion_notes"] = str(e)

    return converted_entities

def convert_5e_bestiary_to_nimble(input_dir: str, output_dir: str, tag: str = "Monster", provider: str = "claude", batch_size: int = 20) -> dict:
    """
    Bulk converts a directory of 5e statblocks to Nimble 2e formatted Obsidian markdown.
    """
    from obsidian_tools import extract_entities_llm, extract_entities_heuristic, generate_obsidian
    
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    
    if not in_path.exists():
        return {"error": f"Input directory {input_dir} not found"}
        
    out_path.mkdir(parents=True, exist_ok=True)
    
    # Read all markdown files
    md_files = list(in_path.glob("*.md"))
    
    converted = 0
    failed = []
    
    all_entities: dict = {
        "chapters": [
            {
                "name": "Bestiary",
                "overview": "Converted Nimble 2e Monsters",
                "monsters": []
            }
        ]
    }
    
    # Process in batches
    md_files_list = [f for f in md_files]
    for i in range(0, len(md_files_list), batch_size):
        batch = md_files_list[i:i + batch_size]
        
        batch_text = ""
        for f in batch:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    batch_text += f"\n\n--- Start Statblock: {f.name} ---\n{file.read()}"
            except Exception as e:
                failed.append(f.name)
        
        if batch_text:
            # 1. Extract using LLM
            entities = extract_entities_llm(batch_text, provider=provider)
            
            if "error" in entities:
                for f in batch: failed.append(f.name)
                continue
                
            # 2. Convert to Nimble
            nimble_entities = convert_entities_to_nimble(entities, provider=provider)
            
            # 3. Accumulate monsters
            if "chapters" in nimble_entities:
                for chap in nimble_entities["chapters"]:
                    if "monsters" in chap:
                        all_entities["chapters"][0]["monsters"].extend(chap["monsters"])
                        converted += len(chap["monsters"])
    
    # Apply tags if necessary (we can pass it to the entities or let generator handle it based on role/type)
    for m in all_entities["chapters"][0]["monsters"]:
        m["tag_override"] = tag
        
    # 4. Generate markdown
    generate_obsidian(all_entities, output_dir)
    
    return {
        "converted": converted,
        "failed": failed,
        "output_dir": output_dir
    }
