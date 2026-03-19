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
        """Verify _Home.md is created with Dataview query blocks."""
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
            # Dataview blocks for all core entity types
            self.assertIn("```dataview", content)
            self.assertIn("FROM #Chapter", content)
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

    def test_campaign_setting_mode_global_folders(self):
        """Verify campaign_setting mode creates top-level global entity folders with correct frontmatter."""
        entities = {
            "chapters": [],
            "races": [{"name": "Elf", "description": "Graceful folk.", "size": "Medium", "speed": 30,
                        "asi": {"DEX": 2}, "subraces": ["High Elf"], "traits": [{"name": "Darkvision", "description": "See in the dark."}],
                        "languages": ["Common", "Elvish"], "source_chapter": "Races"}],
            "spells": [{"name": "Fireball", "level": 3, "school": "Evocation", "casting_time": "1 action",
                        "range": "150 feet", "components": "V, S, M", "duration": "Instantaneous",
                        "classes": ["Sorcerer", "Wizard"], "description": "A bright streak.", "source_chapter": "Spells"}],
            "deities": [{"name": "Pelor", "title": "The Sun Father", "alignment": "Neutral Good",
                         "domains": ["Life", "Light"], "symbol": "Sun", "worshippers": "Farmers",
                         "description": "God of the sun.", "source_chapter": "Deities"}],
            "classes": [{"name": "College of Lore", "base_class": "Bard", "type": "subclass",
                         "description": "A learned bard.", "features": [{"name": "Bonus Proficiencies", "level": 3, "description": "Gain 3 skills."}],
                         "source_chapter": "Classes"}],
            "backgrounds": [{"name": "Sage", "description": "A scholarly type.", "skill_proficiencies": ["Arcana", "History"],
                             "tool_proficiencies": [], "feature": {"name": "Researcher", "description": "Find info."},
                             "source_chapter": "Backgrounds"}],
            "feats": [{"name": "Alert", "prerequisite": "None", "description": "Always ready.",
                       "benefits": ["+5 to initiative"], "source_chapter": "Feats"}],
            "factions": [{"name": "Harpers", "type": "Secret Society", "description": "Good guys.",
                          "goals": "Fight evil", "members": ["Elminster"], "base_of_operations": "Waterdeep",
                          "allies": [], "enemies": ["Zhentarim"], "source_chapter": "Factions"}],
            "lore_entries": [{"name": "The Sundering", "category": "History", "description": "The world broke.",
                              "related_entities": ["Pelor"], "source_chapter": "Lore"}],
        }
        files = generate_obsidian(entities, self.test_dir, mode="campaign_setting")

        # Check global folders exist with files
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Races", "Elf.md")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Spells", "Fireball.md")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Deities", "Pelor.md")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Classes", "College of Lore.md")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Backgrounds", "Sage.md")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Feats", "Alert.md")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Factions", "Harpers.md")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Lore", "The Sundering.md")))

        # Verify frontmatter tags
        with open(os.path.join(self.test_dir, "Races", "Elf.md"), "r") as f:
            content = f.read()
            self.assertIn("tags: [Race]", content)
            self.assertIn("size: Medium", content)
            self.assertIn("DEX: 2", content)

        with open(os.path.join(self.test_dir, "Spells", "Fireball.md"), "r") as f:
            content = f.read()
            self.assertIn("tags: [Spell]", content)
            self.assertIn("level: 3", content)
            self.assertIn("school: Evocation", content)

        with open(os.path.join(self.test_dir, "Deities", "Pelor.md"), "r") as f:
            content = f.read()
            self.assertIn("tags: [Deity]", content)
            self.assertIn("alignment: Neutral Good", content)

    def test_auto_mode_detects_campaign_setting(self):
        """Auto mode should resolve to campaign_setting when global arrays are present."""
        entities = {
            "chapters": [{"name": "Ch1", "npcs": [], "locations": [], "encounters": [],
                          "events": [], "items": [], "monsters": []}],
            "races": [{"name": "Dwarf", "description": "Stout.", "size": "Medium", "speed": 25}],
        }
        files = generate_obsidian(entities, self.test_dir, mode="auto")
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "Races", "Dwarf.md")))

    def test_auto_mode_detects_adventure(self):
        """Auto mode should resolve to adventure when no global arrays are present."""
        entities = {
            "chapters": [{
                "name": "Chapter 1",
                "npcs": [{"name": "Bob", "motivation": "Live"}],
                "locations": [], "encounters": [], "events": [],
                "items": [], "monsters": []
            }]
        }
        files = generate_obsidian(entities, self.test_dir, mode="auto")
        # No global folders should exist
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "Races")))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "Spells")))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "Deities")))

    def test_deduplication_skips_existing(self):
        """Calling generate_obsidian twice should not overwrite or double file count."""
        entities = {
            "chapters": [{
                "name": "Chapter 1",
                "npcs": [{"name": "Alice", "motivation": "Explore"}],
                "locations": [], "encounters": [], "events": [],
                "items": [], "monsters": []
            }]
        }
        files1 = generate_obsidian(entities, self.test_dir)
        npc_file = os.path.join(self.test_dir, "Chapter 1", "NPCs", "Alice.md")
        self.assertTrue(os.path.exists(npc_file))

        # Write a marker into the file to prove it's not overwritten
        with open(npc_file, "a") as f:
            f.write("\n<!-- marker -->")

        files2 = generate_obsidian(entities, self.test_dir)

        # The NPC file should NOT be in the second run's output (skipped)
        self.assertNotIn(npc_file, files2)

        # The marker should still be present (file not overwritten)
        with open(npc_file, "r") as f:
            self.assertIn("<!-- marker -->", f.read())

    def test_home_page_dataview_campaign_setting(self):
        """In campaign_setting mode, _Home.md should include Dataview queries for global entity types."""
        entities = {
            "chapters": [],
            "races": [{"name": "Elf", "description": "Graceful.", "size": "Medium", "speed": 30}],
            "deities": [{"name": "Pelor", "alignment": "NG", "domains": ["Life"]}],
        }
        generate_obsidian(entities, self.test_dir, mode="campaign_setting")
        with open(os.path.join(self.test_dir, "_Home.md"), "r") as f:
            content = f.read()
            self.assertIn("FROM #Race", content)
            self.assertIn("FROM #Deity", content)
            self.assertIn("FROM #Spell", content)
            self.assertIn("FROM #Faction", content)
            self.assertIn("FROM #Feat", content)
            self.assertIn("FROM #Background", content)
            self.assertIn("FROM #Lore", content)

    def test_heuristic_extracts_new_types(self):
        """Verify extract_entities_heuristic recognizes global entity type lines."""
        text = (
            "Race: Elf\n"
            "Spell: Fireball\n"
            "Deity: Pelor\n"
            "Class: Fighter\n"
            "Background: Sage\n"
            "Feat: Alert\n"
            "Faction: Harpers\n"
            "Lore: The Sundering\n"
        )
        entities = extract_entities_heuristic(text)
        self.assertEqual(len(entities["races"]), 1)
        self.assertEqual(entities["races"][0]["name"], "Elf")
        self.assertEqual(len(entities["spells"]), 1)
        self.assertEqual(entities["spells"][0]["name"], "Fireball")
        self.assertEqual(len(entities["deities"]), 1)
        self.assertEqual(entities["deities"][0]["name"], "Pelor")
        self.assertEqual(len(entities["classes"]), 1)
        self.assertEqual(entities["classes"][0]["name"], "Fighter")
        self.assertEqual(len(entities["backgrounds"]), 1)
        self.assertEqual(entities["backgrounds"][0]["name"], "Sage")
        self.assertEqual(len(entities["feats"]), 1)
        self.assertEqual(entities["feats"][0]["name"], "Alert")
        self.assertEqual(len(entities["factions"]), 1)
        self.assertEqual(entities["factions"][0]["name"], "Harpers")
        self.assertEqual(len(entities["lore_entries"]), 1)
        self.assertEqual(entities["lore_entries"][0]["name"], "The Sundering")

if __name__ == "__main__":
    unittest.main()
