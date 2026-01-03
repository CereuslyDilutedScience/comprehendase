import requests
import re
from itertools import islice

# ---------------------------------------------------------
# CONFIG / LIMITS
# ---------------------------------------------------------

# Hard cap on how many unique candidate terms we will query per PDF
MAX_TERMS_PER_DOCUMENT = 300

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

# ---------------------------------------------------------
# COMMON WORD / PATTERN FILTERS
# ---------------------------------------------------------

COMMON_WORDS = {
    "the","and","for","with","from","that","this","were","have","been",
    "in","on","of","to","as","by","is","are","be","or","an","at","it",
    "we","was","using","used","use","our","their","these","those",
    "its","they","them","he","she","his","her","you","your","i",
    "into","onto","within","between","through","over","under","out",
    "up","down","off","than","then","also","such","each","both","via",
    "per","among","amid","despite","during","before","after","because"
}

SCI_PREFIXES = (
    "bio", "micro", "immuno", "neuro", "cyto", "geno", "patho",
    "chemo", "thermo", "myco", "entomo"
)

SCI_SUFFIXES = (
    "ase","itis","osis","emia","phage","phyte","coccus","viridae","aceae","ales",
    "bacteria","mycetes","mycotina","phyta","phyceae","mycota","archaea"
)

# Lowercase biological terms we explicitly allow
ALLOWED_LOWER = {
    "biofilm", "larvae", "pathogen", "pathogenic", "lipoprotein", "lipoproteins",
    "adhesion", "invasion", "dissemination", "strain", "strains",
    "protein", "proteins", "microorganism", "microorganisms", "enzyme",
    "bacteria", "fungi", "broth", "agar", "colony", "colonies",
    "pneumonia", "mastitis", "arthritis", "otitis", "media"
}

# ---------------------------------------------------------
# AUTHOR / CITATION DETECTION
# ---------------------------------------------------------

def looks_like_author_name(word: str) -> bool:
    """Detect capitalized author last names commonly found in citations."""
    if re.match(r"^[A-Z][a-z]+$", word):
        return True
    if re.match(r"^[A-Z][a-z]+,$", word):
        return True
    return False


def phrase_is_citation(phrase: str) -> bool:
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

# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def is_acronym(word: str) -> bool:
    """Detect standalone acronyms (we suppress these unless part of a phrase)."""
    return word.isupper() and len(word) >= 3


def clean_token(token: str) -> str:
    """Strip punctuation and control chars from a token."""
    token = token.strip().strip(".,;:()[]{}")
    token = token.replace("\u200b", "").replace("\u00ad", "").replace("\u2011", "")
    return token


def words_from_phrase_text(phrase_text: str):
    """Split phrase text into cleaned word tokens."""
    raw_parts = phrase_text.split()
    cleaned = []
    for p in raw_parts:
        t = clean_token(p)
        if t:
            cleaned.append(t)
    return cleaned

# ---------------------------------------------------------
# WORD-LEVEL CANDIDATE FILTER
# ---------------------------------------------------------

def is_candidate_single_word(raw_word: str) -> bool:
    """
    Decide if a single word is worth sending to OLS4.
    raw_word is the original token (case preserved).
    """
    if not raw_word:
        return False

    word_clean = re.sub(r"[^A-Za-z0-9\-]", "", raw_word)
    if not word_clean:
        return False

    if len(word_clean) < 3:
        return False

    lower = word_clean.lower()

    if lower in COMMON_WORDS:
        return False

    if word_clean.isdigit():
        return False

    if looks_like_author_name(word_clean):
        return False

    # Suppress standalone acronyms (PCR, ITS, etc.) as single terms
    if is_acronym(word_clean):
        return False

    # Allow pure lowercase biological terms via whitelist/patterns
    if word_clean.islower():
        if lower in ALLOWED_LOWER:
            return True
        if lower.startswith(SCI_PREFIXES):
            return True
        if lower.endswith(SCI_SUFFIXES):
            return True
        return False

    # Gene-like patterns (mixed case or uppercase, often with digits)
    if re.match(r"^[A-Za-z]{2,6}\d*[A-Za-z]*$", word_clean):
        return True

    # Strain-like patterns
    if re.match(r"^[A-Z]{1,4}\d{1,4}[A-Za-z0-9]*$", word_clean):
        return True

    # Family names
    if lower.endswith("aceae"):
        return True

    # Order names
    if lower.endswith("ales"):
        return True

    # Capitalized biological / taxonomic words
    if re.match(r"^[A-Z][a-z]+$", word_clean):
        return True

    # Broader scientific names (capitalized, may include more letters)
    if re.match(r"^[A-Z][a-zA-Z]+$", word_clean):
        return True

    # Protein-like words
    if lower.endswith("protein") or lower.endswith("proteins"):
        return True

    # Scientific prefixes/suffixes
    if lower.startswith(SCI_PREFIXES):
        return True
    if lower.endswith(SCI_SUFFIXES):
        return True

    return False

# ---------------------------------------------------------
# PHRASE-LEVEL FILTERING / N-GRAMS
# ---------------------------------------------------------

def is_species_like(words) -> bool:
    """Case-insensitive species detection (two words, both non-trivial)."""
    if len(words) < 2:
        return False

    w1, w2 = words[0], words[1]

    if not w1.isalpha() or not w2.isalpha():
        return False

    if len(w1) < 3 or len(w2) < 3:
        return False

    if w1.lower() in COMMON_WORDS or w2.lower() in COMMON_WORDS:
        return False

    return True


