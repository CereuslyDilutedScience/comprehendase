import requests
import re

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

PHRASE_DEFS = load_definitions("phrase_definitions.txt")
WORD_DEFS = load_definitions("word_definitions.txt")
SYNONYMS = load_synonyms("synonyms.txt")

# ---------------------------------------------------------
# NORMALIZATION (for dedupe only)
# ---------------------------------------------------------

def normalize_term(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9\- ]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

# ---------------------------------------------------------
# BIOPORTAL CONFIG
# ---------------------------------------------------------

BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"
BIOPORTAL_API_KEY = os.getenv("BIOPORTAL_API_KEY")

MAX_TERMS_PER_DOCUMENT = 1000
MAX_BIOPORTAL_LOOKUPS = 1000

# ---------------------------------------------------------
# BIOPORTAL LOOKUP (using ORIGINAL phrase/word)
# ---------------------------------------------------------

def lookup_term_bioportal(original_phrase: str):
    if not original_phrase.strip():
        return None

    params = {
        "q": original_phrase,
        "apikey": BIOPORTAL_API_KEY,
        "require_exact_match": "false"
    }

    try:
        r = requests.get(BIOPORTAL_SEARCH_URL, params=params, timeout=3)
        r.raise_for_status()
        data = r.json()

        for item in data.get("collection", []):
            label = item.get("prefLabel") or item.get("label")
            defs = item.get("definition")
            definition = defs[0] if isinstance(defs, list) and defs else defs

            if label and definition:
                return {
                    "label": label,
                    "definition": definition,
                    "iri": item.get("@id", "")
                }

        return None

    except Exception:
        return None

# ---------------------------------------------------------
# INTERNAL LOOKUP HELPERS
# ---------------------------------------------------------

def lookup_internal_phrase(phrase: str):
    p = phrase.lower().strip()
    return PHRASE_DEFS.get(p)

def lookup_internal_word(word: str):
    w = word.lower().strip()
    return WORD_DEFS.get(w)

def apply_synonym_lookup(term: str):
    t = term.lower().strip()
    # map variant → canonical if exists, else term itself
    return SYNONYMS.get(t, t)

# ---------------------------------------------------------
# MAIN ENTRYPOINT — PHASE 1 PIPELINE
# ---------------------------------------------------------

