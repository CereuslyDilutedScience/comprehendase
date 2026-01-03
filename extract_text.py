import pdfplumber
import math
import re
import os 
import sys
# --- FILTER CONFIGURATION ---

MONTHS = [
    "january","february","march","april","may","june",
    "july","august","september","october","november","december"
]

BAD_UNITS = ["bp", "nm", "cycles", "k-mer", "kmer", "mer"]

BAD_PATTERNS = [
    r"\bdoi\b",
    r"http[s]?:\/\/",
    r"\b\d{1,2}[:\/]\d{1,2}\b",
    r"\b[eE]\d{2,4}\b",
    r"\b[A-Z]{2,}\d{2,}\b",
]

JOURNAL_HINTS = [
    "j vet", "diagn invest", "microbiology resource",
    "announcement", "infect immun", "plos", "bmc", "genome res"
]

WORKFLOW_HINTS = [
    "aliquot", "centrifuged", "agar", "broth", "purified",
    "addition", "times using", "three times", "g dna", "dna was"
]

PLATFORM_HINTS = [
    "truseq", "smrtbell", "pacbio", "hiseq", "abyss", "canu", "gapcloser"
]

BIO_HINTS = [
    "mycoplasma", "bovis", "strain", "rrna", "virulence",
    "lipoprotein", "mollicutes", "mycoplasmataceae", "pathogen",
    "mastitis", "otitis", "pneumonia", "adhesion", "invasion",
    "protein", "genome", "gene", "operon", "membrane", "surface",
    "lipid", "enzyme", "ribosomal", "subunit", "replication",
    "transcription", "translation"
]


# --- CORRECTED GARBAGE FILTER (BIOLOGICALLY SAFE) ---

def is_garbage_phrase(text):
    t = text.lower().strip()

    if not t:
        return True

    # Allow up to 10 words (scientific terms can be long)
    if len(t.split()) > 10:
        return True

    # Reject Creative Commons / license text
    if "creative commons" in t or "attribution" in t:
        return True

    # Reject journal names
    if any(j in t for j in JOURNAL_HINTS):
        return True

    # Reject workflow/procedure phrases
    if any(w in t for w in WORKFLOW_HINTS):
        return True

    # Reject months (citations)
    if any(m in t for m in MONTHS):
        return True

    # Reject DOI/URL
    if "doi" in t or "http" in t:
        return True

    # Reject email-like
    if "@" in t:
        return True

    # Reject leading number ONLY if the phrase is not biological
    if re.match(r"^\d", t) and not any(b in t for b in BIO_HINTS):
        return True

    # Reject units (but allow biological context)
    if any(u in t for u in BAD_UNITS) and not any(b in t for b in BIO_HINTS):
        return True

    # DO NOT reject punctuation — biological terms often contain punctuation
    # (parentheses, hyphens, commas, etc.)

    return False


# --- MAIN EXTRACTION FUNCTION ---

def extract_pdf_layout(pdf_path):
    pages_output = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):

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

            print(f"\n=== PAGE {page_index+1} ===")
            print("Raw word count:", len(raw_words))

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

                    if not is_garbage_phrase(phrase_text):
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
                        same_line = abs(prev["y"] - w["y"]) < 5
                        horizontal_gap = w["x"] - (prev["x"] + prev["width"])
                        adjacent = -3 <= horizontal_gap < 40

                        if same_line and adjacent:
                            current_phrase.append(w)
                        else:
                            flush_phrase()
                            current_phrase = [w]
                else:
                    flush_phrase()

            flush_phrase()

            # --- DEBUG OUTPUT ---
            print("Total words:", len(words))
            print("Total phrases:", len(phrases))
            print("Key phrases containing targets:")
            for p in phrases:
                if any(k in p["text"].lower() for k in [
                    "otitis", "media", "mycoplasma", "bovis", "xby01", "strain", "gene"
                ]):
                    print("  PHRASE:", p["text"])

            # --- OUTPUT STRUCTURE ---
            pages_output.append({
                "page_number": page_index + 1,
                "width": float(page.width) if page.width else 0.0,
                "height": float(page.height) if page.height else 0.0,
                "words": words,
                "phrases": phrases
            })

    return pages_output
