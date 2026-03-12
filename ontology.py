import requests
import re
import os


# NORMALIZATION (for dedupe only)
def normalize_term(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[.,;:!?\"']", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

def chunk_list(lst, size):
    """
    Yields successive chunks of the given list with at most `size` elements. Utilities to parse lookup
    OLS4 max 500 words per batch, though much more restrictive when phrases are introduced. 
    """
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

# OLS4 CONFIG
OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"


def lookup_terms_ols4(terms):
    """
    Accepts a list of terms and performs a single batched OLS4 search.
    Returns a dict: lowercase term -> best match or None.
    """

    results = {t.lower().strip(): None for t in terms}

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

def extract_ontology_terms(extracted):
    """
    Phase 1 of pipeline, returns extracted_text output and sorts terms based on length.
    """
    phrases = extracted.get("phrases", [])

    results = {}
    unmatched_terms = []

    #binned by length
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

   
    # TRUE BATCH FOR 2-WORD PHRASES (CHUNKED)
    two_word_texts = [p["text"].strip() for p in two_word_spans]

    if two_word_texts:
        combined_batch = {}
        for chunk in chunk_list(two_word_texts, 20):
            chunk_batch = lookup_terms_ols4(chunk)
            combined_batch.update(chunk_batch)
    else:
        combined_batch = {}

    for p in two_word_spans:
        phrase_text = p["text"].strip()
        bp = combined_batch.get(phrase_text.lower())

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

        for w in split_words:
            one_word_spans.append({"text": w})

    # TRUE BATCH FOR 3+ WORD PHRASES (CHUNKED) INCOMPLETE, WILL BE ADDING PHRASE DELIMINTATING LOOKUP ONCE SITE IS STABLE
    multi_word_texts = [p["text"].strip() for p in multi_word_spans]

    if multi_word_texts:
        combined_batch = {}
        for chunk in chunk_list(multi_word_texts, 20):
            chunk_batch = lookup_terms_ols4(chunk)
            combined_batch.update(chunk_batch)
    else:
        combined_batch = {}

    for p in multi_word_spans:
        phrase_text = p["text"].strip()
        bp = combined_batch.get(phrase_text.lower())

        if bp:
            results[phrase_text] = {
                "source": "ontology_phrase",
                "definition": bp["definition"],
                "iri": bp.get("iri", ""),
                "highlight_as_phrase": True
            }
            continue

        unmatched_terms.append(phrase_text)

    # PROCESS 1-WORD TERMS (LAST, CHUNKED)
    norm_to_originals = {}

    for p in one_word_spans:
        w = p["text"].strip()
        norm = normalize_term(w)
        if not norm:
            continue

        norm_to_originals.setdefault(norm, []).append(w)

    all_norms = list(norm_to_originals.keys())

    if all_norms:
        combined_batch = {}
        for chunk in chunk_list(all_norms, 20):
            chunk_batch = lookup_terms_ols4(chunk)
            combined_batch.update(chunk_batch)
    else:
        combined_batch = {}

    for norm in all_norms:
        originals = sorted(norm_to_originals[norm])
        bp = combined_batch.get(norm)

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
