import os
from pdf_tools import analyze_pdf_structure, extract_pdf_section

def test_pdf_parsing():
    pdf_path = "references/SRD/SRD_CC_v5.2.pdf"
    # pdf_path = "LastOwlbear/Last-Owlbear.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    print("--- Testing PDF Analysis ---")
    analysis = analyze_pdf_structure(pdf_path)
    print(analysis)
    
    print("\n--- Testing Text Extraction (Pages 1-3) ---")
    text = extract_pdf_section(pdf_path, 1, 3)
    # Print the first 500 characters to avoid flooding the console
    print(text[:500] + "\n...[truncated]...")

if __name__ == "__main__":
    test_pdf_parsing()
