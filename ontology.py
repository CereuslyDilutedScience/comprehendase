import requests
import re
from itertools import islice
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------
# CONFIG / LIMITS
# ---------------------------------------------------------

MAX_TERMS_PER_DOCUMENT = 500
MAX_BIOPORTAL_LOOKUPS = 300

BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"
BIOPORTAL_API_KEY = "7e84a21d-3f8e-4837-b7a9-841fb4847ddf"

# ---------------------------------------------------------
# COMMON WORD / PATTERN FILTERS
# ---------------------------------------------------------

COMMON_WORDS = {
    "the","and","for","with","from","that","this","were","was","are","but",
    "into","onto","between","among","after","before","during","under","over",
    "using","used","based","data","study","analysis","results","methods",
    "introduction","discussion","conclusion","figure","table","supplementary",
    "supplement","dataset","section","chapter","page","value","values"
}

SCI_PREFIXES = (
    "bio","micro","immuno","neuro","cyto","geno","patho",
    "chemo","thermo","myco","entomo","viro","bacterio",
    "proto","phyto","toxo","onco","cardio","hepato"
)

SCI_SUFFIXES = (
    "ase","ases","protein","proteins","enzyme","enzymes",
    "gen","gens","genome","genomes","omic","omics","ome","omes",
    "itis","osis","oses","emia","emias","phage","phages",
    "coccus","cocci","bacter","bacteria","archaea",
    "viridae","aceae","ales","mycetes","mycotina","phyta","phyceae",
    "plasm","plasma","cyte","cytes","blast","blasts","some","somes",
    "filament","filaments","granule","granules","membrane","membranes",
    "pathway","pathways","response","responses","signaling","signalling"
)

BANNED_TOKENS = {
    "figure","table","supplementary","supplement","dataset","analysis"
}

STOPWORDS = COMMON_WORDS | BANNED_TOKENS

# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def is_acronym(word: str) -> bool:
    w = word.strip()
    if len(w) < 2:
        return False
    if not re.fullmatch(r"[A-Za-z0-9\-]+", w):
        return False
    return sum(1 for c in w if c.isupper()) >= 2

def clean_token(token: str) -> str:
    return token.strip().strip(".,;:()[]{}\"'")

