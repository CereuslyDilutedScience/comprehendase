import requests
import re
from itertools import islice
import sys

# ---------------------------------------------------------
# CONFIG / LIMITS
# ---------------------------------------------------------

MAX_TERMS_PER_DOCUMENT = 1000
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

# Scientific prefixes/suffixes for biological terms
SCI_PREFIXES = (
    "bio", "micro", "immuno", "neuro", "cyto", "geno", "patho",
    "chemo", "thermo", "myco", "entomo"
)

SCI_SUFFIXES = (
    "ase","itis","osis","emia","phage","phyte","coccus","viridae","aceae","ales",
    "bacteria","mycetes","mycotina","phyta","phyceae","mycota","archaea"
)

# Allowed lowercase biological terms
ALLOWED_LOWER = {
    "biofilm", "larvae", "pathogen", "pathogenic", "lipoprotein", "lipoproteins",
    "adhesion", "invasion", "dissemination", "strain", "strains",
    "protein", "proteins", "microorganism", "microorganisms", "enzyme",
    "bacteria", "fungi", "colony", "colonies",
    "pneumonia", "mastitis", "arthritis", "otitis", "media"
}

# Tokens that should never appear in a biological n‑gram
BANNED_TOKENS = {
    "to","was","were","size","data","finally","software",
    "accession","genbank","issue","volume","license",
    "biosample","bioproject","biosystems","samn","cp0"
}

