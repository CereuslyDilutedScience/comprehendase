import requests
import re

# Simple in-memory cache for ontology lookups
TERM_CACHE = {}

# -----------------------------
# AUTHOR / CITATION DETECTION
# -----------------------------

def looks_like_author_name(word):
    """
    Detect capitalized author last names commonly found in citations.
    """
    # Smith, Johnson, Fisher, etc.
    if re.match(r"^[A-Z][a-z]+$", word):
        return True

    # Smith,
    if re.match(r"^[A-Z][a-z]+,$", word):
        return True

    return False


def phrase_is_citation(phrase):
    """
    Detect multi-word citation patterns like:
    - Smith et al.
    - Johnson and Lee
    - Baker et al., 2020
    """
    lower = phrase.lower()

    if "et al" in lower:
        return True

    # Capitalized Lastname Lastname (common in citations)
    if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+$", phrase):
        return True

    # Lastname, YEAR
    if re.match(r"^[A-Z][a-z]+, \d{4}$", phrase):
        return True

    return False


# -----------------------------
# OLS4 LOOKUP
# -----------------------------
def lookup_term_ols4(term):
    """
    Query the OLS4 API for a scientific term.
    Uses in-memory caching to avoid repeated lookups.
    Returns a dict with label, definition, iri OR None if not found.
    """

    # Normalize term for caching
    key = term.strip().lower()

    # Return cached result if available
    if key in TERM_CACHE:
        return TERM_CACHE[key]

    url = "https://www.ebi.ac.uk/ols4/api/search"
    params = {
        "q": term,
        "queryFields": "label",
        "fields": "label,description,iri",
        "exact": "false"
    }

    try:
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()

        docs = data.get("response", {}).get("docs", [])
        if not docs:
            TERM_CACHE[key] = None
            return None

        doc = docs[0]
        result = {
            "label": doc.get("label"),
            "definition": (doc.get("description") or [""])[0],
            "iri": doc.get("iri")
        }

        TERM_CACHE[key] = result
        return result

    except Exception:
        TERM_CACHE[key] = None
        return None


# -----------------------------
# TERM FILTERING (OPTIMIZED)
# -----------------------------

COMMON_WORDS = {
    "the","and","for","with","from","that","this","were","have","been",
    "in","on","of","to","as","by","is","are","be","or","an","at","it",
    "we","was","using","used","use","our","their","these","those"
}

SCI_PREFIXES = (
    "bio", "micro", "immuno", "neuro", "cyto", "geno", "patho",
    "chemo", "thermo", "myco", "entomo"
)

SCI_SUFFIXES = (
    "ase", "itis", "osis", "emia", "phage", "phyte", "coccus",
    "viridae", "aceae"
)


def is_candidate_term(word):
    """
    Decide if a single word is worth checking in OLS.
    Much stricter than before to avoid thousands of junk lookups.
    """
    word_clean = re.sub(r"[^A-Za-z0-9\-]", "", word)

    if len(word_clean) < 4:
        return False

    if word_clean.lower() in COMMON_WORDS:
        return False

    if word_clean.isdigit():
        return False

    # Reject author names
    if looks_like_author_name(word_clean):
        return False

    # Gene/protein names (e.g., BRCA1, rpoB)
    if re.match(r"^[A-Za-z]{2,5}\d+$", word_clean):
        return True

    # Capitalized scientific words (e.g., Staphylococcus)
    if re.match(r"^[A-Z][a-z]+$", word_clean):
        return True

    # Prefix-based scientific words
    if word_clean.lower().startswith(SCI_PREFIXES):
        return True

    # Suffix-based scientific words
    if word_clean.lower().endswith(SCI_SUFFIXES):
        return True

    return False


def is_candidate_phrase(phrase):
    """
    Decide if a multi-word phrase is worth checking in OLS.
    Now requires at least ONE scientific-looking word.
    """
    words = phrase.split()

    # Reject citation patterns
    if phrase_is_citation(phrase):
        return False

    # Reject if any word is a common stopword
    if any(w.lower() in COMMON_WORDS for w in words):
        return False

    # Reject if any word is an author name
    if any(looks_like_author_name(w) for w in words):
        return False

    # Species names: Genus species
    if len(words) == 2 and words[0][0].isupper() and words[1].islower():
        return True

    # Multi-word scientific concepts:
    # Keep only if at least ONE word looks scientific
    if len(words) > 1:
        if any(is_candidate_term(w) for w in words):
            return True
        return False

    # Fallback to single-word logic
    return is_candidate_term(phrase)


# -----------------------------
# N-GRAM GENERATION
# -----------------------------

def generate_ngrams(words, max_n=3):
    """
    Generate n-grams (3-word, 2-word, 1-word) from a list of words.
    Returns tuples: (start_index, end_index, phrase)
    """
    ngrams = []
    for i in range(len(words)):
        for n in range(max_n, 0, -1):
            if i + n <= len(words):
                phrase = " ".join(words[i:i+n])
                ngrams.append((i, i+n, phrase))
    return ngrams
