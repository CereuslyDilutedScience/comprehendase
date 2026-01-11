import pdfplumber
import subprocess
import tempfile
import os
import re

from debug_tools import DEBUG  # Debug collector


# --- LOAD LISTS ---
def load_list(path):
    with open(path, encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())


STOPWORDS = load_list("stopwords.txt")


# --- GARBAGE FILTER (KEPT EXACTLY AS IS) ---
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
            DEBUG.add_flow("ocr_skipped_embedded_text")
            return None

        temp_dir = tempfile.gettempdir()
        unique_name = next(tempfile._get_candidate_names())
        cleaned_path = os.path.join(temp_dir, f"ocr_{unique_name}.pdf")
        print("\n=== OCR STEP ===")
        DEBUG.add_flow("ocr_triggered")

        subprocess.run(
            ["ocrmypdf", "--force-ocr", "--deskew", "--clean", input_path, cleaned_path],
            check=True
        )
        return cleaned_path
    except Exception as e:
        print(f"OCR FAILED: {e}")
        DEBUG.add_flow(f"ocr_failed:{e}")
        return None


# --- ANOMALY HELPERS ---
def detect_duplicate_coordinates(all_words):
    """
    Detect words that share identical page + bounding box coordinates.
    """
    seen = {}
    for w in all_words:
        key = (
            w.get("page"),
            round(w.get("x", 0), 2),
            round(w.get("y", 0), 2),
            round(w.get("width", 0), 2),
            round(w.get("height", 0), 2),
        )
        if key in seen:
            sample = {
                "page": key[0],
                "x": key[1],
                "y": key[2],
                "width": key[3],
                "height": key[4],
                "text_1": seen[key].get("text"),
                "text_2": w.get("text"),
            }
            DEBUG.add_anomaly("duplicate_coordinates", sample)
        else:
            seen[key] = w


def detect_duplicate_text_spans(all_words):
    """
    Detect repeated text spans on the same page.
    """
    seen = {}
    for w in all_words:
        key = (w.get("page"), w.get("text", "").strip())
        if not key[1]:
            continue
        if key in seen:
            sample = {
                "page": key[0],
                "text": key[1],
                "first_coords": {
                    "x": seen[key].get("x"),
                    "y": seen[key].get("y"),
                },
                "second_coords": {
                    "x": w.get("x"),
                    "y": w.get("y"),
                },
            }
            DEBUG.add_anomaly("duplicate_text_spans", sample)
        else:
            seen[key] = w


def boxes_overlap(a, b):
    """
    Simple rectangle overlap check for bounding boxes on the same page.
    """
    ax1 = a.get("x", 0)
    ay1 = a.get("y", 0)
    ax2 = ax1 + a.get("width", 0)
    ay2 = ay1 + a.get("height", 0)

    bx1 = b.get("x", 0)
    by1 = b.get("y", 0)
    bx2 = bx1 + b.get("width", 0)
    by2 = by1 + b.get("height", 0)

    # No overlap if one is completely to one side of the other
    if ax2 <= bx1 or bx2 <= ax1:
        return False
    if ay2 <= by1 or by2 <= ay1:
        return False
    return True


def detect_overlapping_boxes(all_words, max_checks=1000):
    """
    Detect overlapping bounding boxes on the same page.
    To avoid heavy computation, we cap the number of pairwise checks.
    """
    by_page = {}
    for w in all_words:
        page = w.get("page")
        by_page.setdefault(page, []).append(w)

    checks = 0
    for page, words in by_page.items():
        n = len(words)
        for i in range(n):
            for j in range(i + 1, n):
                if checks >= max_checks:
                    return
                checks += 1

                a = words[i]
                b = words[j]
                if boxes_overlap(a, b):
                    sample = {
                        "page": page,
                        "word_1": {
                            "text": a.get("text"),
                            "x": a.get("x"),
                            "y": a.get("y"),
                            "width": a.get("width"),
                            "height": a.get("height"),
                        },
                        "word_2": {
                            "text": b.get("text"),
                            "x": b.get("x"),
                            "y": b.get("y"),
                            "width": b.get("width"),
                            "height": b.get("height"),
                        },
                    }
                    DEBUG.add_anomaly("overlapping_boxes", sample)


