import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------
# LOAD LISTS
# ---------------------------------------------------------

def load_list(path):
    with open(path, encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())

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

STOPWORDS = load_list("stopwords.txt")
PHRASE_DEFS = load_definitions("phrase_definitions.txt")
WORD_DEFS = load_definitions("definitions.txt")
SYNONYMS = load_synonyms("synonyms.txt")

# ---------------------------------------------------------
# NORMALIZATION
# ---------------------------------------------------------

def normalize_term(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9\- ]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

def apply_synonyms(term: str) -> str:
    """Normalize using synonyms.txt"""
    if term in SYNONYMS:
        return SYNONYMS[term]
    return term

# ---------------------------------------------------------
# BIOPORTAL CONFIG
# ---------------------------------------------------------

BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"
BIOPORTAL_API_KEY = "7e84a21d-3f8e-4837-b7a9-841fb4847ddf"

MAX_TERMS_PER_DOCUMENT = 1000
MAX_BIOPORTAL_LOOKUPS = 1000

# ---------------------------------------------------------
# BIOPORTAL LOOKUP
# ---------------------------------------------------------

def lookup_term_bioportal(term: str):
    norm = normalize_term(term)
    if not norm:
        return None

    params = {
        "q": norm,
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
# MAIN ENTRYPOINT (OPTION B + OPTION 2)
# ---------------------------------------------------------

def extract_ontology_terms(extracted):
    """
    Returns a unified dictionary:
    {
        "Original PDF Text": {
            "source": "phrase_definition" | "word_definition" | "ontology",
            "definition": "...",
            "iri": optional
        }
    }
    """
    results = {}

    # Collect candidate terms from extract_text.py
    phrases = extracted.get("phrases", [])

    # Build a list of (original_text, normalized_text)
    candidates = []
    for p in phrases:
        original = p["text"]
        normalized = normalize_term(original)

        # Skip stopwords
        if normalized in STOPWORDS:
            continue

        # Apply synonyms
        normalized = apply_synonyms(normalized)

        candidates.append((original, normalized))

    # Deduplicate by normalized form
    seen_norm = set()
    final_candidates = []
    for original, norm in candidates:
        if norm not in seen_norm:
            seen_norm.add(norm)
            final_candidates.append((original, norm))

    # Limit
    if len(final_candidates) > MAX_TERMS_PER_DOCUMENT:
        final_candidates = final_candidates[:MAX_TERMS_PER_DOCUMENT]

    # -----------------------------------------------------
    # LAYER 1 — PHRASE DEFINITIONS
    # -----------------------------------------------------
    for original, norm in final_candidates:
        if norm in PHRASE_DEFS:
            results[original] = {
                "source": "phrase_definition",
                "definition": PHRASE_DEFS[norm]
            }

    # -----------------------------------------------------
    # LAYER 2 — WORD DEFINITIONS
    # -----------------------------------------------------
    for original, norm in final_candidates:
        if original in results:
            continue  # phrase already matched

        if norm in WORD_DEFS:
            results[original] = {
                "source": "word_definition",
                "definition": WORD_DEFS[norm]
            }

    # -----------------------------------------------------
    # LAYER 3 — ONTOLOGY LOOKUP (ONLY FOR LEFTOVERS)
    # -----------------------------------------------------
    to_lookup = [
        (original, norm)
        for (original, norm) in final_candidates
        if original not in results
    ]

    to_lookup = to_lookup[:MAX_BIOPORTAL_LOOKUPS]

    with ThreadPoolExecutor(max_workers=15) as executor:
        future_map = {
            executor.submit(lookup_term_bioportal, norm): (original, norm)
            for (original, norm) in to_lookup
        }

        for future in as_completed(future_map):
            original, norm = future_map[future]
            hit = future.result()
            if hit:
                results[original] = {
                    "source": "ontology",
                    "definition": hit["definition"],
                    "iri": hit.get("iri", "")
                }

    return results