def normalize_term(term: str) -> str:
    t = term.strip().lower()
    t = re.sub(r"[^a-z0-9\- ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def core_alpha(token: str) -> str:
    return re.sub(r"[^A-Za-z]", "", token)

# ---------------------------------------------------------
# JUNK DETECTION
# ---------------------------------------------------------

def is_numeric_heavy(term: str) -> bool:
    digits = sum(c.isdigit() for c in term)
    return digits > len(term) * 0.4

def looks_like_accession(term: str) -> bool:
    return bool(re.match(r"^[a-z]{1,3}\d{4,}$", term))

def looks_like_hash(term: str) -> bool:
    return len(term) > 20 and re.fullmatch(r"[a-f0-9]+", term)

def looks_like_doi_or_url(term: str) -> bool:
    return "doi" in term or "http" in term or "www" in term

def is_junk_term(term: str) -> bool:
    if len(term) > 40:
        return True
    if is_numeric_heavy(term):
        return True
    if looks_like_accession(term):
        return True
    if looks_like_hash(term):
        return True
    if looks_like_doi_or_url(term):
        return True
    if term in STOPWORDS:
        return True
    if not re.search(r"[a-zA-Z]", term):
        return True
    return False

def is_junk_phrase(tokens):
    if any(tok in STOPWORDS for tok in tokens):
        return True
    if any(any(c.isdigit() for c in tok) for tok in tokens):
        return True
    return False

# ---------------------------------------------------------
# SPECIES DETECTION
# ---------------------------------------------------------

def looks_like_species_name(tokens_raw):
    if len(tokens_raw) != 2:
        return False
    first_raw, second_raw = tokens_raw
    first = core_alpha(first_raw)
    second = core_alpha(second_raw)
    if not first or not second:
        return False
    return first[0].isupper() and first.isalpha() and second.islower() and second.isalpha()

def looks_like_abbrev_species(tokens_raw):
    if len(tokens_raw) != 2:
        return False
    first_raw, second_raw = tokens_raw
    first = first_raw.strip()
    second = core_alpha(second_raw)
    if not first or not second:
        return False
    return len(first) == 2 and first[0].isupper() and first[1] == "." and second.islower()

# ---------------------------------------------------------
# WORD-LEVEL CANDIDATE FILTER
# ---------------------------------------------------------

def is_candidate_single_word(raw_word: str) -> bool:
    w_clean = clean_token(raw_word)
    if not w_clean:
        return False

    lw = w_clean.lower()
    if lw in STOPWORDS:
        return False
    if is_junk_term(lw):
        return False

    if any(lw.startswith(p) for p in SCI_PREFIXES):
        return True
    if any(lw.endswith(s) for s in SCI_SUFFIXES):
        return True
    if is_acronym(w_clean):
        return True

    alpha_core = core_alpha(w_clean).lower()
    return len(alpha_core) >= 5

# ---------------------------------------------------------
# PHRASE-LEVEL N-GRAMS
# ---------------------------------------------------------

def generate_ngrams(tokens, min_n=2, max_n=3):
    L = len(tokens)
    for n in range(min_n, max_n + 1):
        for i in range(L - n + 1):
            yield tokens[i:i+n]

def phrase_ngrams_for_ontology(phrase_text: str):
    if not phrase_text:
        return []

    tokens_raw = phrase_text.strip().split()
    tokens_lower = [t.lower() for t in tokens_raw]
    results = set()

    # Unigrams
    for t in tokens_lower:
        if len(t) >= 3 and not is_junk_term(t):
            results.add(t)

    # Species
    for bg in generate_ngrams(tokens_raw, 2, 2):
        if looks_like_species_name(bg) or looks_like_abbrev_species(bg):
            results.add(normalize_term(" ".join(bg)))

    # Bigrams/trigrams
    for ng in generate_ngrams(tokens_lower, 2, 3):
        if is_junk_phrase(ng):
            continue

        joined = " ".join(ng)
        compact = joined.replace(" ", "")
        if len(compact) < 5:
            continue

        if any(is_candidate_single_word(tok) for tok in ng):
            results.add(joined)

    return sorted(results)

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
# UPDATED MAIN ENTRYPOINT (GLOBAL WORDS + PHRASES)
# ---------------------------------------------------------

def extract_ontology_terms(extracted):
    """
    extracted = {
        "words": [...],
        "phrases": [...]
    }
    """

    candidate_terms = set()

    # --- GLOBAL WORDS ---
    for w in extracted.get("words", []):
        raw = w.get("text", "")
        if raw and is_candidate_single_word(raw):
            norm = normalize_term(raw)
            if norm and not is_junk_term(norm):
                candidate_terms.add(norm)

    # --- GLOBAL PHRASES ---
    for phrase_obj in extracted.get("phrases", []):
        phrase_text = phrase_obj.get("text", "")
        if not phrase_text:
            continue

        for t in phrase_ngrams_for_ontology(phrase_text):
            norm = normalize_term(t)
            if norm and not is_junk_term(norm):
                candidate_terms.add(norm)

    # Limit total candidates
    candidate_terms = sorted(candidate_terms)
    if len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        candidate_terms = candidate_terms[:MAX_TERMS_PER_DOCUMENT]

    print("CANDIDATE TERMS (filtered):", candidate_terms, flush=True)
    return candidate_terms

# ---------------------------------------------------------
# PARALLEL LOOKUP
# ---------------------------------------------------------

def process_terms(candidate_terms):
    found_terms = {}
    bioportal_count = 0

    print("\n=== DEBUG: Parallel ontology lookup ===")
    print("MAX_BIOPORTAL_LOOKUPS:", MAX_BIOPORTAL_LOOKUPS)

    terms_to_lookup = candidate_terms[:MAX_BIOPORTAL_LOOKUPS]

    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_term = {
            executor.submit(lookup_term_bioportal, term): term
            for term in terms_to_lookup
        }

        for future in as_completed(future_to_term):
            term = future_to_term[future]
            try:
                hit = future.result()
            except Exception as e:
                print(f"Error for term {term}: {e}")
                continue

            if hit:
                found_terms[term] = hit
                bioportal_count += 1
                print(f"Hit: {term} → {hit['label']}")
            else:
                print(f"No hit: {term}")

    print("\n=== DEBUG COMPLETE ===")
    print("Total hits:", bioportal_count)
    print("Found terms:", list(found_terms.keys()))
    print("=======================\n")

    return found_terms
