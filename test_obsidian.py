import unittest
import os
import shutil
from obsidian_tools import (
    extract_entities_heuristic,
    enrich_with_references,
    generate_obsidian
)

class TestObsidianTools(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_obsidian_output"
        os.makedirs(self.test_dir, exist_ok=True)
        
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            
    def test_extract_heuristic(self):
        text = "NPC: Goblin King\nScene: Throneroom\nEncounter: Ambush\nEvent: The Floor Collapses\nItem: Crown of Rags"
        entities = extract_entities_heuristic(text)
        chapter = entities["chapters"][0]
        self.assertEqual(len(chapter["npcs"]), 1)
        self.assertEqual(chapter["npcs"][0]["name"], "Goblin King")
        self.assertEqual(len(chapter["locations"]), 1)
        self.assertEqual(chapter["locations"][0]["name"], "Throneroom")
        self.assertEqual(len(chapter["encounters"]), 1)
        self.assertEqual(chapter["encounters"][0]["name"], "Ambush")
        self.assertEqual(len(chapter["events"]), 1)
        self.assertEqual(chapter["events"][0]["name"], "The Floor Collapses")
        self.assertEqual(len(chapter["items"]), 1)
        self.assertEqual(chapter["items"][0]["name"], "Crown of Rags")
        
    def test_enrich_with_references(self):
        entities = {
            "chapters": [{
                "name": "Chapter 1",
                "npcs": [{"name": "Goblin", "statblock": "Goblin"}],
                "encounters": [{"name": "Fight", "monsters": ["Goblin"]}],
                "events": [],
                "locations": [],
                "items": []
            }]
        }
        enriched = enrich_with_references(entities, [])
        chapter = enriched["chapters"][0]
        self.assertEqual(chapter["npcs"][0]["name"], "Goblin")
        self.assertTrue(len(chapter["encounters"][0].get("srd_references", [])) > 0)
        self.assertEqual(chapter["encounters"][0]["srd_references"][0]["name"], "Goblin")

    def test_generate_obsidian(self):
        entities = {
            "chapters": [{
                "name": "The Great Cave",
                "description": "A very dark cave.",
                "npcs": [{"name": "Goblin King", "location": "Throneroom", "statblock": "Goblin", "motivation": "Rule the cave"}],
                "locations": [{"name": "Throneroom", "description": "A very dirty room.", "encounters": ["Goblin King"]}],
                "encounters": [{"name": "Throne Fight", "description": "Fight the king", "mechanics": "Roll initiative.", "monsters": ["Goblin", "Big Bat"]}],
                "events": [{"name": "Cave In", "next_steps": "Run away"}],
                "items": [{"name": "Crown of Rags", "rarity": "Common", "mechanics": "Does nothing."}],
                "monsters": [{"name": "Big Bat", "statblock": "AC 12, HP 5, Bite attack"}]
            }]
        }
        
        files = generate_obsidian(entities, self.test_dir)
        self.assertEqual(len(files), 8)  # 6 child entities + 1 chapter file + 1 _Home.md
        
        # Check Chapter file
        chapter_dir = os.path.join(self.test_dir, "The Great Cave")
        chapter_file = os.path.join(chapter_dir, "The Great Cave.md")
        self.assertTrue(os.path.exists(chapter_file))
        with open(chapter_file, "r") as f:
            content = f.read()
            self.assertIn("tags: [Chapter]", content)
            self.assertIn("[[Goblin King]]", content)
            self.assertIn("[[Cave In]]", content)
            self.assertIn("[[Big Bat]]", content)

        # Check Encounter file
        enc_file = os.path.join(chapter_dir, "Encounters", "Throne Fight.md")
        self.assertTrue(os.path.exists(enc_file))
        with open(enc_file, "r") as f:
            content = f.read()
            self.assertIn("tags: [Encounter]", content)
            self.assertIn("Roll initiative.", content)
            self.assertIn("Big Bat", content)
            
        # Check Custom Monster file
        monster_file = os.path.join(chapter_dir, "Monsters", "Big Bat.md")
        self.assertTrue(os.path.exists(monster_file))
        with open(monster_file, "r") as f:
            content = f.read()
            self.assertIn("tags: [Monster, Bestiary]", content)
            self.assertIn("AC 12, HP 5", content)

    def test_home_page_generated(self):
        """Verify _Home.md is created with static tables and Dataview blocks."""
        entities = {
            "chapters": [{
                "name": "Chapter 1: The Beginning",
                "description": "A test chapter.",
                "npcs": [{"name": "Test NPC", "location": "Inn", "motivation": "Survive"}],
                "locations": [{"name": "The Inn", "description": "A cozy inn."}],
                "encounters": [{"name": "Bar Fight", "description": "A brawl.", "monsters": ["Thug"]}],
                "events": [],
                "items": [],
                "monsters": []
            }]
        }
        files = generate_obsidian(entities, self.test_dir)
        
        home_file = os.path.join(self.test_dir, "_Home.md")
        self.assertTrue(os.path.exists(home_file))
        
        with open(home_file, "r") as f:
            content = f.read()
            # Static chapter table
            self.assertIn("| Chapter |", content)
            self.assertIn("[[Chapter 1: The Beginning]]", content)
            # Dataview blocks
            self.assertIn("```dataview", content)
            self.assertIn("FROM #NPC", content)
            self.assertIn("FROM #Encounter", content)
            self.assertIn("FROM #Item", content)
            self.assertIn("FROM #Monster", content)
            self.assertIn("FROM #Location", content)

    def test_enriched_frontmatter(self):
        """Verify all entity types include chapter field and type-specific metadata."""
        entities = {
            "chapters": [{
                "name": "Chapter 2: The Hunt",
                "description": "Hunting time.",
                "npcs": [{"name": "Hunter", "location": "Forest", "motivation": "Track prey", "statblock": "Scout"}],
                "locations": [{"name": "Dark Forest", "description": "Spooky trees."}],
                "encounters": [{"name": "Wolf Attack", "description": "Wolves!", "monsters": ["Wolf", "Dire Wolf"], "npcs_present": ["Hunter"]}],
                "events": [{"name": "Storm Arrives", "next_steps": "Seek shelter"}],
                "items": [{"name": "Hunting Bow", "rarity": "Uncommon", "mechanics": "+1 to hit"}],
                "monsters": [{"name": "Dire Wolf", "statblock": "AC 14, HP 37"}]
            }]
        }
        generate_obsidian(entities, self.test_dir)
        chap_dir = os.path.join(self.test_dir, "Chapter 2 The Hunt")
        
        # NPC frontmatter
        with open(os.path.join(chap_dir, "NPCs", "Hunter.md"), "r") as f:
            content = f.read()
            self.assertIn("chapter:", content)
            self.assertIn("motivation:", content)
            self.assertIn("location:", content)
        
        # Encounter frontmatter — monsters as YAML list
        with open(os.path.join(chap_dir, "Encounters", "Wolf Attack.md"), "r") as f:
            content = f.read()
            self.assertIn("chapter:", content)
            self.assertIn("monsters:", content)
            self.assertIn("  - Wolf", content)
            self.assertIn("npcs_present:", content)
            self.assertIn("  - Hunter", content)
        
        # Event frontmatter
        with open(os.path.join(chap_dir, "Events", "Storm Arrives.md"), "r") as f:
            content = f.read()
            self.assertIn("chapter:", content)
            self.assertIn("next_steps:", content)
        
        # Item frontmatter
        with open(os.path.join(chap_dir, "Items", "Hunting Bow.md"), "r") as f:
            content = f.read()
            self.assertIn("chapter:", content)
            self.assertIn("rarity:", content)
        
        # Monster frontmatter
        with open(os.path.join(chap_dir, "Monsters", "Dire Wolf.md"), "r") as f:
            content = f.read()
            self.assertIn("chapter:", content)
            self.assertIn("tags: [Monster, Bestiary]", content)

        # Location frontmatter
        with open(os.path.join(chap_dir, "Locations", "Dark Forest.md"), "r") as f:
            content = f.read()
            self.assertIn("chapter:", content)

    def test_generate_nimble_monster(self):
        """Verify Nimble 2e monsters get the correct callout format and frontmatter."""
        entities = {
            "chapters": [{
                "name": "Nimble Test Chapter",
                "monsters": [{
                    "name": "Nimble Goblin",
                    "system": "Nimble 2e",
                    "role": "Skirmisher",
                    "level": 1,
                    "hp": 7,
                    "armor": "Unarmored",
                    "speed": "30 ft.",
                    "damage_traits": "Vulnerable: Fire",
                    "actions": ["Shortbow. Ranged attack (hits unless roll of 1, crits on max die). Hit: 3 piercing."],
                    "conversion_notes": "Needs review"
                }]
            }]
        }
        
        generate_obsidian(entities, self.test_dir)
        chap_dir = os.path.join(self.test_dir, "Nimble Test Chapter")
        monster_file = os.path.join(chap_dir, "Monsters", "Nimble Goblin.md")
        
        self.assertTrue(os.path.exists(monster_file))
        with open(monster_file, "r") as f:
            content = f.read()
            
            # Check custom tag
            self.assertIn("tags: [Monster, Nimble, Skirmisher]", content)
            self.assertIn('source_system: "D&D 5e (converted to Nimble 2e)"', content)
            
            # Check callout structure
            self.assertIn("> [!info]- Nimble Stat Block", content)
            self.assertIn("> **Level:** 1 | **Role:** Skirmisher | **HP:** 7 | **Armor:** Unarmored | **Speed:** 30 ft.", content)
            self.assertIn("> **Damage Traits:** Vulnerable: Fire", content)
            
            # Check Actions list formatting
            self.assertIn("> **Actions**", content)
            self.assertIn("> Shortbow. Ranged attack", content)
            
            # Check conversion notes callout
            self.assertIn("> [!warning]- Conversion Notes", content)
            self.assertIn("> - Needs review", content)

if __name__ == "__main__":
    unittest.main()
