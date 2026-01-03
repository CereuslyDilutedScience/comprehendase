import pdfplumber
import subprocess
import tempfile
import os
import re

# --- FILTER CONFIGURATION ---

MONTHS = [
    "january","february","march","april","may","june",
    "july","august","september","october","november","december"
]

BAD_UNITS = ["bp", "nm", "cycles", "k-mer", "kmer", "mer"]

JOURNAL_HINTS = [
    "j vet", "diagn invest", "microbiology resource",
    "announcement", "infect immun", "plos", "bmc", "genome res"
]

WORKFLOW_HINTS = [
    "aliquot", "centrifuged", "agar", "broth", "purified",
    "addition", "times using", "three times", "g dna", "dna was"
]

BIO_HINTS = [
    "mycoplasma", "bovis", "strain", "rrna", "virulence",
    "lipoprotein", "mollicutes", "mycoplasmataceae", "pathogen",
    "mastitis", "otitis", "pneumonia", "adhesion", "invasion",
    "protein", "genome", "gene", "operon", "membrane", "surface",
    "lipid", "enzyme", "ribosomal", "subunit", "replication",
    "transcription", "translation"
]


# --- GARBAGE FILTER WITH REJECTION REASONS ---

def is_garbage_phrase(text):
    t = text.lower().strip()

    if not t:
        return True, "empty phrase"

    if len(t.split()) > 10:
        return True, "too many words (>10)"

    if "creative commons" in t or "attribution" in t:
        return True, "contains journal/license text"

    if any(j in t for j in JOURNAL_HINTS):
        return True, "contains journal name"

    if any(w in t for w in WORKFLOW_HINTS):
        return True, "contains workflow/procedure text"

    if any(m in t for m in MONTHS):
        return True, "contains month (likely citation)"

    if "doi" in t or "http" in t:
        return True, "contains DOI/URL"

    if "@" in t:
        return True, "contains email-like text"

    if re.match(r"^\d", t) and not any(b in t for b in BIO_HINTS):
        return True, "starts with number (non-biological)"

    if any(u in t for u in BAD_UNITS) and not any(b in t for b in BIO_HINTS):
        return True, "contains measurement unit"

    return False, None


# --- OCR + EXTRACTION PIPELINE ---

def ocr_pdf(input_path):
    """
    Runs OCRmyPDF on the input PDF and returns the path to the cleaned PDF.
    If OCR fails, returns None.
    """
    try:
        temp_dir = tempfile.gettempdir()
        cleaned_path = os.path.join(temp_dir, "ocr_cleaned.pdf")

        print("\n=== OCR STEP ===")
        print(f"Running OCRmyPDF on: {input_path}")
        print(f"Output will be: {cleaned_path}")

        subprocess.run(
            ["ocrmypdf", "--force-ocr", "--deskew", "--clean", input_path, cleaned_path],
            check=True
        )

        print("OCR completed successfully.")
        return cleaned_path

    except Exception as e:
        print(f"OCR FAILED: {e}")
        return None


# --- MAIN EXTRACTION FUNCTION ---

