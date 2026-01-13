import requests
import re
import os

# ---------------------------------------------------------
# NORMALIZATION (for dedupe only)
# ---------------------------------------------------------

def normalize_term(t: str) -> str:
    # lowercase + trim
    t = t.lower().strip()
    # remove ONLY basic punctuation: commas, periods, semicolons, colons, quotes
    t = re.sub(r"[.,;:!?\"']", "", t)
    # collapse whitespace
    t = re.sub(r"\s+", " ", t)
    
    return t

# ---------------------------------------------------------
# OLS4 CONFIG
# ---------------------------------------------------------

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
MAX_TERMS_PER_DOCUMENT = 100000
MAX_OLS4_LOOKUPS = 100000

# ---------------------------------------------------------
# OLS4 LOOKUP (supports batching)
# ---------------------------------------------------------

def lookup_terms_ols4(terms):
    """
    Accepts a list of terms and performs a single batched OLS4 search.
    Returns a dict: term -> best match or None.
    """

    results = {t: None for t in terms}

    if not terms:
        return results

    params = [("q", t) for t in terms]

    try:
        r = requests.get(OLS4_SEARCH_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        for item in data.get("response", {}).get("docs", []):
            label = item.get("label")
            defs = item.get("description")
            definition = defs[0] if isinstance(defs, list) and defs else defs
            iri = item.get("iri", "")

            if not definition:
                continue

            key = label.lower().strip()
            if key in results:
                results[key] = {
                    "label": label,
                    "definition": definition,
                    "iri": iri
                }

        return results

    except Exception:
        return results

# ---------------------------------------------------------
# MAIN ENTRYPOINT — PHASE 1 PIPELINE (OLS4 VERSION)
# ---------------------------------------------------------

def extract_ontology_terms(extracted):
    phrases = extracted.get("phrases", [])

    results = {}
    unmatched_terms = []

    # ---------------------------------------------
    # STEP 1 — BUCKET BY LENGTH
    # ---------------------------------------------
    one_word_spans = []
    two_word_spans = []
    multi_word_spans = []

    for p in phrases:
        text = p.get("text", "").strip()
        words_meta = p.get("words") or []
        if not text:
            continue

        length = len(words_meta) if words_meta else len(text.split())

        if length == 1:
            one_word_spans.append(p)
        elif length == 2:
            two_word_spans.append(p)
        else:
            multi_word_spans.append(p)

    # ---------------------------------------------
    # STEP 2 — TRUE BATCH FOR 2-WORD PHRASES
    # ---------------------------------------------
    two_word_texts = [p["text"].strip() for p in two_word_spans]

    if two_word_texts and ols4_lookups < MAX_OLS4_LOOKUPS:
        batch = lookup_terms_ols4(two_word_texts)
        ols4_lookups += 1
    else:
        batch = {t.lower(): None for t in two_word_texts}

    for p in two_word_spans:
        phrase_text = p["text"].strip()
        bp = batch.get(phrase_text.lower())

        if bp:
            results[phrase_text] = {
                "source": "ontology_phrase",
                "definition": bp["definition"],
                "iri": bp.get("iri", ""),
                "highlight_as_phrase": True
            }
            continue

        # fallback → split into 1-word terms
        words_meta = p.get("words") or []
        split_words = [w["text"].strip() for w in words_meta] if words_meta else phrase_text.split()
        one_word_terms.extend(split_words)

    # ---------------------------------------------
    # STEP 3 — TRUE BATCH FOR 3+ WORD PHRASES
    # ---------------------------------------------
    multi_word_texts = [p["text"].strip() for p in multi_word_spans]

    if multi_word_texts and ols4_lookups < MAX_OLS4_LOOKUPS:
        batch = lookup_terms_ols4(multi_word_texts)
        ols4_lookups += 1
    else:
        batch = {t.lower(): None for t in multi_word_texts}

    for p in multi_word_spans:
        phrase_text = p["text"].strip()
        bp = batch.get(phrase_text.lower())

        if bp:
            results[phrase_text] = {
                "source": "ontology_phrase",
                "definition": bp["definition"],
                "iri": bp.get("iri", ""),
                "highlight_as_phrase": True
            }
            continue

        unmatched_terms.append(phrase_text)


    # ---------------------------------------------
    # STEP 4 — PROCESS 1-WORD TERMS (LAST)
    # ---------------------------------------------

    norm_to_originals = {}
    for w in one_word_terms:
        norm = normalize_term(w)
        if not norm:
            continue

        # preserve ALL occurrences
        norm_to_originals.setdefault(norm, []).append(w)


    all_norms = list(norm_to_originals.keys())
    if len(all_norms) > MAX_TERMS_PER_DOCUMENT:
        all_norms = all_norms[:MAX_TERMS_PER_DOCUMENT]

    if ols4_lookups < MAX_OLS4_LOOKUPS:
        batch = lookup_terms_ols4(all_norms)
        ols4_lookups += 1
    else:
        batch = {n: None for n in all_norms}

    for norm in all_norms:
        originals = sorted(norm_to_originals[norm])
        rep = originals[0]
        bp = batch.get(norm)
        if bp:
            for word in originals:
                results[word] = {
                    "source": "ontology_word",
                    "definition": bp["definition"],
                    "iri": bp.get("iri", "")
                }
            continue

        for word in originals:
            unmatched_terms.append(word)

    results["_unmatched"] = unmatched_terms
    return results
