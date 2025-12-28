import fitz  # PyMuPDF

def extract_pdf_layout(pdf_path):
    """
    Extract words with coordinates using PyMuPDF's 'words' extraction.
    This restores the original flat word list your pipeline expects.
    """

    doc = fitz.open(pdf_path)
    pages_output = []

    for page_index, page in enumerate(doc):
        raw_words = page.get_text("words")  # (text, x0, y0, x1, y1, block_no, line_no, word_no)
        words = []

        for w in words_raw:
            x0, y0, x1, y1, text, block, line, word_no = w

            words.append({
                "text": text,
                "x": float(x0),
                "y": float(y0),
                "width": float(x1 - x0),
                "height": float(y1 - y0),
                "block": int(block),
                "line": int(line),
                "word_no": int(word_no)
            })

        pages_output.append({
            "page_number": page_index + 1,
            "width": page.rect.width,
            "height": page.rect.height,
            "words": words
        })

    doc.close()
    return pages_output