def extract_pdf_layout(pdf_path):
    print("\n==============================")
    print("=== STARTING EXTRACTION ===")
    print("==============================")

    # --- RUN OCR FIRST ---
    cleaned_pdf = ocr_pdf(pdf_path)

    if cleaned_pdf:
        print("Using OCR-cleaned PDF for extraction.")
        target_pdf = cleaned_pdf
    else:
        print("Falling back to original PDF (OCR unavailable).")
        target_pdf = pdf_path

    pages_output = []

    with pdfplumber.open(target_pdf) as pdf:
        for page_index, page in enumerate(pdf.pages):

            print(f"\n==============================")
            print(f"=== PAGE {page_index+1} START ===")
            print("==============================")

            # --- WORD EXTRACTION ---
            try:
                raw_words = page.extract_words(
                    use_text_flow=False,
                    keep_blank_chars=False,
                    x_tolerance=1,
                    y_tolerance=2,
                    extra_attrs=["fontname", "size"]
                ) or []
            except Exception as e:
                print(f"ERROR extracting words on page {page_index+1}: {e}")
                raw_words = []

            print(f"Raw word count: {len(raw_words)}")

            # --- NORMALIZE WORD STRUCTURE ---
            words = []
            for w in raw_words:
                try:
                    text = w.get("text", "")
                    x0 = w.get("x0")
                    x1 = w.get("x1")
                    top = w.get("top")
                    bottom = w.get("bottom")

                    if not text or x0 is None or x1 is None or top is None or bottom is None:
                        continue

                    words.append({
                        "text": text,
                        "x": float(x0),
                        "y": float(top),
                        "width": float(x1 - x0),
                        "height": float(bottom - top),
                        "block": 0,
                        "line": 0,
                        "word_no": 0
                    })
                except Exception as e:
                    print(f"Skipping malformed word on page {page_index+1}: {e}")
                    continue

            # --- SORT WORDS ---
            words.sort(key=lambda w: (round(w["y"] / 5), w["x"]))

            # --- DEBUG: FIRST 10 WORDS ---
            print("\nWORD DEBUG (first 10):")
            for w in words[:10]:
                print(f"  '{w['text']}' at x={w['x']:.1f}, y={w['y']:.1f}")

            # --- MERGE HYPHENATED WORDS ---
            merged_words = []
            i = 0
            while i < len(words):
                current = words[i]
                text = current["text"]

                if text.endswith("-") and (i + 1) < len(words):
                    next_word = words[i + 1]
                    merged = current.copy()
                    merged["text"] = text.rstrip("-") + next_word["text"]
                    print(f"MERGE: '{text}' + '{next_word['text']}' → '{merged['text']}'")
                    merged_words.append(merged)
                    i += 2
                else:
                    merged_words.append(current)
                    i += 1

            words = merged_words

            # --- PHRASE RECONSTRUCTION ---
            phrases = []
            current_phrase = []

            def flush_phrase():
                nonlocal current_phrase
                if current_phrase:
                    phrase_text = " ".join([w["text"] for w in current_phrase]).strip()
                    rejected, reason = is_garbage_phrase(phrase_text)

                    if rejected:
                        print(f"REJECTED: \"{phrase_text}\" — reason: {reason}")
                    else:
                        print(f"PHRASE BUILT: \"{phrase_text}\"")
                        phrases.append({
                            "text": phrase_text,
                            "words": current_phrase.copy()
                        })

                    current_phrase = []

            for w in words:
                raw = w["text"]
                token = raw.strip().strip(".,;:()[]{}")
                token = token.replace("\u200b", "").replace("\u00ad", "").replace("\u2011", "")

                is_valid = (
                    token.isalpha() or
                    "-" in token or
                    token.isalnum()
                )

                if is_valid:
                    if not current_phrase:
                        current_phrase = [w]
                    else:
                        prev = current_phrase[-1]
                        same_line = abs(prev["y"] - w["y"]) < 8
                        horizontal_gap = w["x"] - (prev["x"] + prev["width"])
                        adjacent = -3 <= horizontal_gap < 60

                        if same_line and adjacent:
                            current_phrase.append(w)
                        else:
                            flush_phrase()
                            current_phrase = [w]
                else:
                    flush_phrase()

            flush_phrase()

            print(f"\nTotal words after merge: {len(words)}")
            print(f"Total phrases: {len(phrases)}")

            # --- CANDIDATE TERM DEBUG (GROUPED BY SOURCE) ---
            print(f"\n=== CANDIDATE TERMS (page {page_index+1}) ===")

            # From words
            word_terms = sorted({w["text"].lower() for w in words if w["text"].isalpha()})
            print("From words:")
            for t in word_terms:
                print(f"  {t}")

            # From phrases
            phrase_terms = sorted({p["text"].lower() for p in phrases})
            print("\nFrom phrases:")
            for t in phrase_terms:
                print(f"  {t}")

            # --- OUTPUT STRUCTURE ---
            pages_output.append({
                "page_number": page_index + 1,
                "width": float(page.width) if page.width else 0.0,
                "height": float(page.height) if page.height else 0.0,
                "words": words,
                "phrases": phrases
            })

            print(f"=== PAGE {page_index+1} END ===\n")

    return pages_output
