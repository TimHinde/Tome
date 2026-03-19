import fitz  # PyMuPDF
import os

def analyze_pdf_structure(pdf_path: str) -> str:
    """
    Opens the specified PDF file and extracts its Table of Contents.
    Heuristically guesses the 'Document Type' based on the TOC.
    Returns a formatted Markdown summary.
    """
    if not os.path.exists(pdf_path):
        return f"Error: File not found at {pdf_path}"

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return f"Error opening PDF: {e}"

    toc = doc.get_toc()
    if not toc:
        return "No Table of Contents found in this PDF."

    # Heuristic guessing
    toc_lower = str(toc).lower()
    doc_type = "Unknown"

    player_option_kw = any(kw in toc_lower for kw in ["race", "class", "spell", "background", "feat", "subclass"])
    setting_kw = any(kw in toc_lower for kw in ["religion", "deity", "lore", "world", "setting", "region", "history", "pantheon"])
    adventure_kw = any(kw in toc_lower for kw in ["encounter", "adventure", "quest", "campaign"])
    
    if player_option_kw and setting_kw:
        doc_type = "Campaign Setting"
    elif player_option_kw and not setting_kw and not adventure_kw:
        doc_type = "Supplement"
    elif ("chapter" in toc_lower or "part" in toc_lower) and adventure_kw:
        doc_type = "Adventure"
    elif "class" in toc_lower and "spell" in toc_lower and "combat" in toc_lower:
        doc_type = "Rulebook"
    elif "monster" in toc_lower or "bestiary" in toc_lower or "creature" in toc_lower:
        doc_type = "Bestiary"

    # Build markdown output
    output = f"## PDF Analysis: {os.path.basename(pdf_path)}\n"
    output += f"**Predicted Document Type:** {doc_type}\n\n"
    output += "### Table of Contents\n"
    
    for item in toc:
        level, title, page = item
        indent = "  " * (level - 1)
        output += f"{indent}- {title} (Page {page})\n"

    return output

def extract_pdf_section(pdf_path: str, start_page: int, end_page: int) -> str:
    """
    Extracts all text from the specified page range (1-indexed).
    """
    if not os.path.exists(pdf_path):
        return f"Error: File not found at {pdf_path}"

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return f"Error opening PDF: {e}"

    total_pages = len(doc)
    
    # Constrain to valid ranges
    actual_start = max(1, start_page)
    actual_end = min(total_pages, end_page)
    
    if actual_start > actual_end:
        return f"Error: Invalid page range. Start ({actual_start}) is greater than end ({actual_end})."

    extracted_text = []
    # fitz uses 0-indexed pages
    for page_num in range(actual_start - 1, actual_end):
        page = doc.load_page(page_num)
        text = page.get_text()
        extracted_text.append(f"--- Page {page_num + 1} ---\n{text}")

    return "\n".join(extracted_text)


def suggest_chunks(pdf_path: str) -> list:
    """
    Analyze PDF TOC and suggest logical page-range chunks for extraction.
    Returns a list of dicts with name, start_page, end_page for each chunk.
    Uses the TOC to find chapter/section boundaries.
    """
    if not os.path.exists(pdf_path):
        return [{"error": f"File not found at {pdf_path}"}]

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return [{"error": f"Error opening PDF: {e}"}]

    toc = doc.get_toc()
    total_pages = len(doc)

    if not toc:
        # No TOC — suggest the whole document in one chunk
        return [{"name": "Full Document", "start_page": 1, "end_page": total_pages}]

    # Only use top-level TOC entries (level 1) for chunking
    top_level = [(title, page) for level, title, page in toc if level == 1]

    if not top_level:
        # Fall back to all TOC entries
        top_level = [(title, page) for level, title, page in toc]

    chunks = []
    for i, (title, start_page) in enumerate(top_level):
        if i + 1 < len(top_level):
            end_page = top_level[i + 1][1] - 1
        else:
            end_page = total_pages
        
        # Skip very small chunks (likely title pages or single-page sections)
        if end_page >= start_page:
            chunks.append({
                "name": title.strip(),
                "start_page": start_page,
                "end_page": end_page
            })

    return chunks

