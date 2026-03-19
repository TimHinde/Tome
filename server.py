import sys
import logging
from dotenv import load_dotenv

# MCP stdio uses stdout as the JSON-RPC transport pipe.
# All logging must go to stderr, or it will corrupt the message stream.
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
load_dotenv()

from mcp.server.fastmcp import FastMCP
from reference_tools import query_reference, list_reference_topics
from pdf_tools import analyze_pdf_structure, extract_pdf_section, suggest_chunks
from obsidian_tools import (
    extract_entities_llm,
    extract_entities_heuristic,
    enrich_with_references,
    generate_obsidian,
    merge_entities
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
def suggest_pdf_chunks(pdf_path: str) -> list:
    """
    Analyze PDF TOC and suggest logical page-range chunks for extraction.
    Returns a list of {name, start_page, end_page} dicts based on chapter/section boundaries.
    Use this after analyze_pdf to plan your extraction strategy.
    """
    return suggest_chunks(pdf_path)

@mcp.tool()
def extract_entities_with_llm(text: str, provider: str = "gemini") -> dict:
    """
    Uses an LLM (Gemini, Claude, or OpenAI) to extract structured TTRPG entities from text.
    Returns a dict with chapters (adventure content) and global arrays (races, classes, spells, deities, etc.).
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
def merge_entity_dicts(entity_dicts: list[dict]) -> dict:
    """
    Merge multiple entity extraction results into one, deduplicating by name.
    Use this after extracting entities from multiple chunks to combine them before generating output.
    First-write-wins: the first extraction of an entity keeps its data.
    """
    return merge_entities(entity_dicts)

@mcp.tool()
def generate_obsidian_markdown(entities: dict, output_dir: str, mode: str = "auto") -> list[str]:
    """
    Generates Obsidian Markdown files from structured entities.
    
    Modes:
    - "adventure": Chapter-scoped subfolders only (original behavior)
    - "campaign_setting": Global folders for reference content + chapter folders for adventure content
    - "auto" (default): Detects from entity data — campaign_setting if global arrays present, else adventure
    
    Returns a list of generated file paths.
    """
    return generate_obsidian(entities, output_dir, mode)

if __name__ == "__main__":
    mcp.run()