def extract_ontology_terms(extracted):
    """
    Phase 1 ontology pipeline:

    1. Bucket phrases into 1-word, 2-word, 3+ word.
    2. Process 2-word phrases:
       - phrase_definitions.txt
       - BioPortal
       - if both fail → split into 1-word terms → add to 1-word bucket.
    3. Process 3+ word phrases:
       - phrase_definitions.txt
       - BioPortal
       - if both fail → no definition, no highlight.
    4. Process 1-word bucket last:
       - dedupe
       - internal word definitions
       - BioPortal
       - attach to all occurrences.
    """

    phrases = extracted.get("phrases", [])

    results = {}          # term_text -> info dict
    unmatched_terms = []  # list of phrase/word texts with no definition

    # ---------------------------------------------
    # STEP 1 — BUCKET BY LENGTH
    # ---------------------------------------------
    one_word_spans = []   # list of phrase dicts with length == 1
    two_word_spans = []   # list of phrase dicts with length == 2
    multi_word_spans = [] # list of phrase dicts with length >= 3

    for p in phrases:
        text = p.get("text", "").strip()
        words_meta = p.get("words") or []
        if not text:
            continue

        # Prefer length from words metadata; fallback to splitting text
        if words_meta:
            length = len(words_meta)
        else:
            length = len(text.split())

        if length == 1:
            one_word_spans.append(p)
        elif length == 2:
            two_word_spans.append(p)
        else:
            multi_word_spans.append(p)

    # Bucket for 1-word *terms* to resolve at the end (strings, not spans)
    one_word_terms = []

    # Seed 1-word terms from original 1-word spans
    for p in one_word_spans:
        text = p.get("text", "").strip()
        if text:
            one_word_terms.append(text)

    bioportal_lookups = 0

    # ---------------------------------------------
    # STEP 2 — PROCESS 2-WORD PHRASES
    # ---------------------------------------------
    for p in two_word_spans:
        phrase_text = p.get("text", "").strip()
        if not phrase_text:
            continue

        # A. internal phrase definitions
        hit = lookup_internal_phrase(phrase_text)
        if hit:
            results[phrase_text] = {
                "source": "phrase_definition",
                "definition": hit
            }
            continue

        # B. BioPortal phrase lookup
        if bioportal_lookups < MAX_BIOPORTAL_LOOKUPS:
            bp = lookup_term_bioportal(phrase_text)
            bioportal_lookups += 1
        else:
            bp = None

        if bp:
            results[phrase_text] = {
                "source": "ontology_phrase",
                "definition": bp["definition"],
                "iri": bp.get("iri", "")
            }
            continue

        # C. If still no match → split into 1-word terms and add to 1-word bucket
        words_meta = p.get("words") or []
        if words_meta:
            split_words = [w.get("text", "").strip() for w in words_meta if w.get("text", "").strip()]
        else:
            split_words = [w.strip() for w in phrase_text.split() if w.strip()]

        for w in split_words:
            one_word_terms.append(w)

        # No result stored for the 2-word phrase itself at this stage

    # ---------------------------------------------
    # STEP 3 — PROCESS 3+ WORD PHRASES
    # ---------------------------------------------
    for p in multi_word_spans:
        phrase_text = p.get("text", "").strip()
        if not phrase_text:
            continue

        # A. internal phrase definitions
        hit = lookup_internal_phrase(phrase_text)
        if hit:
            results[phrase_text] = {
                "source": "phrase_definition",
                "definition": hit
            }
            continue

        # B. BioPortal phrase lookup
        if bioportal_lookups < MAX_BIOPORTAL_LOOKUPS:
            bp = lookup_term_bioportal(phrase_text)
            bioportal_lookups += 1
        else:
            bp = None

        if bp:
            results[phrase_text] = {
                "source": "ontology_phrase",
                "definition": bp["definition"],
                "iri": bp.get("iri", "")
            }
            continue

        # C. If still no match → stop, no definition, no highlight
        unmatched_terms.append(phrase_text)

    # ---------------------------------------------
    # STEP 4 — PROCESS 1-WORD TERMS (LAST)
    # ---------------------------------------------

    # Deduplicate by normalized form, but keep mapping back to original forms
    norm_to_originals = {}
    for w in one_word_terms:
        if not w.strip():
            continue
        norm = normalize_term(w)
        if not norm:
            continue
        norm_to_originals.setdefault(norm, set()).add(w.strip())

    # Cap number of unique 1-word terms if needed
    all_norms = list(norm_to_originals.keys())
    if len(all_norms) > MAX_TERMS_PER_DOCUMENT:
        all_norms = all_norms[:MAX_TERMS_PER_DOCUMENT]

    for norm in all_norms:
        originals = sorted(norm_to_originals[norm])
        # Representative word for lookup
        rep = originals[0]

        # Apply synonyms only at 1-word level
        lookup_key = apply_synonym_lookup(rep)

        # Internal word definition
        hit = lookup_internal_word(lookup_key)
        if hit:
            for word in originals:
                results[word] = {
                    "source": "word_definition",
                    "definition": hit
                }
            continue

        # BioPortal word lookup
        if bioportal_lookups < MAX_BIOPORTAL_LOOKUPS:
            bp = lookup_term_bioportal(rep)
            bioportal_lookups += 1
        else:
            bp = None

        if bp:
            for word in originals:
                results[word] = {
                    "source": "ontology_word",
                    "definition": bp["definition"],
                    "iri": bp.get("iri", "")
                }
            continue

        # If still no match → all originals are unmatched words
        for word in originals:
            unmatched_terms.append(word)

    # ---------------------------------------------
    # STEP 5 — RETURN RESULTS
    # ---------------------------------------------
    results["_unmatched"] = unmatched_terms
    return results
