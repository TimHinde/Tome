import unittest
from obsidian_tools import merge_entities


class TestMergeEntities(unittest.TestCase):

    def test_merge_deduplicates_by_name(self):
        """Merging two dicts with the same NPC name should produce one entry (first-write-wins)."""
        dict1 = {
            "chapters": [{
                "name": "Chapter 1",
                "npcs": [{"name": "Alice", "motivation": "Explore"}],
                "locations": [], "encounters": [], "events": [], "items": [], "monsters": []
            }]
        }
        dict2 = {
            "chapters": [{
                "name": "Chapter 1",
                "npcs": [{"name": "Alice", "motivation": "Fight"}],
                "locations": [], "encounters": [], "events": [], "items": [], "monsters": []
            }]
        }
        merged = merge_entities([dict1, dict2])
        ch1_npcs = [c for c in merged["chapters"] if c["name"] == "Chapter 1"][0]["npcs"]
        self.assertEqual(len(ch1_npcs), 1)
        # First-write-wins: motivation should be "Explore"
        self.assertEqual(ch1_npcs[0]["motivation"], "Explore")

    def test_merge_combines_types(self):
        """Merging one dict with races and another with spells should produce both."""
        dict1 = {
            "chapters": [],
            "races": [{"name": "Elf", "description": "Graceful."}],
        }
        dict2 = {
            "chapters": [],
            "spells": [{"name": "Fireball", "level": 3, "description": "Boom."}],
        }
        merged = merge_entities([dict1, dict2])
        self.assertEqual(len(merged.get("races", [])), 1)
        self.assertEqual(merged["races"][0]["name"], "Elf")
        self.assertEqual(len(merged.get("spells", [])), 1)
        self.assertEqual(merged["spells"][0]["name"], "Fireball")

    def test_merge_global_deduplicates(self):
        """Global arrays should also deduplicate by name."""
        dict1 = {"chapters": [], "races": [{"name": "Elf", "description": "Version 1"}]}
        dict2 = {"chapters": [], "races": [{"name": "Elf", "description": "Version 2"}]}
        merged = merge_entities([dict1, dict2])
        self.assertEqual(len(merged["races"]), 1)
        self.assertEqual(merged["races"][0]["description"], "Version 1")

    def test_merge_combines_different_chapters(self):
        """Chapters with different names should both appear in merged output."""
        dict1 = {
            "chapters": [{"name": "Chapter 1", "npcs": [{"name": "Alice"}],
                          "locations": [], "encounters": [], "events": [], "items": [], "monsters": []}]
        }
        dict2 = {
            "chapters": [{"name": "Chapter 2", "npcs": [{"name": "Bob"}],
                          "locations": [], "encounters": [], "events": [], "items": [], "monsters": []}]
        }
        merged = merge_entities([dict1, dict2])
        self.assertEqual(len(merged["chapters"]), 2)
        chapter_names = {c["name"] for c in merged["chapters"]}
        self.assertIn("Chapter 1", chapter_names)
        self.assertIn("Chapter 2", chapter_names)

    def test_merge_empty_input(self):
        """Merging an empty list should return a valid structure."""
        merged = merge_entities([])
        self.assertIn("chapters", merged)
        self.assertEqual(len(merged["chapters"]), 0)

    def test_merge_removes_empty_global_arrays(self):
        """Empty global arrays should be removed from output."""
        dict1 = {"chapters": [], "races": [{"name": "Elf", "description": "..."}]}
        merged = merge_entities([dict1])
        self.assertIn("races", merged)
        self.assertNotIn("spells", merged)
        self.assertNotIn("deities", merged)


if __name__ == "__main__":
    unittest.main()