# --- MAIN EXTRACTION FUNCTION ---
def extract_pdf_layout(pdf_path, render_metadata):
    print("\n=== STARTING EXTRACTION ===")
    DEBUG.add_flow("extraction_started")
    DEBUG.add_flow("render_metadata_received")

    cleaned_pdf = ocr_pdf(pdf_path)
    target_pdf = cleaned_pdf if cleaned_pdf else pdf_path

    if cleaned_pdf:
        DEBUG.add_flow("using_ocr_cleaned_pdf")
    else:
        DEBUG.add_flow("using_original_pdf_no_ocr")

    all_words = []
    pages_output = []

    # --- EXTRACT WORDS ---
    DEBUG.add_flow("pdfplumber_extraction_started")
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
            except Exception:
                raw_words = []

            normalized = []
            for w in raw_words:
                text = w.get("text", "")
                if not text:
                    continue
                normalized.append({
                    "text": text,
                    "x": float(w["x0"]) * scale_x,
                    "y": float(w["top"]) * scale_y,
                    "width": float(w["x1"] - w["x0"]) * scale_x,
                    "height": float(w["bottom"] - w["top"]) * scale_y,
                    "page": page_index + 1
                })

            # Sort by reading order
            normalized.sort(key=lambda w: (round(w["y"] / 5), w["x"]))

            # --- KEEP HYPHEN MERGING EXACTLY AS IS ---
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

    DEBUG.add_flow("pdfplumber_extraction_completed")

    # Sample page-level metadata as "boxes" (complements server samples)
    for page_info in pages_output[:5]:
        DEBUG.add_sample("boxes", page_info)

    # --- SORT ALL WORDS GLOBALLY ---
    all_words.sort(key=lambda w: (w["page"], round(w["y"] / 5), w["x"]))

    # ============================================================
    # ⭐ PURE GREEDY STOPWORD-BOUNDED EXTRACTION (NO MAX LENGTH)
    # ============================================================

    phrases = []
    n = len(all_words)
    i = 0

    while i < n:
        w = all_words[i]
        raw = w["text"]

        # Clean token for stopword check
        token = raw.lower().strip(".,;:()[]{}")

        # Skip stopwords entirely
        if token in STOPWORDS:
            i += 1
            continue

        # Start a new greedy phrase
        phrase_words = [w]
        j = i + 1

        # Expand right until a stopword
        while j < n:
            nxt_raw = all_words[j]["text"]
            nxt_token = nxt_raw.lower().strip(".,;:()[]{}")

            if nxt_token in STOPWORDS:
                break  # stop expansion

            phrase_words.append(all_words[j])
            j += 1

        # Emit phrase (even if length 1)
        phrase_text = " ".join([pw["text"] for pw in phrase_words]).strip()
        phrase_text_clean = phrase_text.lower()

        rejected, reason = is_garbage_phrase(phrase_text_clean)
        if rejected and reason == "empty phrase":
            # Track unexpected empty phrases as anomalies
            DEBUG.add_anomaly("empty_phrases", {
                "reason": reason,
                "raw_text": phrase_text,
                "first_word": w.get("text"),
                "page": w.get("page"),
            })

        if not rejected:
            phrases.append({
                "text": phrase_text,
                "words": phrase_words.copy()
            })

        # Move index to next word after phrase
        i = j

    DEBUG.add_flow("phrase_extraction_completed")

    # --- ANOMALY DETECTION ON WORDS ---
    detect_duplicate_coordinates(all_words)
    detect_duplicate_text_spans(all_words)
    detect_overlapping_boxes(all_words)
    DEBUG.add_flow("anomaly_detection_completed")

    return target_pdf, {
        "pages": pages_output,
        "words": all_words,
        "phrases": phrases
    }
