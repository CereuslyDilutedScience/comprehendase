import fitz  # PyMuPDF

def extract_pdf_layout(pdf_path):
    """
    Extract words with coordinates using PyMuPDF's 'words' extraction.
    This restores the original flat word list your pipeline expects.
    """

    doc = fitz.open(pdf_path)
    pages_output = []

    for page_index, page in enumerate(doc):
        raw_words = page.get_text("words")  # (text, x0, y0, x1, y1, block, line, word_no)
        words = []

        for w in raw_words:
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
# --- NEW: Rejoin hyphenated words across line breaks ---
merged_words = []
skip_next = False

for i in range(len(words)):
    if skip_next:
        skip_next = False
        continue

    current = words[i]
    text = current["text"]

    # If a word ends with a hyphen, try to merge with the next word
    if text.endswith("-") and i + 1 < len(words):
        next_word = words[i + 1]
        merged_text = text.rstrip("-") + next_word["text"]

        # Create a merged word entry
        merged_word = current.copy()
        merged_word["text"] = merged_text

        merged_words.append(merged_word)
        skip_next = True
    else:
        merged_words.append(current)

# Replace original words with merged version
words = merged_words

        
pages_output.append({
        "page_number": page_index + 1,
        "width": page.rect.width,
        "height": page.rect.height,
        "words": words
        })

doc.close()
return pages_output
