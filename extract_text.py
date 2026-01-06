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


# --- GARBAGE FILTER ---

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


# --- OCR STEP (ONLY RUN IF NEEDED) ---

def ocr_pdf(input_path):
    """
    Run OCR *only* if the PDF has no embedded text.
    Returns:
        - cleaned OCR PDF path if OCR was needed
        - None if OCR was skipped
    """
    try:
        import fitz  # PyMuPDF

        # Check if ANY page has embedded text
        doc = fitz.open(input_path)
        has_text = False
        for page in doc:
            if page.get_text("text").strip():
                has_text = True
                break

        if has_text:
            print("\n=== OCR SKIPPED: Embedded text detected ===")
            return None

        # Otherwise run OCR
        temp_dir = tempfile.gettempdir()
        unique_name = next(tempfile._get_candidate_names())
        cleaned_path = os.path.join(temp_dir, f"ocr_{unique_name}.pdf")

        print("\n=== OCR STEP ===")
        print(f"No embedded text found. Running OCRmyPDF on: {input_path}")
        print(f"OCR output: {cleaned_path}")

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

    # Only OCR if needed
    cleaned_pdf = ocr_pdf(pdf_path)
    target_pdf = cleaned_pdf if cleaned_pdf else pdf_path

    all_words = []      # GLOBAL list of all words across all pages
    pages_output = []   # Page metadata only

    with pdfplumber.open(target_pdf) as pdf:
        for page_index, page in enumerate(pdf.pages):

            print(f"\n=== PAGE {page_index+1} START ===")

            # --- Try embedded text extraction first ---
            try:
                raw_words = page.extract_words(
                    use_text_flow=False,
                    keep_blank_chars=False,
                    x_tolerance=1,
                    y_tolerance=2,
                    extra_attrs=["fontname", "size"]
                ) or []
            except Exception as e:
                print(f"ERROR extracting words: {e}")
                raw_words = []

            normalized = []
            for w in raw_words:
                try:
                    text = w.get("text", "")
                    x0 = w.get("x0")
                    x1 = w.get("x1")
                    top = w.get("top")
                    bottom = w.get("bottom")

                    if not text or x0 is None or x1 is None or top is None or bottom is None:
                        continue

                    normalized.append({
                        "text": text,
                        "x": float(x0),
                        "y": float(page.height - bottom),   # FIX: convert to top-left origin
                        "width": float(x1 - x0),
                        "height": float(bottom - top),
                        "page": page_index + 1
                    })

                except:
                    continue

            # Sort words on this page
            normalized.sort(key=lambda w: (round(w["y"] / 5), w["x"]))

            # Merge hyphenated words
            merged = []
            i = 0
            while i < len(normalized):
                current = normalized[i]
                text = current["text"]

                if text.endswith("-") and (i + 1) < len(normalized):
                    nxt = normalized[i + 1]
                    merged_word = current.copy()
                    merged_word["text"] = text.rstrip("-") + nxt["text"]
                    merged.append(merged_word)
                    i += 2
                else:
                    merged.append(current)
                    i += 1

            # Add to GLOBAL list
            all_words.extend(merged)

            pages_output.append({
                "page_number": page_index + 1,
                "width": float(page.width),
                "height": float(page.height)
            })

            print(f"=== PAGE {page_index+1} END ===")


    # --- GLOBAL PHRASE RECONSTRUCTION ---
    all_words.sort(key=lambda w: (w["page"], round(w["y"] / 5), w["x"]))

    phrases = []
    current_phrase = []

    def flush_phrase():
        nonlocal current_phrase
        if current_phrase:
            phrase_text = " ".join([w["text"] for w in current_phrase]).strip()
            rejected, reason = is_garbage_phrase(phrase_text)

            if not rejected:
                phrases.append({
                    "text": phrase_text,
                    "words": current_phrase.copy()
                })

            current_phrase = []

    for w in all_words:
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
                same_line = (w["page"] == prev["page"]) and abs(prev["y"] - w["y"]) < 8
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

    return target_pdf, {
        "pages": pages_output,
        "words": all_words,
        "phrases": phrases
    }