def is_candidate_phrase_full(phrase_text: str) -> bool:
    """
    Decide if a multi-word phrase (as a whole) is worth querying.
    """
    if not phrase_text:
        return False

    if phrase_is_citation(phrase_text):
        return False

    words = words_from_phrase_text(phrase_text)
    if len(words) < 2:
        return False

    # All author-like names -> skip
    if all(looks_like_author_name(w) for w in words):
        return False

    # Species-like patterns
    if is_species_like(words):
        return True

    lower = phrase_text.lower()
    # Subspecies, serotypes, strains
    if "subspecies" in lower or "serotype" in lower or "strain" in lower:
        return True

    # Generic multi-word scientific-ish phrase:
    # keep if there is at least one non-trivial, non-common word.
    for w in words:
        w_clean = re.sub(r"[^A-Za-z0-9\-]", "", w)
        if len(w_clean) < 3:
            continue
        if w_clean.lower() in COMMON_WORDS:
            continue
        return True

    return False


def generate_ngrams(tokens, min_n=2, max_n=3):
    """Generate n-grams (as strings) from a list of tokens."""
    ngrams = []
    L = len(tokens)
    for n in range(min_n, max_n + 1):
        if L < n:
            continue
        for i in range(L - n + 1):
            ngram = " ".join(tokens[i:i+n])
            ngrams.append(ngram)
    return ngrams


def phrase_ngrams_for_ontology(phrase_text: str):
    """
    From a phrase, produce:
      - full phrase (if candidate)
      - 2-grams
      - 3-grams
    all filtered by basic sanity rules.
    """
    results = []

    # Full phrase
    if is_candidate_phrase_full(phrase_text):
        results.append(phrase_text)

    tokens = words_from_phrase_text(phrase_text)
    if len(tokens) < 2:
        return results

    # N-grams (2–3)
    for ng in generate_ngrams(tokens, min_n=2, max_n=3):
        # Apply a light filter: skip if all tokens are too trivial/common
        words = words_from_phrase_text(ng)
        keep = False
        for w in words:
            wc = re.sub(r"[^A-Za-z0-9\-]", "", w)
            if len(wc) < 3:
                continue
            if wc.lower() in COMMON_WORDS:
                continue
            keep = True
            break
        if keep:
            results.append(ng)

    return results

# ---------------------------------------------------------
# OLS4 LOOKUP (per-term)
# ---------------------------------------------------------

def lookup_term_ols4(term: str):
    """
    Query the OLS4 API for a scientific term.
    Two-stage: prefer exact label match, then filtered fuzzy match.
    """
    params = {
        "q": term,
        "queryFields": "label",
        "fields": "label,description,iri,ontology_prefix",
        "exact": "false"
    }

    try:
        r = requests.get(OLS4_SEARCH_URL, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()

        docs = data.get("response", {}).get("docs", [])
        if not docs:
            return None

        term_lower = term.lower()

        # Stage 1: exact label match
        for doc in docs:
            label = doc.get("label", "")
            definition_list = doc.get("description") or []
            definition = definition_list[0].strip() if definition_list else ""
            if label and label.lower() == term_lower and definition:
                return {
                    "label": label,
                    "definition": definition,
                    "iri": doc.get("iri")
                }

        # Stage 2: label must contain term (case-insensitive)
        for doc in docs:
            label = doc.get("label", "")
            definition_list = doc.get("description") or []
            definition = definition_list[0].strip() if definition_list else ""
            if not label:
                continue
            if term_lower not in label.lower():
                continue
            if definition:
                return {
                    "label": label,
                    "definition": definition,
                    "iri": doc.get("iri")
                }

        return None

    except Exception:
        return None

# ---------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------

def extract_ontology_terms(pages_output):
    """
    Given pages_output from extract_text.py, return a dict:
      term -> { label, definition, iri }
    Strategy:
      - collect candidate single words
      - collect candidate phrase-based n-grams (2–3) and full phrases
      - filter, deduplicate (per document)
      - cap total terms per document
      - query OLS4 term-by-term
    """

    # 1. Collect candidates (per-document)
    candidate_terms = set()

    for page in pages_output:
        # Single words
        for w in page.get("words", []):
            raw = w.get("text", "")
            if not raw:
                continue
            # Do NOT lowercase before pattern detection
            if is_candidate_single_word(raw):
                candidate_terms.add(raw)

        # Phrases and their n-grams
        for phrase_obj in page.get("phrases", []):
            phrase_text = phrase_obj.get("text", "")
            if not phrase_text:
                continue

            # Full phrase + 2–3-grams
            for t in phrase_ngrams_for_ontology(phrase_text):
                candidate_terms.add(t)

    # 2. Cap total number of terms to avoid runaway CPU
    if len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        # Deterministic truncation: sort and keep first N
        candidate_terms = set(islice(sorted(candidate_terms), MAX_TERMS_PER_DOCUMENT))

    # 3. Query OLS4 per term
    found_terms = {}

    for term in sorted(candidate_terms):
        hit = lookup_term_ols4(term)
        if hit:
            found_terms[term] = hit

    return found_terms
