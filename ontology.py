import requests
import re

# -----------------------------
# AUTHOR / CITATION DETECTION
# -----------------------------

def looks_like_author_name(word):
    """Detect capitalized author last names commonly found in citations."""
    if re.match(r"^[A-Z][a-z]+$", word):
        return True
    if re.match(r"^[A-Z][a-z]+,$", word):
        return True
    return False


def phrase_is_citation(phrase):
    """Detect multi-word citation patterns."""
    lower = phrase.lower()

    if "et al" in lower:
        return True

    # Capitalized Lastname Lastname
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
    """Query the OLS4 API for a scientific term."""
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
            return None

        doc = docs[0]
        definition = (doc.get("description") or [""])[0].strip()

        if definition:
            return {
                "label": doc.get("label"),
                "definition": definition,
                "iri": doc.get("iri")
            }

        return None

    except Exception:
        return None


# -----------------------------
# TERM FILTERING
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
    "ase","itis","osis","emia","phage","phyte","coccus","viridae","aceae","ales",
    "bacteria","mycetes","mycotina","phyta","phyceae","mycota","archaea"
)


def is_candidate_term(word):
    """Filter single-word terms."""
    word_clean = re.sub(r"[^A-Za-z0-9\-]", "", word)

    if len(word_clean) < 3:
        return False

    if word_clean.lower() in COMMON_WORDS:
        return False

    if word_clean.isdigit():
        return False

    if looks_like_author_name(word_clean):
        return False

    # Gene names
    if re.match(r"^[A-Za-z]{2,6}\d*[A-Za-z]*$", word_clean):
        return True

    # Strain names
    if re.match(r"^[A-Z]{1,4}\d{1,4}[A-Za-z0-9]*$", word_clean):
        return True

    # Family names
    if word_clean.lower().endswith("aceae"):
        return True

    # Order names
    if word_clean.lower().endswith("ales"):
        return True

    # Class names
    if re.match(r"^[A-Z][a-z]+$", word_clean):
        return True

    # Broad taxonomic names
    if re.match(r"^[A-Z][a-zA-Z]+$", word_clean):
        return True

    # Proteins
    if word_clean.lower().endswith("protein") or word_clean.lower().endswith("proteins"):
        return True

    # Scientific prefixes/suffixes
    if word_clean.lower().startswith(SCI_PREFIXES):
        return True
    if word_clean.lower().endswith(SCI_SUFFIXES):
        return True

    return False


def is_candidate_phrase(phrase):
    """Filter multi-word phrases."""
    words = phrase.split()

    if phrase_is_citation(phrase):
        return False

    if all(looks_like_author_name(w) for w in words):
        return False

    # Species names (Genus species)
    if len(words) == 2:
        w1, w2 = words
        if re.match(r"^[A-Z][a-z]+$|^[A-Z]\.$", w1):
            if re.match(r"^[a-zA-Z]+$", w2):
                return True

    # Subspecies, serotypes, strains
    lower = phrase.lower()
    if "subspecies" in lower or "serotype" in lower or "strain" in lower:
        return True

    # Multi-word scientific concepts
    if len(words) > 1:
        if any(is_candidate_term(w) for w in words):
            return True
        return False

    return is_candidate_term(phrase)


# -----------------------------
# MAIN ENTRYPOINT (NEW)
# -----------------------------

def extract_ontology_terms(pages_output):
    """
    NEW: This replaces n-gram generation.
    Uses the 'phrases' list from extraction_text.py.
    """

    found_terms = {}

    for page in pages_output:
        # 1. Try multi-word phrases first
        for phrase_obj in page["phrases"]:
            phrase = phrase_obj["text"]

            if not is_candidate_phrase(phrase):
                continue

            hit = lookup_term_ols4(phrase)
            if hit:
                found_terms[phrase] = hit
                continue

        # 2. Fallback: single words
        for w in page["words"]:
            word = w["text"]

            if not is_candidate_term(word):
                continue

            hit = lookup_term_ols4(word)
            if hit:
                found_terms[word] = hit

    return found_terms
