import pdfplumber
import subprocess
import tempfile
import os
import re

# --- LOAD LISTS ---
def load_list(path):
    with open(path, encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())

def load_definitions(path):
    definitions = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "<TAB>" in line:
                term, definition = line.strip().split("<TAB>", 1)
                definitions[term.lower()] = definition.strip()
    return definitions

def load_synonyms(path):
    mapping = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "<-" in line:
                canonical, variants = line.strip().split("<-", 1)
                canonical = canonical.strip().lower()
                for variant in variants.split(","):
                    mapping[variant.strip().lower()] = canonical
    return mapping

STOPWORDS = load_list("stopwords.txt")
PHRASE_DEFS = load_definitions("phrase_definitions.txt")
WORD_DEFS = load_definitions("definitions.txt")
SYNONYMS = load_synonyms("synonyms.txt")

# --- GARBAGE FILTER (MINIMAL) ---
def is_garbage_phrase(text):
    t = text.lower().strip()
    if not t:
        return True, "empty phrase"
    if "creative commons" in t or "attribution" in t:
        return True, "license text"
    if "doi" in t or "http" in t:
        return True, "DOI/URL"
    if "@" in t:
        return True, "email"
    return False, None

# --- OCR STEP ---
def ocr_pdf(input_path):
    try:
        import fitz
        doc = fitz.open(input_path)
        if any(page.get_text("text").strip() for page in doc):
            print("\n=== OCR SKIPPED: Embedded text detected ===")
            return None
        temp_dir = tempfile.gettempdir()
        unique_name = next(tempfile._get_candidate_names())
        cleaned_path = os.path.join(temp_dir, f"ocr_{unique_name}.pdf")
        print("\n=== OCR STEP ===")
        subprocess.run(["ocrmypdf", "--force-ocr", "--deskew", "--clean", input_path, cleaned_path], check=True)
        return cleaned_path
    except Exception as e:
        print(f"OCR FAILED: {e}")
        return None

# --- MAIN EXTRACTION FUNCTION ---
def extract_pdf_layout(pdf_path, render_metadata):
    print("\n=== STARTING EXTRACTION ===")
    cleaned_pdf = ocr_pdf(pdf_path)
    target_pdf = cleaned_pdf if cleaned_pdf else pdf_path
    all_words = []
    pages_output = []

    with pdfplumber.open(target_pdf) as pdf:
        for page_index, page in enumerate(pdf.pages):
            meta = render_metadata[page_index]
            scale_x = meta["rendered_width"] / meta["pdf_width"]
            scale_y = meta["rendered_height"] / meta["pdf_height"]

            try:
                raw_words = page.extract_words(
                    use_text_flow=False,
                    keep_blank_chars=False,
                    x_tolerance=1,
                    y_tolerance=2,
                    extra_attrs=["fontname", "size"]
                ) or []
            except:
                raw_words = []

            normalized = []
            for w in raw_words:
                text = w.get("text", "")
                if not text: continue
                normalized.append({
                    "text": text,
                    "x": float(w["x0"]) * scale_x,
                    "y": float(w["top"]) * scale_y,
                    "width": float(w["x1"] - w["x0"]) * scale_x,
                    "height": float(w["bottom"] - w["top"]) * scale_y,
                    "page": page_index + 1
                })

            normalized.sort(key=lambda w: (round(w["y"] / 5), w["x"]))

            # Merge hyphenated words
            merged = []
            i = 0
            while i < len(normalized):
                current = normalized[i]
                if current["text"].endswith("-") and (i + 1) < len(normalized):
                    nxt = normalized[i + 1]
                    current["text"] = current["text"].rstrip("-") + nxt["text"]
                    merged.append(current)
                    i += 2
                else:
                    merged.append(current)
                    i += 1

            all_words.extend(merged)
            pages_output.append({
                "page_number": page_index + 1,
                "width": float(page.width),
                "height": float(page.height)
            })

    # --- PHRASE RECONSTRUCTION ---
    all_words.sort(key=lambda w: (w["page"], round(w["y"] / 5), w["x"]))
    phrases = []
    current_phrase = []

    def flush_phrase():
        nonlocal current_phrase
        if current_phrase:
            phrase_text = " ".join([w["text"] for w in current_phrase]).strip()
            phrase_text_clean = phrase_text.lower()
            rejected, reason = is_garbage_phrase(phrase_text_clean)
            if not rejected:
                phrases.append({
                    "text": phrase_text,
                    "normalized": normalize_term(phrase_text_clean),
                    "words": current_phrase.copy()
                })
            current_phrase = []

    def normalize_term(term):
        term = term.strip().lower()
        if term in STOPWORDS:
            return None
        if term in PHRASE_DEFS:
            return term
        if term in SYNONYMS:
            term = SYNONYMS[term]
        if term in WORD_DEFS:
            return term
        return term  # fallback for ontology lookup

    for w in all_words:
        raw = w["text"]
        token = raw.strip(".,;:()[]{}").replace("\u200b", "").replace("\u00ad", "").replace("\u2011", "")
        is_valid = token.isalpha() or "-" in token or token.isalnum()
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
