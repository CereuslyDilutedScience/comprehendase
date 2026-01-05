import requests
import re
from itertools import islice

# ---------------------------------------------------------
# CONFIG / LIMITS
# ---------------------------------------------------------

MAX_TERMS_PER_DOCUMENT = 2000  # raised for high recall
OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"
BIOPORTAL_API_KEY = "7e84a21d-3f8e-4837-b7a9-841fb4847ddf"   # <-- replace locally

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
    if t.endswith("proteins"):
        t = t[:-1]
    if t.endswith("genomes"):
        t = t[:-1]
    t = re.sub(r"[^a-z0-9\- ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def core_alpha(token: str) -> str:
    return re.sub(r"[^A-Za-z]", "", token)

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
    if not first[0].isupper():
        return False
    if not first.isalpha():
        return False
    if not second.islower():
        return False
    if not second.isalpha():
        return False
    return True

def looks_like_abbrev_species(tokens_raw):
    if len(tokens_raw) != 2:
        return False
    first_raw, second_raw = tokens_raw
    first = first_raw.strip()
    second = core_alpha(second_raw)
    if not first or not second:
        return False
    if not (len(first) == 2 and first[0].isupper() and first[1] == "."):
        return False
    if not second.islower():
        return False
    if not second.isalpha():
        return False
    return True

# ---------------------------------------------------------
# WORD-LEVEL CANDIDATE FILTER
# ---------------------------------------------------------

def is_candidate_single_word(raw_word: str) -> bool:
    w_clean = clean_token(raw_word)
    if not w_clean:
        return False

    lw = w_clean.lower()

    if lw in COMMON_WORDS or lw in BANNED_TOKENS:
        return False
    if len(lw) <= 2:
        return False

    if any(lw.startswith(p) for p in SCI_PREFIXES):
        return True
    if any(lw.endswith(s) for s in SCI_SUFFIXES):
        return True

    if is_acronym(w_clean):
        return True

    alpha_core = core_alpha(w_clean).lower()
    if len(alpha_core) >= 5 and alpha_core not in COMMON_WORDS and alpha_core not in BANNED_TOKENS:
        return True

    return False

# ---------------------------------------------------------
# PHRASE-LEVEL N-GRAMS
# ---------------------------------------------------------

def generate_ngrams(tokens, min_n=2, max_n=3):
    ngrams = []
    L = len(tokens)
    for n in range(min_n, max_n + 1):
        for i in range(L - n + 1):
            ngrams.append(tokens[i:i+n])
    return ngrams

def phrase_ngrams_for_ontology(phrase_text: str):
    if not phrase_text:
        return []

    tokens_raw = phrase_text.strip().split()
    if not tokens_raw:
        return []

    tokens_lower = [t.lower() for t in tokens_raw]
    results = set()

    for t_raw, t_low in zip(tokens_raw, tokens_lower):
        t_clean = clean_token(t_low)
        if len(t_clean) >= 3 and t_clean not in BANNED_TOKENS:
            results.add(t_clean)

    bigrams_raw = generate_ngrams(tokens_raw, min_n=2, max_n=2)
    for bg_tokens in bigrams_raw:
        if looks_like_species_name(bg_tokens) or looks_like_abbrev_species(bg_tokens):
            phrase = " ".join(bg_tokens)
            results.add(normalize_term(phrase))

    ngrams_tokens = generate_ngrams(tokens_lower, min_n=2, max_n=3)
    for ng_tokens in ngrams_tokens:
        joined_raw = " ".join(ng_tokens)
        joined_clean = clean_token(joined_raw)
        compact = joined_clean.replace(" ", "")

        if len(compact) < 5:
            continue

        has_strong_component = any(is_candidate_single_word(tok) for tok in ng_tokens)
        has_scientific_suffix = any(core_alpha(tok).lower().endswith(s) for tok in ng_tokens for s in SCI_SUFFIXES)

        if has_strong_component or has_scientific_suffix:
            results.add(joined_clean)

    return sorted(results)

# ---------------------------------------------------------
# BIOPORTAL LOOKUP (PRIMARY)
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
        r = requests.get(BIOPORTAL_SEARCH_URL, params=params, timeout=6)
        r.raise_for_status()
        data = r.json()

        collection = data.get("collection", [])
        if not collection:
            return None

        for item in collection:
            label = item.get("prefLabel") or item.get("label")
            definition = None

            defs = item.get("definition")
            if isinstance(defs, list) and defs:
                definition = defs[0]
            elif isinstance(defs, str):
                definition = defs

            if label and definition:
                return {
                    "label": label,
                    "definition": definition,
                    "iri": item.get("@id", "")
                }

        return None

    except Exception as e:
        print("BioPortal lookup failed for", term, ":", e, flush=True)
        return None

# ---------------------------------------------------------
# OLS4 LOOKUP (FALLBACK)
# ---------------------------------------------------------

BIO_ONTOLOGY_PREFIXES = {
    "go","so","pr","chebi","ncbitaxon","envo","obi","eco"
}

def lookup_term_ols4(term: str):
    norm = normalize_term(term)
    if not norm:
        return None

    params = {
        "q": norm,
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

        for d in docs:
            prefix = d.get("ontology_prefix", "").lower()
            definition = d.get("description", "")
            if prefix in BIO_ONTOLOGY_PREFIXES and definition:
                return {
                    "label": d.get("label", ""),
                    "definition": definition,
                    "iri": d.get("iri", "")
                }

        d = docs[0]
        if d.get("description"):
            return {
                "label": d.get("label", ""),
                "definition": d.get("description", ""),
                "iri": d.get("iri", "")
            }

        return None

    except Exception as e:
        print("OLS4 lookup failed for", term, ":", e, flush=True)
        return None

# ---------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------

def extract_ontology_terms(pages_output):
    candidate_terms = set()

    for page in pages_output:

        for w in page.get("words", []):
            raw = w.get("text", "")
            if raw and is_candidate_single_word(raw):
                norm = normalize_term(raw)
                if len(norm) >= 3 and norm not in COMMON_WORDS:
                    candidate_terms.add(norm)

        for phrase_obj in page.get("phrases", []):
            phrase_text = phrase_obj.get("text", "")
            if not phrase_text:
                continue

            for t in phrase_ngrams_for_ontology(phrase_text):
                norm = normalize_term(t)
                if len(norm) >= 3 and norm not in COMMON_WORDS:
                    candidate_terms.add(norm)

    if MAX_TERMS_PER_DOCUMENT and len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        candidate_terms = set(islice(sorted(candidate_terms), MAX_TERMS_PER_DOCUMENT))

    print("CANDIDATE TERMS (high-recall):", sorted(candidate_terms), flush=True)

    found_terms = {}
    for term in candidate_terms:

        hit = lookup_term_bioportal(term)
        if not hit:
            hit = lookup_term_ols4(term)

        if hit:
            found_terms[term] = hit

    return found_terms
