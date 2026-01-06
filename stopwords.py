from pathlib import Path

def load_stopwords(path: str) -> set[str]:
    """
    Load stopwords from a text file.
    Returns a set of lowercase terms.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    out = set()
    for line in lines:
        w = line.strip().lower()
        if w:
            out.add(w)
    return out

STOPWORDS = load_stopwords("stopwords.txt")
