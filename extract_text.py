import fitz  # PyMuPDF

def extract_pdf_layout(pdf_path):
    """
    Extract words with coordinates AND font metadata (bold, italic, font, size)
    using PyMuPDF's 'dict' text extraction.
    """

    doc = fitz.open(pdf_path)
    pages_output = []

    for page_index, page in enumerate(doc):
        page_dict = page.get_text("dict")  # full structured text
        words = []

        for block in page_dict.get("blocks", []):
            if block["type"] != 0:  # skip images, drawings, etc.
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue

                    x0, y0, x1, y1 = span["bbox"]

                    flags = span.get("flags", 0)
                    is_italic = bool(flags & 1)
                    is_bold = bool(flags & 2)

                    words.append({
                        "text": text,
                        "x": float(x0),
                        "y": float(y0),
                        "width": float(x1 - x0),
                        "height": float(y1 - y0),

                        # NEW metadata
                        "font": span.get("font", None),
                        "font_size": span.get("size", None),
                        "bold": is_bold,
                        "italic": is_italic,

                        # Keep block/line info for consistency
                        "block": block.get("number", None),
                        "line": line.get("number", None),
                    })

        pages_output.append({
            "page_number": page_index + 1,
            "width": page.rect.width,
            "height": page.rect.height,
            "words": words
        })

    doc.close()
    return pages_output
