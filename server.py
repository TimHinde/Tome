import sys
import logging
from dotenv import load_dotenv

# MCP stdio uses stdout as the JSON-RPC transport pipe.
# All logging must go to stderr, or it will corrupt the message stream.
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
load_dotenv()

from mcp.server.fastmcp import FastMCP
from reference_tools import query_reference, list_reference_topics
from pdf_tools import analyze_pdf_structure, extract_pdf_section
from obsidian_tools import (
    extract_entities_llm,
    extract_entities_heuristic,
    enrich_with_references,
    generate_obsidian,
    convert_5e_to_nimble
)

# Initialize FastMCP Server
mcp = FastMCP("tome")

@mcp.tool()
def query_references(query: str, reference_dir: str = None) -> str:
    """
    Query local reference markdown files (e.g. D&D SRD, Pathfinder SRD, homebrew).
    Searches headers first, then falls back to text matches.
    Returns snippets from the reference material where the query is found.
    """
    return query_reference(query, reference_dir)

@mcp.tool()
def convert_5e_monster_to_nimble(statblock: str) -> dict:
    """
    Prepares context for converting a D&D 5e monster statblock to Nimble RPG 2e format.
    Returns the statblock, Nimble 2e reference material, output format description, and conversion
    instructions. The calling LLM performs the actual conversion and writes the output file.
    """
    return convert_5e_to_nimble(statblock)

@mcp.tool()
def convert_5e_bestiary_to_nimble_batch(input_dir: str, output_dir: str) -> dict:
    """
    Prepares context for bulk-converting a directory of D&D 5e statblock markdown files to Nimble 2e.
    Returns all statblock contents, Nimble 2e reference material, and conversion instructions.
    The calling LLM performs the conversion and writes one Obsidian markdown file per monster to output_dir.
    """
    from nimble_tools import convert_5e_bestiary_to_nimble
    return convert_5e_bestiary_to_nimble(input_dir, output_dir)

@mcp.tool()
def list_references(reference_dir: str = None) -> str:
    """
    List all available high-level topics/files in a reference directory.
    Useful for seeing what rules categories are available before querying.
    """
    return list_reference_topics(reference_dir)

@mcp.tool()
def analyze_pdf(pdf_path: str) -> str:
    """
    Opens the specified local PDF file and extracts its Table of Contents.
    Returns a heuristic guess of the Document Type and the structured TOC.
    Useful for identifying chapters and page ranges before extraction.
    """
    return analyze_pdf_structure(pdf_path)

@mcp.tool()
def extract_pdf_text(pdf_path: str, start_page: int, end_page: int) -> str:
    """
    Extracts raw text from a specified local PDF file given a start and end page (1-indexed).
    Use this after analyze_pdf to pull specific chapters or encounters.
    """
    return extract_pdf_section(pdf_path, start_page, end_page)

@mcp.tool()
def extract_entities_with_llm(text: str, provider: str = "gemini") -> dict:
    """
    Uses an LLM (Gemini, Claude, or OpenAI) to extract structured TTRPG entities from text.
    Returns a dict with chapters containing npcs, locations, encounters, events, items, monsters.
    Requires GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY environment variables.
    """
    return extract_entities_llm(text, provider)

@mcp.tool()
def extract_entities_with_heuristics(text: str) -> dict:
    """
    Fallback tool that uses heuristics (regex) to extract basic entities when an LLM isn't available.
    """
    return extract_entities_heuristic(text)

@mcp.tool()
def enrich_entities(entities: dict, reference_dirs: list[str] = None) -> dict:
    """
    Iterates through extracted entities and queries reference material to enrich them with rules references.
    Pass reference_dirs to specify custom reference directories (e.g. for non-D&D systems).
    """
    return enrich_with_references(entities, reference_dirs or [])

@mcp.tool()
def generate_obsidian_markdown(entities: dict, output_dir: str) -> list[str]:
    """
    Generates Obsidian Markdown files from structured entities.
    Returns a list of generated file paths.
    """
    return generate_obsidian(entities, output_dir)

if __name__ == "__main__":
    mcp.run()