# Biological genome contexts to keep (multi‑word genome phrases)
BIO_GENOME_CONTEXT = {
    "replication","stability","annotation","assembly"
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
    """Detect standalone acronyms (PCR, ITS, etc.)."""
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

    # Remove common words
    if lower in COMMON_WORDS:
        return False

    # Remove banned metadata/procedural tokens
    if lower in BANNED_TOKENS:
        return False

    # Remove pure numbers
    if word_clean.isdigit():
        return False

    # Remove author names
    if looks_like_author_name(word_clean):
        return False

    # Remove standalone acronyms
    if is_acronym(word_clean):
        return False

    # Explicitly allow single-word genome terms
    if lower in {"genome", "genomic", "genomics"}:
        return True

    # Allow lowercase biological terms
    if word_clean.islower():
        if lower in ALLOWED_LOWER:
            return True
        if lower.startswith(SCI_PREFIXES):
            return True
        if lower.endswith(SCI_SUFFIXES):
            return True
        return False

    # Gene-like patterns (uvrC, rpoB, etc.)
    if re.match(r"^[A-Za-z]{2,6}\d*[A-Za-z]*$", word_clean):
        return True

    # Strain-like patterns (PG45, HB0801, XBY01)
    if re.match(r"^[A-Z]{1,4}\d{1,4}[A-Za-z0-9]*$", word_clean):
        return True

    # Family names (Mycoplasmataceae)
    if lower.endswith("aceae"):
        return True

    # Order names (Mollicutes, etc.)
    if lower.endswith("ales"):
        return True

    # Capitalized biological/taxonomic words
    if re.match(r"^[A-Z][a-z]+$", word_clean):
        return True

    # Broader scientific names
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

# Procedural / narrative / metadata patterns to remove entirely
PROCEDURAL_PATTERNS = [
    "were incubated", "cultures were", "incubated at",
    "listed as", "co-first", "to isolate",
    "important pathogen", "serious pneumonia", "an important",
    "the genome size", "genome size of", "gc content",
    "complete genome", "genome sequence", "sequence of",
    "international license", "volume", "issue", "e00001",
    "accession", "genbank", "samn", "cp0", "biosample",
    "bioproject", "biosystems"
]

def phrase_is_procedural_or_metadata(phrase: str) -> bool:
    """Remove procedural, narrative, accession, and metadata fragments."""
    lower = phrase.lower()
    for pat in PROCEDURAL_PATTERNS:
        if pat in lower:
            return True
    return False


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
    """Decide if a multi-word phrase (as a whole) is worth querying."""
    if not phrase_text:
        return False

    if phrase_is_citation(phrase_text):
        return False

    if phrase_is_procedural_or_metadata(phrase_text):
        return False

    words = words_from_phrase_text(phrase_text)
    if len(words) < 2:
        return False

    # Remove author lists
    if all(looks_like_author_name(w) for w in words):
        return False

    # Reject if any banned token appears
    if any(w.lower() in BANNED_TOKENS for w in words):
        return False

    # Species-like patterns
    if is_species_like(words):
        return True

    # Strain / serotype / subspecies
    lower = phrase_text.lower()
    if "strain" in lower or "serotype" in lower or "subspecies" in lower:
        return True

    # Biological genome phrases (genome replication, genome assembly, etc.)
    if words[0].lower() == "genome":
        if len(words) >= 2 and words[1].lower() in BIO_GENOME_CONTEXT:
            return True
        else:
            return False

    # Biological multi-word phrases: keep only if all tokens are biological or neutral
    for w in words:
        wc = re.sub(r"[^A-Za-z0-9\-]", "", w)
        if len(wc) < 3:
            continue
        if wc.lower() in COMMON_WORDS:
            continue
        if is_candidate_single_word(wc):
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
    All filtered by strict Option-B rules.
    """
    results = []

    if is_candidate_phrase_full(phrase_text):
        results.append(phrase_text)

    tokens = words_from_phrase_text(phrase_text)
    if len(tokens) < 2:
        return results

    for ng in generate_ngrams(tokens, min_n=2, max_n=3):
        if phrase_is_procedural_or_metadata(ng):
            continue
        if phrase_is_citation(ng):
            continue

        words = words_from_phrase_text(ng)

        # Reject if any banned token appears
        if any(w.lower() in BANNED_TOKENS for w in words):
            continue

        # Biological genome phrases
        if words[0].lower() == "genome":
            if len(words) >= 2 and words[1].lower() in BIO_GENOME_CONTEXT:
                results.append(ng)
            continue

        # Keep only if all tokens are biologically valid or neutral
        if all(
            (len(re.sub(r"[^A-Za-z0-9\-]", "", w)) >= 3 and
             (w.lower() in COMMON_WORDS or is_candidate_single_word(re.sub(r"[^A-Za-z0-9\-]", "", w))))
            for w in words
        ):
            results.append(ng)

    return results
# ---------------------------------------------------------
# OLS4 LOOKUP (Improved Ranking)
# ---------------------------------------------------------

BIO_ONTOLOGY_PREFIXES = {
    "go", "so", "pr", "chebi", "ncbitaxon", "envo", "obi", "eco"
}

def normalize_term(term: str) -> str:
    """Normalize plural/singular forms for better matching."""
    t = term.lower().strip()

    # proteins -> protein
    if t.endswith("proteins"):
        return t[:-1]

    # genomes -> genome
    if t.endswith("genomes"):
        return t[:-1]

    return t


def lookup_term_ols4(term: str):
    """Query the OLS4 API for a scientific term with improved ranking."""
    norm = normalize_term(term)

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

        term_lower = norm.lower()

        # -----------------------------
        # Stage 1: Exact label match
        # -----------------------------
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

        # -----------------------------
        # Stage 2: Synonym / startswith match
        # -----------------------------
        stage2 = []
        for doc in docs:
            label = doc.get("label", "")
            if not label:
                continue

            if label.lower().startswith(term_lower):
                stage2.append(doc)

        if stage2:
            # Prefer biological ontologies
            stage2.sort(
                key=lambda d: (
                    0 if (d.get("ontology_prefix", "").lower() in BIO_ONTOLOGY_PREFIXES) else 1,
                    len(d.get("label", ""))
                )
            )
            best = stage2[0]
            definition_list = best.get("description") or []
            definition = definition_list[0].strip() if definition_list else ""
            if definition:
                return {
                    "label": best.get("label"),
                    "definition": definition,
                    "iri": best.get("iri")
                }

        # -----------------------------
        # Stage 3: Label contains term
        # -----------------------------
        stage3 = []
        for doc in docs:
            label = doc.get("label", "")
            if not label:
                continue
            if term_lower in label.lower():
                stage3.append(doc)

        if stage3:
            stage3.sort(
                key=lambda d: (
                    0 if (d.get("ontology_prefix", "").lower() in BIO_ONTOLOGY_PREFIXES) else 1,
                    len(d.get("label", ""))
                )
            )
            best = stage3[0]
            definition_list = best.get("description") or []
            definition = definition_list[0].strip() if definition_list else ""
            if definition:
                return {
                    "label": best.get("label"),
                    "definition": definition,
                    "iri": best.get("iri")
                }

        return None

    except Exception:
        return None

# ---------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------

def extract_ontology_terms(pages_output):
    """
    Given pages_output from extract_text.py, return:
      term -> { label, definition, iri }
    """
    candidate_terms = set()

    # 1. Collect candidates
    for page in pages_output:

        # Single words
        for w in page.get("words", []):
            raw = w.get("text", "")
            if raw and is_candidate_single_word(raw):
                norm = normalize_term(raw)
                if len(norm) >= 3:
                    candidate_terms.add(norm)

        # Phrases and n-grams
        for phrase_obj in page.get("phrases", []):
            phrase_text = phrase_obj.get("text", "")
            if not phrase_text:
                continue

            for t in phrase_ngrams_for_ontology(phrase_text):
                norm = normalize_term(t)
                if len(norm) >= 3:
                    candidate_terms.add(norm)

    # 2. Cap total terms
    if len(candidate_terms) > MAX_TERMS_PER_DOCUMENT:
        candidate_terms = set(islice(sorted(candidate_terms), MAX_TERMS_PER_DOCUMENT))

    print("CANDIDATE TERMS:", sorted(candidate_terms), file=sys.stdout, flush=True)

    # 3. Query OLS4
    found_terms = {}
    for term in sorted(candidate_terms):
        hit = lookup_term_ols4(term)
        if hit:
            found_terms[term] = hit

    return found_terms
