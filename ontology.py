import requests
import re

# -----------------------------
# CACHE
# -----------------------------
import json
import os

CACHE_FILE = "/tmp/term_cache.json"

# If /tmp cache doesn't exist yet, initialize it from the repo version
if not os.path.exists(CACHE_FILE):
    if os.path.exists("term_cache.json"):
        with open("term_cache.json", "r") as src, open(CACHE_FILE, "w") as dst:
            dst.write(src.read())

# Load the cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        TERM_CACHE = json.load(f)
else:
    TERM_CACHE = {}

# -----------------------------
# AUTHOR / CITATION DETECTION
# -----------------------------

def looks_like_author_name(word):
    """
    Detect capitalized author last names commonly found in citations.
    """
    if re.match(r"^[A-Z][a-z]+$", word):
        return True
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
    """
    Query the OLS4 API for a scientific term.
    Uses in-memory caching to avoid repeated lookups.
    Returns a dict with label, definition, iri OR None if not found.
    """

    key = term.strip().lower()

    # Only return cached entries that actually contain definitions
    if key in TERM_CACHE:
        return TERM_CACHE[key]

    url = "https://www.ebi.ac.uk/ols4/api/search"
    params = {
        "q": term,
        "queryFields": "label",
        "fields": "label,description,iri",
        "exact": "true"
    }

    try:
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()

        docs = data.get("response", {}).get("docs", [])
        if not docs:
            # Do NOT cache missing terms
            return None

        doc = docs[0]
        definition = (doc.get("description") or [""])[0].strip()

        # Only cache if definition is non-empty
        if definition:
            result = {
                "label": doc.get("label"),
                "definition": definition,
                "iri": doc.get("iri")
            }

            TERM_CACHE[key] = result

            with open(CACHE_FILE, "w") as f:
                json.dump(TERM_CACHE, f, indent=2)

            commit_cache_to_github()
            return result

        # If definition is empty, do NOT cache
        return None

    except Exception:
        # Do NOT cache failures
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
    """
    Decide if a single word is worth checking in OLS.
    Expanded to include:
    - strain names (XBY01, H37Rv)
    - gene names (uvrC, recA)
    - families (-aceae)
    - orders (-ales)
    - classes (Mollicutes)
    - proteins (lipoproteins)
    """

    word_clean = re.sub(r"[^A-Za-z0-9\-]", "", word)

    if len(word_clean) < 3:
        return False

    if word_clean.lower() in COMMON_WORDS:
        return False

    if word_clean.isdigit():
        return False

    # Reject author names ONLY for single-word terms
    if looks_like_author_name(word_clean):
        return False

    # Gene names (uvrC, recA, BRCA1)
    if re.match(r"^[A-Za-z]{2,6}\d*[A-Za-z]*$", word_clean):
        return True

    # Strain names (XBY01, H37Rv, K12, etc.)
    if re.match(r"^[A-Z]{1,4}\d{1,4}[A-Za-z0-9]*$", word_clean):
        return True

    # Family names (-aceae)
    if word_clean.lower().endswith("aceae"):
        return True

    # Order names (-ales)
    if word_clean.lower().endswith("ales"):
        return True

    # Class names (Mollicutes-style)
    if re.match(r"^[A-Z][a-z]+$", word_clean):
        return True
    
    # Broad taxonomic names (e.g., Firmicutes, Actinobacteria, Proteobacteria)
    if re.match(r"^[A-Z][a-zA-Z]+$", word_clean):
        return True

    # Protein names
    if word_clean.lower().endswith("protein") or word_clean.lower().endswith("proteins"):
        return True

    # Scientific prefixes/suffixes
    if word_clean.lower().startswith(SCI_PREFIXES):
        return True
    if word_clean.lower().endswith(SCI_SUFFIXES):
        return True

    return False


def is_candidate_phrase(phrase):
    """
    Decide if a multi-word phrase is worth checking in OLS.
    Expanded to include:
    - species (Genus species)
    - subspecies
    - serotypes
    - strain phrases
    """

    words = phrase.split()

    # Reject citation patterns
    if phrase_is_citation(phrase):
        return False

    # Reject if ALL words look like author names
    if all(looks_like_author_name(w) for w in words):
        return False

    # Species names (Genus species) with flexible capitalization
    if len(words) == 2:
        w1, w2 = words
        
    # Genus: capitalized or abbreviated (E. or Escherichia)
        if re.match(r"^[A-Z][a-z]+$|^[A-Z]\.$", w1):
        
            # species: usually lowercase but allow capitalized due to PDF errors
            if re.match(r"^[a-zA-Z]+$", w2):
                return True

    # Allow subspecies phrases
    if "subspecies" in phrase.lower():
        return True

    # Allow serotype phrases
    if "serotype" in phrase.lower():
        return True

    # Allow strain phrases
    if "strain" in phrase.lower():
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

#----------------------
#Token to write terms into file
#----------------------

import base64

def commit_cache_to_github():
    import os
    import requests

    repo_owner = "CereuslyDilutedScience"
    repo_name = "comprehendase"
    file_path = "term_cache.json"
    branch = "main"

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    # Read updated cache from /tmp
    with open("/tmp/term_cache.json", "r") as f:
        content = f.read()

    # GitHub API URL
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

    # Get current file SHA
    r = requests.get(url, headers={"Authorization": f"token {token}"})
    r.raise_for_status()
    sha = r.json()["sha"]

    # Prepare commit payload
    payload = {
        "message": "Update ontology cache",
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha,
        "branch": branch
    }

    # Commit the file
    r = requests.put(url, json=payload, headers={"Authorization": f"token {token}"})
    r.raise_for_status()
