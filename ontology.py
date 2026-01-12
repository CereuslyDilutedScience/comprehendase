import requests
import re
import os

# ---------------------------------------------------------
# LOAD LISTS
# ---------------------------------------------------------

def load_definitions(path):
    defs = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "<TAB>" in line:
                term, definition = line.strip().split("<TAB>", 1)
                defs[term.lower()] = definition.strip()
    return defs

PHRASE_DEFS = load_definitions("phrase_definitions.txt")
WORD_DEFS = load_definitions("word_definitions.txt")

# ---------------------------------------------------------
# NORMALIZATION (for dedupe only)
# ---------------------------------------------------------

def normalize_term(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9\- ]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

# ---------------------------------------------------------
# OLS4 CONFIG
# ---------------------------------------------------------

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
MAX_TERMS_PER_DOCUMENT = 1000
MAX_OLS4_LOOKUPS = 1000

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

    # OLS4 supports multiple q parameters: ?q=term1&q=term2&q=term3
    params = [("q", t) for t in terms]

    try:
        r = requests.get(OLS4_SEARCH_URL, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()

        # OLS4 returns a flat list of hits for ALL queries combined
        for item in data.get("response", {}).get("docs", []):
            label = item.get("label")
            defs = item.get("description")
            definition = defs[0] if isinstance(defs, list) and defs else defs
            iri = item.get("iri", "")

            if not label or not definition:
                continue

            # OLS4 returns exact matches only if the ontology contains the term
            # So we match by exact label lowercased
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
# INTERNAL LOOKUP HELPERS
# ---------------------------------------------------------

def lookup_internal_phrase(phrase: str):
    return PHRASE_DEFS.get(phrase.lower().strip())

def lookup_internal_word(word: str):
    return WORD_DEFS.get(word.lower().strip())

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

    one_word_terms = [p["text"].strip() for p in one_word_spans if p.get("text")]

    ols4_lookups = 0

    # ---------------------------------------------
    # STEP 2 — PROCESS 2-WORD PHRASES
    # ---------------------------------------------
    for p in two_word_spans:
        phrase_text = p["text"].strip()

        hit = lookup_internal_phrase(phrase_text)
        if hit:
            results[phrase_text] = {
                "source": "phrase_definition",
                "definition": hit
            }
            continue

        if ols4_lookups < MAX_OLS4_LOOKUPS:
            batch = lookup_terms_ols4([phrase_text])
            ols4_lookups += 1
            bp = batch.get(phrase_text.lower())
        else:
            bp = None

        if bp:
            results[phrase_text] = {
                "source": "ontology_phrase",
                "definition": bp["definition"],
                "iri": bp.get("iri", "")
            }
            continue

        # fallback → split into 1-word terms
        words_meta = p.get("words") or []
        split_words = [w["text"].strip() for w in words_meta] if words_meta else phrase_text.split()
        one_word_terms.extend(split_words)

    # ---------------------------------------------
    # STEP 3 — PROCESS 3+ WORD PHRASES
    # ---------------------------------------------
    for p in multi_word_spans:
        phrase_text = p["text"].strip()

        hit = lookup_internal_phrase(phrase_text)
        if hit:
            results[phrase_text] = {
                "source": "phrase_definition",
                "definition": hit
            }
            continue

        if ols4_lookups < MAX_OLS4_LOOKUPS:
            batch = lookup_terms_ols4([phrase_text])
            ols4_lookups += 1
            bp = batch.get(phrase_text.lower())
        else:
            bp = None

        if bp:
            results[phrase_text] = {
                "source": "ontology_phrase",
                "definition": bp["definition"],
                "iri": bp.get("iri", "")
            }
            continue

        unmatched_terms.append(phrase_text)

    # ---------------------------------------------
    # STEP 4 — PROCESS 1-WORD TERMS (LAST)
    # ---------------------------------------------

    norm_to_originals = {}
    for w in one_word_terms:
        norm = normalize_term(w)
        if norm:
            norm_to_originals.setdefault(norm, set()).add(w)

    all_norms = list(norm_to_originals.keys())
    if len(all_norms) > MAX_TERMS_PER_DOCUMENT:
        all_norms = all_norms[:MAX_TERMS_PER_DOCUMENT]

    # Batch OLS4 lookup for all 1-word terms at once
    if ols4_lookups < MAX_OLS4_LOOKUPS:
        batch = lookup_terms_ols4(all_norms)
        ols4_lookups += 1
    else:
        batch = {n: None for n in all_norms}

    for norm in all_norms:
        originals = sorted(norm_to_originals[norm])
        rep = originals[0]

        hit = lookup_internal_word(rep)
        if hit:
            for word in originals:
                results[word] = {
                    "source": "word_definition",
                    "definition": hit
                }
            continue

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
