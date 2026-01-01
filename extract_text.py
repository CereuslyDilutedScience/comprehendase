import fitz  # PyMuPDF

def extract_pdf_layout(pdf_path):
    """
    Extract words with coordinates using PyMuPDF's 'words' extraction.
    Adds a phrase reconstruction step so downstream layers receive
    multi-word scientific terms BEFORE filtering or ontology lookup.
    """

    doc = fitz.open(pdf_path)
    pages_output = []

    for page_index, page in enumerate(doc):
        raw_words = page.get_text("words")  # (x0, y0, x1, y1, text, block, line, word_no)
        words = []

        # --- STEP 1: Build clean word objects ---
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

        # --- STEP 2: Merge hyphenated words across line breaks ---
        merged_words = []
        skip_next = False

        for i in range(len(words)):
            if skip_next:
                skip_next = False
                continue

            current = words[i]
            text = current["text"]

            if text.endswith("-") and i + 1 < len(words):
                next_word = words[i + 1]
                merged_text = text.rstrip("-") + next_word["text"]

                merged_word = current.copy()
                merged_word["text"] = merged_text

                merged_words.append(merged_word)
                skip_next = True
            else:
                merged_words.append(current)

        words = merged_words

        # --- STEP 3: Phrase reconstruction (UPDATED adjacency logic) ---
        phrases = []
        current_phrase = []

        def flush_phrase():
            """Push current phrase into list if valid."""
            if len(current_phrase) > 0:
                phrase_text = " ".join([w["text"] for w in current_phrase])
                phrases.append({
                    "text": phrase_text,
                    "words": current_phrase.copy()
                })

        for i, w in enumerate(words):
            token = w["text"]

            # Basic noun-phrase heuristics:
            # - alphabetic or hyphenated
            # - not punctuation
            # - not starting with a digit
            # - adjacent words on same line/block
            if token.isalpha() or "-" in token:
                if not current_phrase:
                    current_phrase = [w]
                else:
                    prev = current_phrase[-1]
                    same_line = (prev["line"] == w["line"])

                    # --- UPDATED: allow small gaps in word_no (1–2) ---
                    gap = w["word_no"] - prev["word_no"]
                    adjacent = (1 <= gap <= 2)

                    if same_line and adjacent:
                        current_phrase.append(w)
                    else:
                        flush_phrase()
                        current_phrase = [w]
            else:
                flush_phrase()
                current_phrase = []

        flush_phrase()

        # --- STEP 4: Save page output ---
        pages_output.append({
            "page_number": page_index + 1,
            "width": page.rect.width,
            "height": page.rect.height,
            "words": words,
            "phrases": phrases  # NEW
        })

    doc.close()
    return pages_output
