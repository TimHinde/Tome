import os
import re
from pathlib import Path

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REFERENCE_DIR = os.path.join(WORKSPACE_DIR, "references", "SRD", "dndsrd5.2_markdown", "src")


def query_reference(query: str, reference_dir: str = None) -> str:
    """
    Query markdown reference files for a given term.
    Searches headers first, then falls back to text matches.
    Works with any system's reference material — D&D SRD, Pathfinder, etc.
    """
    ref_path = Path(reference_dir) if reference_dir else Path(DEFAULT_REFERENCE_DIR)
    if not ref_path.exists():
        return f"Error: Reference directory not found at {ref_path}"

    results = []

    # Try to find a header that matches the query
    header_pattern = re.compile(rf"^(#{{1,6}})\s+.*?\b{re.escape(query)}\b.*$", re.IGNORECASE | re.MULTILINE)

    for filepath in ref_path.glob("*.md"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. Search for a header match (e.g., "## Gorgon")
            match = header_pattern.search(content)
            if match:
                header_hashes = match.group(1)
                start_idx = match.start()

                # Find the next header of the same or higher priority
                next_header_pattern = re.compile(rf"^#{{1,{len(header_hashes)}}}\s+", re.MULTILINE)
                end_idx = len(content)
                newline_idx = content.find('\n', start_idx)

                if newline_idx != -1:
                    next_match = next_header_pattern.search(content, newline_idx + 1)
                    if next_match:
                        end_idx = next_match.start()

                snippet = content[start_idx:end_idx].strip()
                results.append(f"### Match found in: {filepath.name}\n```markdown\n{snippet}\n```")
                continue  # Move to next file if we found a good section hit

            # 2. Fallback: If no header match, look for a simple text match and return a snippet
            if query.lower() in content.lower():
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if query.lower() in line.lower():
                        start = max(0, i - 2)
                        end = min(len(lines), i + 8)
                        snippet = "\n".join(lines[start:end])
                        results.append(f"### Match found in: {filepath.name}\n```markdown\n{snippet}\n```")
                        break
        except Exception as e:
            results.append(f"Error reading {filepath.name}: {e}")

    if not results:
        return f"No results found for '{query}' in the reference material."

    return "\n\n".join(results)


def list_reference_topics(reference_dir: str = None) -> str:
    """
    List all available high-level topics/files in a reference directory.
    Useful for seeing what rules categories are available before querying.
    """
    ref_path = Path(reference_dir) if reference_dir else Path(DEFAULT_REFERENCE_DIR)
    if not ref_path.exists():
        return f"Error: Reference directory not found at {ref_path}"

    files = [f.name for f in ref_path.glob("*.md")]
    return "Available Reference Files/Topics:\n- " + "\n- ".join(sorted(files))


# Backwards compatibility aliases
def query_srd_logic(query: str) -> str:
    """Backwards-compatible alias for query_reference."""
    return query_reference(query)


def list_srd_topics_logic() -> str:
    """Backwards-compatible alias for list_reference_topics."""
    return list_reference_topics()
